import contextlib
import fnmatch
import os
import re
import shutil
import zipfile
from collections.abc import Sequence
from pathlib import Path, PurePath
from typing import Any

from build_environment import PythonEnvironment
from build_python_instance_base import BuildPythonInstanceBase
from cmake_argument_builder import CMakeArgumentBuilder
from module_wheel_init import ITK_INIT, module_init_name, rename_wheel_member
from msvc_path_trim import msvc_trim_definitions

ARCHIVE_EXCLUDES = (
    "*.o",
    "*.obj",
    "wheelbuilds",
    "__pycache__",
    "install_manifest_*.txt",
    ".git",
    ".idea",
    ".pixi",
    "castxml_inputs",
    "Wrapping/Modules",
    "*.pdb",
)

#: Where ``build_tarball`` looks for 7-Zip before ``PATH``.
SEVEN_ZIP_CANDIDATES = (
    Path(r"C:\7-Zip\7z.exe"),
    Path(r"C:\Program Files\7-Zip\7z.exe"),
    Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
)


def _archive_excluded(relative: PurePath) -> bool:
    """Return True when *relative* matches an ``ARCHIVE_EXCLUDES`` pattern."""
    parts = relative.parts
    for pattern in ARCHIVE_EXCLUDES:
        pattern_parts = tuple(pattern.split("/"))
        width = len(pattern_parts)
        for start in range(len(parts) - width + 1):
            window = parts[start : start + width]
            if all(
                fnmatch.fnmatchcase(part, pat)
                for part, pat in zip(window, pattern_parts, strict=True)
            ):
                return True
    return False


class WindowsBuildPythonInstance(BuildPythonInstanceBase):
    """Windows-specific wheel builder.

    Handles Windows path conventions, pixi-based Python environment
    discovery, and ``delvewheel`` for wheel repair.
    """

    def __init__(
        self,
        *,
        windows_extra_lib_paths: list[str] | str = "",
        windows_exclude_libs: list[str] | str = "",
        **kwargs: Any,
    ) -> None:
        """Take ``--lib-paths`` and ``--exclude-libs``; the rest are the base's."""
        super().__init__(**kwargs)
        self.windows_extra_lib_paths = windows_extra_lib_paths
        self.windows_exclude_libs = windows_exclude_libs

    def _configure_toolchain(self) -> None:
        """Windows needs no toolchain values beyond the shared TBB settings."""

    def compiler_flag_definitions(
        self, user_defs: CMakeArgumentBuilder, compile_roots: Sequence[Path]
    ) -> dict[str, str]:
        """Trim the build directories from ``__FILE__``."""
        return msvc_trim_definitions(os.environ, user_defs, compile_roots)

    def python_build_generator_args(self) -> list[str]:
        """Build wheels with Ninja, as ITK itself is built."""
        # pixi's vs2022 activation sets a Visual Studio CMAKE_GENERATOR, whose
        # multi-config wrapping output collides.
        return ["--config-setting=cmake.args=-GNinja"]

    def post_build_fixup(self) -> None:
        """Repair wheels with ``delvewheel``, including oneTBB library paths."""
        self.fixup_wheels(self._delvewheel_lib_paths())

    def _delvewheel_lib_paths(self) -> str:
        """Return the ``--lib-paths`` directories and oneTBB's, semicolon-delimited."""
        # append the oneTBB-prefix\\bin directory for fixing wheels built with local oneTBB
        search_lib_paths = (
            [
                s
                for s in str(self.windows_extra_lib_paths[0]).rstrip(";").split(";")
                if s
            ]
            if self.windows_extra_lib_paths
            else []
        )
        search_lib_paths.append(str(self._tbb_prefix / "bin"))
        return ";".join(map(str, search_lib_paths))

    def fixup_wheels(self, lib_paths: str = "") -> None:
        """Repair the ``itk_core`` wheels, which link oneTBB."""
        # TBB library fix-up (applies to itk_core wheel)
        tbb_wheel = "itk_core"
        for wheel in (self.build_dir_root / "dist").glob(f"{tbb_wheel}*.whl"):
            self.fixup_wheel(str(wheel), lib_paths)

    def fixup_module_wheel(self, filepath: str) -> None:
        """Repair a remote module's wheel into the module's ``dist/``."""
        self.fixup_wheel(
            filepath, self._delvewheel_lib_paths(), remote_module_wheel=True
        )

    def fixup_wheel(
        self, filepath: str, lib_paths: str = "", remote_module_wheel: bool = False
    ) -> None:
        """Repair a wheel using ``delvewheel`` with the given library paths.

        Parameters
        ----------
        filepath : str
            Path to the ``.whl`` file to repair.
        lib_paths : str, optional
            Semicolon-delimited directories to add to ``delvewheel --add-path``.
            DLLs named by ``--exclude-libs`` go to ``delvewheel --no-dll``.
        remote_module_wheel : bool, optional
            If True, output the repaired wheel to the remote module's
            ``dist/`` directory instead of the main build ``dist/``,
            matching the Linux builder.
        """
        lib_paths = lib_paths.strip()
        lib_paths = lib_paths + ";" if lib_paths else ""
        print(f"Library paths for fixup: {lib_paths}")

        # A repaired module wheel replaces the unrepaired one in the module's dist/.
        output_dir = self._repair_output_dir(remote_module_wheel)
        # delvewheel keeps the file name, so a repair written beside the input
        # would be indistinguishable from the unrepaired wheel.
        staging_dir = output_dir / "delvewheel-repaired"
        shutil.rmtree(staging_dir, ignore_errors=True)
        if remote_module_wheel:
            module_init = module_init_name(Path(filepath))
            # delvewheel patches an existing itk/__init__.py rather than adding one.
            rename_wheel_member(Path(filepath), module_init, ITK_INIT)
        delve_wheel = "delvewheel.exe"
        cmd = [
            str(delve_wheel),
            "repair",
            "--no-mangle-all",
            "--add-path",
            lib_paths.strip(";"),
            *self._no_dll_arguments(),
            "--ignore-in-wheel",
            "-w",
            str(staging_dir),
            str(filepath),
        ]
        repair_status = self.echo_check_call(cmd)

        repaired_wheel = staging_dir / Path(filepath).name
        self._require_repaired(
            "delvewheel",
            Path(filepath),
            repair_status,
            repaired_wheel,
            str(repaired_wheel),
        )
        if remote_module_wheel:
            rename_wheel_member(repaired_wheel, ITK_INIT, module_init)
        repaired_wheel.replace(output_dir / repaired_wheel.name)
        shutil.rmtree(staging_dir, ignore_errors=True)

    def _no_dll_arguments(self) -> list[str]:
        """Return ``--no-dll`` with the ``--exclude-libs`` value, if one was given."""
        excludes = self.windows_exclude_libs
        if isinstance(excludes, list):
            excludes = ";".join(excludes)
        excludes = excludes.strip(";")
        return ["--no-dll", excludes] if excludes else []

    def build_tarball(self) -> None:
        """Archive the ITK source, build tree, and IPP into ``ITKPythonBuilds-windows.zip``.

        Uses 7-Zip when present and a Python zip of the same content
        otherwise. ``dist/`` is not archived, so the wheels survive.
        """
        out_zip = self.build_dir_root / "ITKPythonBuilds-windows.zip"
        archive_roots = [
            self.build_dir_root / "ITK",
            self.build_dir_root / "build",
            self.ipp_dir,
        ]

        seven_zip = None
        for cand in SEVEN_ZIP_CANDIDATES:
            if cand.exists():
                seven_zip = cand
                break

        if seven_zip is None:
            found = shutil.which("7z.exe") or shutil.which("7z")
            if found:
                seven_zip = Path(found)

        if seven_zip is not None:
            # "7z a" adds to an existing archive, keeping files since deleted.
            out_zip.unlink(missing_ok=True)
            # No -r: it would match build/ recursively and sweep in a module's tree.
            cmd = [
                str(seven_zip),
                "a",
                "-t7z",
                str(out_zip),
                *map(str, archive_roots),
            ]
            cmd += ["-xr!" + pattern.replace("/", "\\") for pattern in ARCHIVE_EXCLUDES]
            return_status: int = self.echo_check_call(cmd)
            if return_status == 0:
                return

        if out_zip.exists():
            with contextlib.suppress(Exception):
                out_zip.unlink()
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            for root in archive_roots:
                if not root.exists():
                    continue
                for dirpath, dirnames, filenames in os.walk(root):
                    rel_dir = Path(dirpath).relative_to(root.parent)
                    dirnames[:] = sorted(
                        d for d in dirnames if not _archive_excluded(rel_dir / d)
                    )
                    for name in sorted(filenames):
                        if not _archive_excluded(rel_dir / name):
                            archive.write(
                                Path(dirpath) / name, (rel_dir / name).as_posix()
                            )

    def venv_paths(self) -> PythonEnvironment:
        """Return the pixi-managed Python environment on Windows."""

        def get_python_version(platform_env: str) -> tuple[int, int] | None:
            pattern = re.compile(r"py3(?P<minor>\d+)")
            m = pattern.search(platform_env)
            if not m:
                return None
            return 3, int(m.group("minor"))

        python_exe = self.config.python_executable

        env_root = python_exe.parent

        python_version = get_python_version(self.platform_env)
        if python_version is None:
            msg = f"No Python version (py3NN) in platform env {self.platform_env!r}"
            raise ValueError(msg)
        python_major, python_minor = python_version
        # Version-specific library (e.g., python311.lib) - required for
        # CMake's FindPython3 to extract version info for Development.Module
        xy_lib_ver = f"{python_major}{python_minor}"

        return PythonEnvironment(
            root_dir=env_root,
            include_dir=env_root / "include",
            library=env_root / "libs" / f"python{xy_lib_ver}.lib",
            bin_path=env_root,
            base_dir=env_root,
            # Stable ABI library (python3.lib) - for Development.SABIModule
            sabi_library=env_root / "libs" / f"python{python_major}.lib",
        )
