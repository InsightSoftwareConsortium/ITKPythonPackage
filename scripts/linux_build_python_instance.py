import contextlib
import os
import shutil
from pathlib import Path
from typing import Any

from posix_build_python_instance import PosixBuildPythonInstance
from wheel_builder_utils import (
    remove_tree,
)


class LinuxBuildPythonInstance(PosixBuildPythonInstance):
    """Linux-specific wheel builder.

    Handles manylinux container builds, ``auditwheel`` wheel repair, and
    Linux-specific compiler/target triple configuration.
    """

    #: ``--exclude-libs``: libraries ``auditwheel`` must not bundle.
    exclude_libs: list[str] | str = ""

    def __init__(self, *, exclude_libs: list[str] | str = "", **kwargs: Any) -> None:
        """Take ``--exclude-libs``; the rest are the base's."""
        super().__init__(**kwargs)
        self.exclude_libs = exclude_libs

    def builds_manylinux(self) -> bool:
        """True when the wheels are repaired and tagged for manylinux."""
        return bool(self.target.manylinux_version)

    def caps_lto_jobs(self) -> bool:
        """The manylinux images link with GCC, whose ``-flto=auto`` uses every thread."""
        return self.builds_manylinux()

    def _configure_toolchain(self) -> None:
        self.cmake_compiler_configurations.set(
            "CMAKE_CXX_COMPILER_TARGET:STRING", self.target.linux_triple
        )

    def post_build_fixup(self) -> None:
        """Repair wheels with ``auditwheel`` and retag the ITK meta-wheel."""
        if self.builds_manylinux():
            # Repair all produced wheels with auditwheel for packages with so elements (starts with itk_)
            whl = None
            # e.g. itk_segmentation-6.0.0b2-cp311-abi3-linux_x86_64.whl
            # Extract Python version from platform_env
            if "-" in self.platform_env:
                # in manylinux case, platform env is manylinux228-py311, for example, don't want anything before '-'
                py_version = self.platform_env.split("-")[-1]
            else:
                py_version = self.platform_env
            cp_prefix: str = py_version.replace("py", "cp").replace(".", "")
            binary_wheel_glob_pattern: str = f"itk_*-*{cp_prefix}*-linux_*.whl"
            dist_path: Path = self.build_dir_root / "dist"
            for whl in dist_path.glob(binary_wheel_glob_pattern):
                self.fixup_wheel(str(whl))
            del whl
            # auditwheel cannot retag the itk metawheel, which has no native code.
            meta_wheel_glob_pattern: str = f"itk-*-*{cp_prefix}*-linux_*.whl"
            for metawhl in dist_path.glob(meta_wheel_glob_pattern):
                # Unpack, edit WHEEL tag, repack
                metawheel_dir = self.build_dir_root / "metawheel"
                metawheel_dir.mkdir(parents=True, exist_ok=True)
                metawheel_dist = self.build_dir_root / "metawheel-dist"
                metawheel_dist.mkdir(parents=True, exist_ok=True)
                self.echo_check_call(
                    [
                        self.config.python_executable,
                        "-m",
                        "wheel",
                        "unpack",
                        "--dest",
                        str(metawheel_dir),
                        str(metawhl),
                    ],
                    check=True,
                )
                # Find unpacked dir
                unpacked_dirs = list(metawheel_dir.glob("itk-*/itk*.dist-info/WHEEL"))
                # Wheel filename: {name}-{version}-{python}-{abi}-{platform}.whl
                python_tag, abi_tag = metawhl.stem.split("-")[-3:-1]
                tag = f"{python_tag}-{abi_tag}-{self.target.wheel_plat_tag}"
                for wheel_file in unpacked_dirs:
                    content = wheel_file.read_text(encoding="utf-8").splitlines()
                    new = []
                    for line in content:
                        if line.startswith("Tag: "):
                            new.append(f"Tag: {tag}")
                        else:
                            new.append(line)
                    wheel_file.write_text("\n".join(new) + "\n", encoding="utf-8")
                for fixed_dir in metawheel_dir.glob("itk-*"):
                    self.echo_check_call(
                        [
                            self.config.python_executable,
                            "-m",
                            "wheel",
                            "pack",
                            "--dest",
                            str(metawheel_dist),
                            str(fixed_dir),
                        ],
                        check=True,
                    )
                # Move and clean
                repacked = list(metawheel_dist.glob("*.whl"))
                if not repacked:
                    msg = (
                        f"Repacking {metawhl.name} produced no wheel in "
                        f"{metawheel_dist}; refusing to delete the original"
                    )
                    raise RuntimeError(msg)
                for new_whl in repacked:
                    shutil.move(
                        str(new_whl),
                        str((self.build_dir_root / "dist") / new_whl.name),
                    )
                # Remove old and temp
                with contextlib.suppress(OSError):
                    metawhl.unlink()
                remove_tree(metawheel_dir)
                remove_tree(metawheel_dist)

    def _build_env_lib_dir(self) -> Path:
        """Return the build environment's ``lib`` directory.

        Derived from ``PYTHON_EXECUTABLE`` (``<prefix>/bin/python``) so that
        it does not depend on ``CONDA_PREFIX`` being exported.
        """
        python_executable = self.config.python_executable
        lib_dir = python_executable.resolve().parent.parent / "lib"
        if not lib_dir.is_dir():
            msg = (
                f"Build environment library directory {lib_dir} does not exist "
                f"(derived from PYTHON_EXECUTABLE={python_executable})"
            )
            raise RuntimeError(msg)
        return lib_dir

    def fixup_module_wheel(self, filepath: str) -> None:
        """Repair a remote module's wheel into the module's ``dist/``."""
        self.fixup_wheel(filepath, remote_module_wheel=True)

    def fixup_wheel(self, filepath: str, remote_module_wheel: bool = False) -> None:
        """Repair a wheel with ``auditwheel`` and apply manylinux platform tags.

        Parameters
        ----------
        filepath : str
            Path to the ``.whl`` file.
        remote_module_wheel : bool, optional
            If True, output repaired wheel to the remote module's ``dist/``
            directory instead of the main build ``dist/``.
        """
        # Use auditwheel to repair wheels and set manylinux tags
        if self.builds_manylinux():
            output_dir = self._repair_output_dir(remote_module_wheel)
            cmd: list[str | Path] = [
                self.config.python_executable,
                "-m",
                "auditwheel",
                "repair",
                # One deterministic tag, matching the documented floor.
                "--only-plat",
                "--plat",
                self.target.wheel_plat_tag,
            ]
            excludes = self.exclude_libs
            if isinstance(excludes, list):
                excludes = ";".join(excludes)
            for lib in excludes.split(";"):
                if lib:
                    cmd += ["--exclude", lib]
            cmd += [str(filepath), "-w", str(output_dir)]
            # Provide LD_LIBRARY_PATH for oneTBB and common system paths
            extra_lib = str(self._tbb_prefix / "lib")
            env = self.subprocess_environment()
            env["LD_LIBRARY_PATH"] = ":".join(
                entry
                for entry in [
                    str(self._build_env_lib_dir()),
                    env.get("LD_LIBRARY_PATH", ""),
                    extra_lib,
                    "/usr/lib64",
                    "/usr/lib",
                ]
                if entry
            )
            print(f"RUNNING WITH PATH {os.environ['PATH']}")
            env["PATH"] = os.environ["PATH"]
            repair_status = self.echo_check_call(cmd, env=env)

            filepath_obj = Path(filepath)
            stem_prefix = "-".join(filepath_obj.stem.split("-")[:-1])
            repaired_wheel = (
                output_dir / f"{stem_prefix}-{self.target.wheel_plat_tag}.whl"
            )
            self._require_repaired(
                "auditwheel",
                filepath_obj,
                repair_status,
                repaired_wheel,
                repaired_wheel.name,
            )

            # Remove the original linux_*.whl now that the repair is verified.
            if (
                filepath_obj.exists()
                and "-linux_" in filepath_obj.name
                and filepath_obj.suffix == ".whl"
            ):
                print(
                    f"Removing original linux wheel after repair: {filepath_obj.name}"
                )
                try:
                    remove_tree(filepath_obj)
                except OSError as e:
                    print(f"Warning: Could not remove {filepath_obj.name}: {e}")
        else:
            print(
                "Building outside of manylinux environment does not require wheel fixups."
            )
