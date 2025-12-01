from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

import shutil
import subprocess
from pathlib import Path
from os import environ, pathsep
import json
import time
from datetime import datetime

from wheel_builder_utils import (
    _remove_tree,
    echo_check_call,
    push_env,
    _which,
)


class BuildManager:
    """Manage a JSON build report for multi-step runs.

    - Persists status and timing for each named step.
    - Skips steps that are already marked as completed on subsequent runs.
    - Saves after each step and on demand.
    """

    def __init__(self, report_path: Path, step_names: list[str]):
        self.report_path = Path(report_path)
        self._init_structure(step_names)
        self._load_if_exists()

    # ---- Public API ----
    def run_step(self, step_name: str, func) -> None:
        entry = self.report["steps"].setdefault(step_name, self._new_step_entry())
        if entry.get("status") == "done":
            # Already completed in a previous run; skip
            return

        # Mark start
        entry["status"] = "running"
        entry["started_at"] = self._now()
        self.report["updated_at"] = entry["started_at"]
        self.save()

        start = time.perf_counter()
        try:
            func()
        except Exception as e:
            # Record failure and re-raise
            entry["status"] = "failed"
            entry["finished_at"] = self._now()
            entry["duration_sec"] = round(time.perf_counter() - start, 3)
            entry["error"] = f"{type(e).__name__}: {e}"
            self.report["updated_at"] = entry["finished_at"]
            self.save()
            raise
        else:
            # Record success
            entry["status"] = "done"
            entry["finished_at"] = self._now()
            entry["duration_sec"] = round(time.perf_counter() - start, 3)
            self.report["updated_at"] = entry["finished_at"]
            self.save()

    def save(self) -> None:
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.report_path.with_suffix(self.report_path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.report, f, indent=2, sort_keys=True)
        tmp.replace(self.report_path)

    # ---- Internal helpers ----
    def _init_structure(self, step_names: list[str]) -> None:
        steps = {name: self._new_step_entry() for name in step_names}
        now = self._now()
        self.report = {
            "created_at": now,
            "updated_at": now,
            "steps": steps,
        }

    def _load_if_exists(self) -> None:
        if not self.report_path.exists():
            return
        try:
            with open(self.report_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            # Merge existing with current set of steps, preserving statuses
            existing_steps = existing.get("steps", {})
            for name in self.report["steps"].keys():
                if name in existing_steps:
                    self.report["steps"][name] = existing_steps[name]
            # Bring over timestamps
            self.report["created_at"] = existing.get(
                "created_at", self.report["created_at"]
            )
            self.report["updated_at"] = existing.get(
                "updated_at", self.report["updated_at"]
            )
        except Exception:
            # Corrupt or unreadable file; keep freshly initialized structure
            pass

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _new_step_entry() -> dict:
        return {
            "status": "pending",
            "started_at": None,
            "finished_at": None,
            "duration_sec": None,
        }


class BuildPythonInstanceBase(ABC):
    """
    Abstract base class to build wheels for a single Python environment.

    Concrete subclasses implement platform-specific details by delegating to
    injected helper functions. This avoids circular imports with the script
    that defines those helpers.
    """

    def __init__(
        self,
        *,
        py_env,
        wheel_names: Iterable[str],
        platform_name: str,
        platform_architechture: str,
        ipp_source_dir: Path | str,
        ipp_superbuild_binary_dir: Path | str,
        itk_source_dir: Path | str,
        script_dir: Path | str,
        package_env_config: dict,
        cleanup: bool,
        cmake_options: list[str],
        windows_extra_lib_paths: list[str],
        dist_dir: Path,
    ) -> None:
        self.py_env = py_env
        self.wheel_names = list(wheel_names)
        self.platform_name = platform_name
        self.platform_architechture = platform_architechture
        self.IPP_SOURCE_DIR = ipp_source_dir
        self.IPP_SUPERBUILD_BINARY_DIR = ipp_superbuild_binary_dir
        self.ITK_SOURCE_DIR = itk_source_dir
        self.SCRIPT_DIR = script_dir
        self.package_env_config = package_env_config
        self.cleanup = cleanup
        self.cmake_options = cmake_options
        self.windows_extra_lib_paths = windows_extra_lib_paths
        self.dist_dir = dist_dir
        self._cmake_executable = None
        self._doxygen_executable = None
        self._use_tbb = "ON"
        self._tbb_dir = None
        self._build_type = "Release"
        self.venv_info_dict = {
            "python_executable": None,
            "python_include_dir": None,
            "python_library": None,
            "pip_executable": None,
            "ninja_executable": None,
            "venv_bin_path": None,
            "venv_base_dir": None,
        }

    def run(self) -> None:
        """Run the full build flow for this Python instance."""
        # Use BuildManager to persist and resume build steps
        python_packabge_build_steps: dict = {
            "00_prepare_build_env": self.prepare_build_env,
            "01_superbuild_support_components": self.build_superbuild_support_components,
            "02_build_wheels": self.build_wheel,
            "03_post_build_fixup": self.post_build_fixup,
            "04_final_import_test": self.final_import_test,
        }
        self.dist_dir.mkdir(parents=True, exist_ok=True)
        build_report_fn: Path = self.dist_dir / f"build_log_{self.py_env}.json"
        build_manager: BuildManager = BuildManager(
            build_report_fn, list(python_packabge_build_steps.keys())
        )
        build_manager.save()
        for build_step_name, build_step_func in python_packabge_build_steps.items():
            print("=" * 80)
            print(f"Running build step: {build_step_name}")
            build_manager.run_step(build_step_name, build_step_func)
            build_manager.save()
            print(f"Build step {build_step_name} completed.")
            print("=" * 80)

    def build_superbuild_support_components(self):
        # -----------------------------------------------------------------------
        # Build required components (optional local ITK source, TBB builds) used to populate the archive cache
        cmd = [
            self._cmake_executable,
            "-G",
            "Ninja",
            "-DITKPythonPackage_BUILD_PYTHON:BOOL=OFF",
            f"-DITKPythonPackage_USE_TBB:BOOL={self._use_tbb}",
            f"-DCMAKE_BUILD_TYPE:STRING={self._build_type}",
            f"-DCMAKE_MAKE_PROGRAM:FILEPATH={self.venv_info_dict['ninja_executable']}",
            f"-DITK_SOURCE_DIR:PATH={self.package_env_config['ITK_SOURCE_DIR']}",
            f"-DITK_GIT_TAG:STRING={self.package_env_config['ITK_GIT_TAG']}",
        ]

        cmd.extend(self.cmake_options)

        cmd += [
            "-S",
            str(self.IPP_SOURCE_DIR),
            "-B",
            str(self.IPP_SUPERBUILD_BINARY_DIR),
        ]

        echo_check_call(cmd)
        echo_check_call(
            [
                self.venv_info_dict["ninja_executable"],
                "-C",
                str(self.IPP_SUPERBUILD_BINARY_DIR),
            ]
        )

    def fixup_wheels(self, lib_paths: str = ""):
        # TBB library fix-up (applies to itk_core wheel)
        tbb_wheel = "itk_core"
        for wheel in (self.IPP_SOURCE_DIR / "dist").glob(f"{tbb_wheel}*.whl"):
            self.fixup_wheel(str(wheel), lib_paths)

    def final_wheel_import_test(self, installed_dist_dir: Path):
        echo_check_call(
            [
                self.venv_info_dict["pip_executable"],
                "install",
                "itk",
                "--no-cache-dir",
                "--no-index",
                "-f",
                str(installed_dist_dir),
            ]
        )
        print("Wheel successfully installed.")
        # Basic imports
        echo_check_call([self.venv_info_dict["python_executable"], "-c", "import itk;"])
        echo_check_call(
            [
                self.venv_info_dict["python_executable"],
                "-c",
                "import itk; image = itk.Image[itk.UC, 2].New()",
            ]
        )
        echo_check_call(
            [
                self.venv_info_dict["python_executable"],
                "-c",
                "import itkConfig; itkConfig.LazyLoading=False; import itk;",
            ]
        )
        # Full doc tests
        echo_check_call(
            [
                self.venv_info_dict["python_executable"],
                str(self.IPP_SOURCE_DIR / "docs" / "code" / "test.py"),
            ]
        )
        print("Documentation tests passed.")

    @staticmethod
    def _pip_uninstall_itk_wildcard(pip_executable: str):
        """Uninstall all installed packages whose name starts with 'itk'.

        pip does not support shell-style wildcards directly for uninstall, so we:
          - run 'pip list --format=freeze'
          - collect package names whose normalized name starts with 'itk'
          - call 'pip uninstall -y <names...>' if any are found
        """
        try:
            proc = subprocess.run(
                [pip_executable, "list", "--format=freeze"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"Warning: failed to list packages with pip at {pip_executable}: {e}")
            return

        packages = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Formats like 'name==version' or 'name @ URL'
            name = line.split("==")[0].split(" @ ")[0].strip()
            if name.lower().startswith("itk"):
                packages.append(name)

        if packages:
            print(f"Uninstalling existing ITK-related packages: {' '.join(packages)}")
            # Use echo_check_call for consistent logging/behavior
            echo_check_call([pip_executable, "uninstall", "-y", *packages])

    def find_unix_exectable_paths(
        self,
        venv_dir: Path,
    ) -> tuple[str, str, str, str, str, str, Path]:
        python_executable = venv_dir / "bin" / "python3"
        if not python_executable.exists():
            raise FileNotFoundError(f"Python executable not found: {python_executable}")
        pip_executable = venv_dir / "bin" / "pip3"
        if not pip_executable.exists():
            raise FileNotFoundError(f"pip executable not found: {pip_executable}")

        # Prefer venv's ninja, else fall back to PATH
        ninja_executable_path: Path = venv_dir / "bin" / "ninja"
        ninja_executable: Path = self.find_unix_ninja_executable(ninja_executable_path)
        if not ninja_executable.exists():
            raise FileNotFoundError(f"Ninja executable not found: {ninja_executable}")
        # Compute Python include dir using sysconfig for the given interpreter
        try:
            python_include_dir = (
                subprocess.check_output(
                    [
                        str(python_executable),
                        "-c",
                        "import sysconfig; print(sysconfig.get_paths()['include'])",
                    ],
                    text=True,
                ).strip()
                or ""
            )
        except Exception as e:
            print(f"Failed to compute Python include dir: {e}\n defaulting to empty")
            python_include_dir = ""

        # modern CMake with Python3 can infer the library from executable; leave empty
        python_library = ""

        # Update PATH
        venv_bin_path = venv_dir / "bin"
        return (
            str(python_executable),
            python_include_dir,
            python_library,
            str(pip_executable),
            str(ninja_executable),
            str(venv_bin_path),
            venv_dir,
        )

    @staticmethod
    def find_unix_ninja_executable(ninja_executable_path: Path) -> Path | None:
        ninja_executable = (
            str(ninja_executable_path)
            if ninja_executable_path.exists()
            else (shutil.which("ninja") or str(ninja_executable_path))
        )
        return Path(ninja_executable)

    @abstractmethod
    def venv_paths(self):
        pass

    @abstractmethod
    def fixup_wheel(self, filepath, lib_paths: str = ""):  # pragma: no cover - abstract
        pass

    @abstractmethod
    def prepare_build_env(self) -> None:  # pragma: no cover - abstract
        pass

    @abstractmethod
    def post_build_fixup(self) -> None:  # pragma: no cover - abstract
        pass

    @abstractmethod
    def final_import_test(self) -> None:  # pragma: no cover - abstract
        pass

    @abstractmethod
    def discover_python_venvs(
        self, platform_os_name: str, platform_architechure: str
    ) -> list[str]:
        pass

    def build_wheel(self):
        """
        REDO:  cmake_options do not belong here, they should be at intialization
        need to make cmake configure module settings as dictionary to be re-user_data_dir
        for standard cmake.exe and build wrapped cmake, and remove the replace magic
        below:
        make ITK specific build flags dictionary
        make compiler environment specific dictionary
        make other features specific dictionary

        """

        with push_env(
            PATH=f"{self.venv_info_dict['venv_bin_path']}{pathsep}{environ['PATH']}"
        ):

            source_path = f"{self.package_env_config['ITK_SOURCE_DIR']}"
            # Build path naming per platform
            if self.platform_name == "windows":
                build_path = self.IPP_SOURCE_DIR / f"ITK-win_{self.py_env}"
            elif self.platform_name == "darwin":
                osx_arch = (
                    "arm64" if self.platform_architechture == "arm64" else "x86_64"
                )
                build_path = (
                    self.IPP_SOURCE_DIR / f"ITK-{self.py_env}-macosx_{osx_arch}"
                )
            elif self.platform_name == "linux":
                # TODO: do not use environ here, get from package_env instead
                manylinux_ver = environ.get("MANYLINUX_VERSION", "")
                build_path = (
                    self.IPP_SOURCE_DIR
                    / f"ITK-{self.py_env}-manylinux{manylinux_ver}_{self.platform_architechture}"
                )
            else:
                raise ValueError(f"Unknown platform {self.platform_name}")
            pyproject_configure = self.SCRIPT_DIR / "pyproject_configure.py"

            # Clean up previous invocations
            if self.cleanup and Path(build_path).exists():
                _remove_tree(Path(build_path))

            print("#")
            print("# Build multiple ITK wheels")
            print("#")

            self.build_wrapped_itk(
                build_path,
            )

            # Build wheels

            env_file = self.IPP_SOURCE_DIR / "build" / "package.env"
            for wheel_name in self.wheel_names:
                # Configure pyproject.toml
                echo_check_call(
                    [
                        str(self.venv_info_dict["python_executable"]),
                        pyproject_configure,
                        "--env-file",
                        env_file,
                        wheel_name,
                    ]
                )

                # Generate wheel
                cmd = [
                    str(self.venv_info_dict["python_executable"]),
                    "-m",
                    "build",
                    "--verbose",
                    "--wheel",
                    "--outdir",
                    str(self.IPP_SOURCE_DIR / "dist"),
                    "--no-isolation",
                    "--skip-dependency-check",
                    f"--config-setting=cmake.define.ITK_SOURCE_DIR:PATH={self.ITK_SOURCE_DIR}",
                    f"--config-setting=cmake.define.ITK_BINARY_DIR:PATH={build_path}",
                    f"--config-setting=cmake.define.ITKPythonPackage_USE_TBB:BOOL={self._use_tbb}",
                    "--config-setting=cmake.define.ITKPythonPackage_ITK_BINARY_REUSE:BOOL=ON",
                    f"--config-setting=cmake.define.ITKPythonPackage_WHEEL_NAME:STRING={wheel_name}",
                    f"--config-setting=cmake.define.Python3_EXECUTABLE:FILEPATH={self.venv_info_dict['python_executable']}",
                    "--config-setting=cmake.define.DOXYGEN_EXECUTABLE:FILEPATH="
                    + f"{self.package_env_config['DOXYGEN_EXECUTABLE']}",
                    f"--config-setting=cmake.build-type={self._build_type}",
                ]
                if self.platform_name == "darwin":
                    macosx_target = self.package_env_config.get(
                        "MACOSX_DEPLOYMENT_TARGET", ""
                    )
                    if macosx_target:
                        cmd.append(
                            f"--config-setting=cmake.define.CMAKE_OSX_DEPLOYMENT_TARGET:STRING={macosx_target}"
                        )
                    osx_arch = (
                        "arm64" if self.platform_architechture == "arm64" else "x86_64"
                    )
                    cmd.append(
                        f"--config-setting=cmake.define.CMAKE_OSX_ARCHITECTURES:STRING={osx_arch}"
                    )
                elif self.platform_name == "linux":
                    if self.platform_architechture == "x64":
                        target_triple = "x86_64-linux-gnu"
                    elif self.platform_architechture in ("aarch64", "arm64"):
                        target_triple = "aarch64-linux-gnu"
                    elif self.platform_architechture == "x86":
                        target_triple = "i686-linux-gnu"
                    else:
                        target_triple = f"{self.platform_architechture}-linux-gnu"
                    cmd.append(
                        f"--config-setting=cmake.define.CMAKE_CXX_COMPILER_TARGET:STRING={target_triple}"
                    )
                    cmd.append(
                        "--config-setting=cmake.define.CMAKE_CXX_FLAGS:STRING=-O3 -DNDEBUG"
                    )
                    cmd.append(
                        "--config-setting=cmake.define.CMAKE_C_FLAGS:STRING=-O3 -DNDEBUG"
                    )
                if self.venv_info_dict["python_include_dir"]:
                    cmd.append(
                        f"--config-setting=cmake.define.Python3_INCLUDE_DIR:PATH={self.venv_info_dict['python_include_dir']}"
                    )
                    cmd.append(
                        f"--config-setting=cmake.define.Python3_INCLUDE_DIRS:PATH={self.venv_info_dict['python_include_dir']}"
                    )
                if self.venv_info_dict["python_library"]:
                    cmd.append(
                        f"--config-setting=cmake.define.Python3_LIBRARY:FILEPATH={self.venv_info_dict['python_library']}"
                    )
                cmd += [
                    o.replace("-D", "--config-setting=cmake.define.")
                    for o in self.cmake_options
                ]
                cmd += [str(self.IPP_SOURCE_DIR)]
                echo_check_call(cmd)

            # Remove unnecessary files for building against ITK
            if self.cleanup:
                bp = Path(build_path)
                for p in bp.rglob("*"):
                    if p.is_file() and p.suffix in [".cpp", ".xml", ".obj", ".o"]:
                        try:
                            p.unlink()
                        except OSError:
                            pass
                _remove_tree(bp / "Wrapping" / "Generators" / "CastXML")

    def build_wrapped_itk(
        self,
        build_path,
    ):

        # Build ITK python
        cmd = [
            "cmake",
            "-G",
            "Ninja",
            f"-DCMAKE_MAKE_PROGRAM:FILEPATH={self.venv_info_dict['ninja_executable']}",
            f"-DCMAKE_BUILD_TYPE:STRING={self._build_type}",
            f"-DITK_SOURCE_DIR:PATH={self.ITK_SOURCE_DIR}",
            f"-DITK_BINARY_DIR:PATH={build_path}",
            "-DBUILD_TESTING:BOOL=OFF",
        ]

        cmd.extend(self.cmake_options)

        # Set cmake flags for the compiler if CC or CXX are specified
        cxx_compiler: str = self.package_env_config.get("CXX", "")
        if cxx_compiler != "":
            cmd.append(f"-DCMAKE_CXX_COMPILER:STRING={cxx_compiler}")

        c_compiler: str = self.package_env_config.get("CC", "")
        if c_compiler != "":
            cmd.append(f"-DCMAKE_C_COMPILER:STRING={c_compiler}")

        if self.package_env_config.get("USE_CCACHE", "OFF") == "ON":
            ccache_exe: Path = _which("ccache")
            cmd.append(f"-DCMAKE_C_COMPILER_LAUNCHER:FILEPATH={ccache_exe}")
            cmd.append(f"-DCMAKE_CXX_COMPILER_LAUNCHER:FILEPATH={ccache_exe}")

        # Python settings
        cmd.append("-DSKBUILD:BOOL=ON")
        cmd.append(
            f"-DPython3_EXECUTABLE:FILEPATH={self.venv_info_dict['python_executable']}"
        )
        if self.venv_info_dict["python_include_dir"]:
            cmd.append(
                f"-DPython3_INCLUDE_DIR:PATH={self.venv_info_dict['python_include_dir']}"
            )
            cmd.append(
                f"-DPython3_INCLUDE_DIRS:PATH={self.venv_info_dict['python_include_dir']}"
            )
        if self.venv_info_dict["python_library"]:
            cmd.append(
                f"-DPython3_LIBRARY:FILEPATH={self.venv_info_dict['python_library']}"
            )
            cmd.append(
                f"-DPython3_SABI_LIBRARY:FILEPATH={self.venv_info_dict['python_library']}"
            )

        # ITK wrapping options
        cmd += [
            "-DITK_WRAP_unsigned_short:BOOL=ON",
            "-DITK_WRAP_double:BOOL=ON",
            "-DITK_WRAP_complex_double:BOOL=ON",
            "-DITK_WRAP_IMAGE_DIMS:STRING=2;3;4",
            "-DWRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel",
            "-DWRAP_ITK_INSTALL_COMPONENT_PER_MODULE:BOOL=ON",
            "-DPY_SITE_PACKAGES_PATH:PATH=.",
            "-DITK_LEGACY_SILENT:BOOL=ON",
            "-DITK_WRAP_PYTHON:BOOL=ON",
            "-DITK_WRAP_DOC:BOOL=ON",
            f"-DDOXYGEN_EXECUTABLE:FILEPATH={self.package_env_config['DOXYGEN_EXECUTABLE']}",
            f"-DModule_ITKTBB:BOOL={self._use_tbb}",
            f"-DTBB_DIR:PATH={self._tbb_dir}",
            "-S",
            self.ITK_SOURCE_DIR,
            "-B",
            build_path,
        ]
        echo_check_call(cmd)
        echo_check_call([self.venv_info_dict["ninja_executable"], "-C", build_path])
