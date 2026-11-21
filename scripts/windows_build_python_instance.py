import contextlib
import fnmatch
import os
import re
import shutil
import zipfile
from pathlib import Path, PurePath

from build_python_instance_base import BuildPythonInstanceBase

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

    def _configure_toolchain(self) -> None:
        """Windows needs no toolchain values beyond the shared TBB settings."""

    def post_build_fixup(self) -> None:
        """Repair wheels with ``delvewheel``, including oneTBB library paths."""
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
        search_lib_paths_str: str = ";".join(map(str, search_lib_paths))
        self.fixup_wheels(search_lib_paths_str)

    def fixup_wheels(self, lib_paths: str = ""):
        """Repair the ``itk_core`` wheels, which link oneTBB."""
        # TBB library fix-up (applies to itk_core wheel)
        tbb_wheel = "itk_core"
        for wheel in (self.build_dir_root / "dist").glob(f"{tbb_wheel}*.whl"):
            self.fixup_wheel(str(wheel), lib_paths)

    def fixup_wheel(
        self, filepath, lib_paths: str = "", remote_module_wheel: bool = False
    ) -> None:
        """Repair a wheel using ``delvewheel`` with the given library paths.

        Parameters
        ----------
        filepath : str
            Path to the ``.whl`` file to repair.
        lib_paths : str, optional
            Semicolon-delimited directories to add to ``delvewheel --add-path``.
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
        delve_wheel = "delvewheel.exe"
        cmd = [
            str(delve_wheel),
            "repair",
            "--no-mangle-all",
            "--add-path",
            lib_paths.strip(";"),
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
        repaired_wheel.replace(output_dir / repaired_wheel.name)
        shutil.rmtree(staging_dir, ignore_errors=True)

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

        seven_zip_candidates = [
            Path(r"C:\\7-Zip\\7z.exe"),
            Path(r"C:\\Program Files\\7-Zip\\7z.exe"),
            Path(r"C:\\Program Files (x86)\\7-Zip\\7z.exe"),
        ]

        seven_zip = None
        for cand in seven_zip_candidates:
            if cand.exists():
                seven_zip = cand
                break

        if seven_zip is None:
            found = shutil.which("7z.exe") or shutil.which("7z")
            if found:
                seven_zip = Path(found)

        if seven_zip is not None:
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

    def venv_paths(self) -> None:
        """Populate ``venv_info_dict`` from the pixi-managed Python environment on Windows."""

        def get_python_version(platform_env: str) -> tuple[int, int] | None:
            pattern = re.compile(r"py3(?P<minor>\d+)")
            m = pattern.search(platform_env)
            if not m:
                return None
            return 3, int(m.group("minor"))

        python_exe = Path(self.package_env_config["PYTHON_EXECUTABLE"])

        env_root = python_exe.parent
        venv_bin_path = env_root
        venv_base_dir = env_root
        python_include_dir = env_root / "include"

        python_version = get_python_version(self.platform_env)
        if python_version is None:
            msg = f"No Python version (py3NN) in platform env {self.platform_env!r}"
            raise ValueError(msg)
        python_major, python_minor = python_version
        # Version-specific library (e.g., python311.lib) - required for
        # CMake's FindPython3 to extract version info for Development.Module
        xy_lib_ver = f"{python_major}{python_minor}"
        python_library = env_root / "libs" / f"python{xy_lib_ver}.lib"

        # Stable ABI library (python3.lib) - for Development.SABIModule
        python_sabi_library = env_root / "libs" / f"python{python_major}.lib"

        self.venv_info_dict = {
            "python_include_dir": python_include_dir,
            "python_library": python_library,
            "python_sabi_library": python_sabi_library,
            "venv_bin_path": venv_bin_path,
            "venv_base_dir": venv_base_dir,
            "python_root_dir": env_root,
        }
