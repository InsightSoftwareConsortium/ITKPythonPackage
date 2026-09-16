import os
import shutil
from pathlib import Path

from posix_build_python_instance import PosixBuildPythonInstance
from wheel_builder_utils import (
    _remove_tree,
)


class LinuxBuildPythonInstance(PosixBuildPythonInstance):
    """Linux-specific wheel builder.

    Handles manylinux container builds, ``auditwheel`` wheel repair, and
    Linux-specific compiler/target triple configuration.
    """

    def _configure_toolchain(self) -> None:
        self.package_env_config["USE_TBB"] = "ON"
        self.package_env_config["TBB_DIR"] = str(
            self.build_dir_root / "build" / "oneTBB-prefix" / "lib" / "cmake" / "TBB"
        )
        self.cmake_compiler_configurations.set(
            "CMAKE_CXX_COMPILER_TARGET:STRING", self.target.linux_triple
        )

    def post_build_fixup(self) -> None:
        """Repair wheels with ``auditwheel`` and retag the ITK meta-wheel."""
        manylinux_ver: str | None = self.package_env_config.get(
            "MANYLINUX_VERSION", None
        )
        if manylinux_ver:
            # Repair all produced wheels with auditwheel for packages with so elements (starts with itk_)
            whl = None
            # cp39-cp39-linux itk_segmentation-6.0.0b2-cp39-cp39-linux_x86_64.whl
            # Extract Python version from platform_env
            if "-" in self.platform_env:
                # in manylinux case, platform env is manylinux-cp311, for example, don't want anything before '-'
                py_version = self.platform_env.split("-")[-1]
            else:
                py_version = self.platform_env
            cp_prefix: str = py_version.replace("py", "cp").replace(".", "")
            binary_wheel_glob_pattern: str = f"itk_*-*{cp_prefix}*-linux_*.whl"
            dist_path: Path = self.build_dir_root / "dist"
            for whl in dist_path.glob(binary_wheel_glob_pattern):
                if whl.name.startswith("itk-"):
                    print(
                        f"Skipping the itk-meta wheel that has nothing to fixup {whl}"
                    )
                    continue
                self.fixup_wheel(str(whl))
            del whl
            # Retag meta-wheel: Special handling for the itk meta wheel to adjust tag
            # auditwheel does not process this "metawheel" correctly since it does not
            # have any native SO's.
            meta_wheel_glob_pattern: str = f"itk-*-*{cp_prefix}*-linux_*.whl"
            for metawhl in dist_path.glob(meta_wheel_glob_pattern):
                # Unpack, edit WHEEL tag, repack
                metawheel_dir = self.build_dir_root / "metawheel"
                metawheel_dir.mkdir(parents=True, exist_ok=True)
                metawheel_dist = self.build_dir_root / "metawheel-dist"
                metawheel_dist.mkdir(parents=True, exist_ok=True)
                self.echo_check_call(
                    [
                        self.package_env_config["PYTHON_EXECUTABLE"],
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
                for wheel_file in unpacked_dirs:
                    content = wheel_file.read_text(encoding="utf-8").splitlines()
                    base = metawhl.name
                    if len(manylinux_ver) > 0:
                        base = metawhl.name.replace(
                            "linux", f"manylinux{manylinux_ver}"
                        )
                    # Wheel filename: {name}-{version}-{python}-{abi}-{platform}.whl
                    # Tag must be only "{python}-{abi}-{platform}", not the full stem.
                    stem = Path(base).stem
                    parts = stem.split("-")
                    tag = "-".join(parts[-3:])
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
                            self.package_env_config["PYTHON_EXECUTABLE"],
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
                    raise RuntimeError(
                        f"Repacking {metawhl.name} produced no wheel in "
                        f"{metawheel_dist}; refusing to delete the original"
                    )
                for new_whl in repacked:
                    shutil.move(
                        str(new_whl),
                        str((self.build_dir_root / "dist") / new_whl.name),
                    )
                # Remove old and temp
                try:
                    metawhl.unlink()
                except OSError:
                    pass
                _remove_tree(metawheel_dir)
                _remove_tree(metawheel_dist)

    def _build_env_lib_dir(self) -> Path:
        """Return the build environment's ``lib`` directory.

        Derived from ``PYTHON_EXECUTABLE`` (``<prefix>/bin/python``) so that
        it does not depend on ``CONDA_PREFIX`` being exported.
        """
        python_executable = self.package_env_config.get("PYTHON_EXECUTABLE", "")
        if not python_executable:
            raise RuntimeError(
                "PYTHON_EXECUTABLE is unset; cannot locate the build "
                "environment library directory for auditwheel"
            )
        lib_dir = Path(python_executable).resolve().parent.parent / "lib"
        if not lib_dir.is_dir():
            raise RuntimeError(
                f"Build environment library directory {lib_dir} does not exist "
                f"(derived from PYTHON_EXECUTABLE={python_executable})"
            )
        return lib_dir

    def fixup_wheel(
        self, filepath, lib_paths: str = "", remote_module_wheel: bool = False
    ) -> None:
        """Repair a wheel with ``auditwheel`` and apply manylinux platform tags.

        Parameters
        ----------
        filepath : str
            Path to the ``.whl`` file.
        lib_paths : str, optional
            Unused on Linux (kept for interface compatibility).
        remote_module_wheel : bool, optional
            If True, output repaired wheel to the remote module's ``dist/``
            directory instead of the main build ``dist/``.
        """
        # Use auditwheel to repair wheels and set manylinux tags
        manylinux_ver = self.package_env_config.get("MANYLINUX_VERSION", "")
        if len(manylinux_ver) > 1:
            cmd = [
                self.package_env_config["PYTHON_EXECUTABLE"],
                "-m",
                "auditwheel",
                "repair",
                # One deterministic tag, matching the documented floor.
                "--only-plat",
                "--plat",
                self.target.wheel_plat_tag,
            ]
            cmd += [
                str(filepath),
                "-w",
                (
                    str(self.module_source_dir / "dist")
                    if remote_module_wheel
                    else str(self.build_dir_root / "dist")
                ),
            ]
            # Provide LD_LIBRARY_PATH for oneTBB and common system paths
            extra_lib = str(
                self.package_env_config["IPP_SUPERBUILD_BINARY_DIR"].parent
                / "oneTBB-prefix"
                / "lib"
            )
            env = dict(self.package_env_config)
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
            print(f'RUNNING WITH PATH {os.environ["PATH"]}')
            env["PATH"] = os.environ["PATH"]
            repair_status = self.echo_check_call(cmd, env=env)

            filepath_obj = Path(filepath)
            output_dir = (
                self.module_source_dir / "dist"
                if remote_module_wheel
                else self.build_dir_root / "dist"
            )
            stem_prefix = "-".join(filepath_obj.stem.split("-")[:-1])
            repaired_wheel = (
                output_dir / f"{stem_prefix}-{self.target.wheel_plat_tag}.whl"
            )

            if repair_status != 0 or not repaired_wheel.exists():
                raise RuntimeError(
                    f"auditwheel repair failed for {filepath_obj.name} "
                    f"(exit status {repair_status}, expected output "
                    f"{repaired_wheel.name})"
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
                    _remove_tree(filepath_obj)
                except OSError as e:
                    print(f"Warning: Could not remove {filepath_obj.name}: {e}")
        else:
            print(
                "Building outside of manylinux environment does not require wheel fixups."
            )
        return

    def discover_python_venvs(
        self, platform_os_name: str, platform_architecture: str
    ) -> list[str]:
        """Extend the POSIX discovery with manylinux ``/opt/python`` installs."""
        names = super().discover_python_venvs(platform_os_name, platform_architecture)
        opt_python = Path("/opt/python")
        if opt_python.exists():
            names.extend(p.name for p in opt_python.iterdir() if p.is_dir())
        return sorted(names)
