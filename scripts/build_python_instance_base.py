from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

import shutil
import subprocess
from pathlib import Path
from os import environ, pathsep
from cmake_argument_builder import CMakeArgumentBuilder

from BuildManager import BuildManager
from wheel_builder_utils import (
    _remove_tree,
    echo_check_call,
    push_env,
    _which,
)


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
        self.cleanup = False
        # NEVER CLEANUP FOR DEBUGGGING cleanup
        self.windows_extra_lib_paths = windows_extra_lib_paths
        self.dist_dir = dist_dir
        self._cmake_executable = None
        self._doxygen_executable = None
        self._use_tbb = "ON"
        self._tbb_dir = None
        self._build_type = "Release"
        self.env_file = self.IPP_SOURCE_DIR / "build" / "package.env"
        # Unified place to collect cmake -D definitions for this instance
        self.cmake_cmdline_definitions: CMakeArgumentBuilder = CMakeArgumentBuilder()
        # Seed from legacy cmake_options if provided as ['-D<KEY>=<VALUE>', ...]
        if cmake_options:
            for opt in cmake_options:
                if not opt.startswith("-D"):
                    continue
                # Strip leading -D, split on first '=' into key and value
                try:
                    key, value = opt[2:].split("=", 1)
                except ValueError:
                    # Malformed option; skip to avoid breaking build
                    continue
                # Preserve value verbatim (may contain quotes)
                self.cmake_cmdline_definitions.set(key, value)
        self.cmake_compiler_configurations: CMakeArgumentBuilder = (
            CMakeArgumentBuilder()
        )
        self.cmake_compiler_configurations.update(
            {
                "CMAKE_BUILD_TYPE:STRING": f"{self._build_type}",
                "CMAKE_CXX_FLAGS:STRING": "-O3 -DNDEBUG",
                "CMAKE_C_FLAGS:STRING": "-O3 -DNDEBUG",
            }
        )
        # Set cmake flags for the compiler if CC or CXX are specified
        cxx_compiler: str = self.package_env_config.get("CXX", "")
        if cxx_compiler != "":
            self.cmake_compiler_configurations.set(
                "CMAKE_CXX_COMPILER:STRING", cxx_compiler
            )

        c_compiler: str = self.package_env_config.get("CC", "")
        if c_compiler != "":
            self.cmake_compiler_configurations.set(
                "CMAKE_C_COMPILER:STRING", c_compiler
            )

        if self.package_env_config.get("USE_CCACHE", "OFF") == "ON":
            ccache_exe: Path = _which("ccache")
            self.cmake_compiler_configurations.set(
                "CMAKE_C_COMPILER_LAUNCHER:FILEPATH", f"{ccache_exe}"
            )
            self.cmake_compiler_configurations.set(
                "CMAKE_CXX_COMPILER_LAUNCHER:FILEPATH", f"{ccache_exe}"
            )

        self.cmake_itk_source_build_configurations: CMakeArgumentBuilder = (
            CMakeArgumentBuilder()
        )
        self.cmake_itk_source_build_configurations.update(
            # ITK wrapping options
            {
                "ITK_SOURCE_DIR:PATH": f"{self.ITK_SOURCE_DIR}",
                "BUILD_TESTING:BOOL": "OFF",
                "ITK_WRAP_unsigned_short:BOOL": "ON",
                "ITK_WRAP_double:BOOL": "ON",
                "ITK_WRAP_complex_double:BOOL": "ON",
                "ITK_WRAP_IMAGE_DIMS:STRING": "2;3;4",
                "WRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING": "PythonWheel",
                "WRAP_ITK_INSTALL_COMPONENT_PER_MODULE:BOOL": "ON",
                "PY_SITE_PACKAGES_PATH:PATH": ".",
                "ITK_LEGACY_SILENT:BOOL": "ON",
                "ITK_WRAP_PYTHON:BOOL": "ON",
                "ITK_WRAP_DOC:BOOL": "ON",
                "DOXYGEN_EXECUTABLE:FILEPATH": f"{self.package_env_config['DOXYGEN_EXECUTABLE']}",
                "Module_ITKTBB:BOOL": f"{self._use_tbb}",
                "TBB_DIR:PATH": f"{self._tbb_dir}",
                # Python settings
                "SKBUILD:BOOL": "ON",
            }
        )

        self.venv_info_dict = {
            # Filled in for each platform and each pyenvs
            # "python_executable": None,
            # "python_include_dir": None,
            # "python_library": None,
            # "pip_executable": None,
            # "ninja_executable": None,
            # "venv_bin_path": None,
            # "venv_base_dir": None,
        }

    def update_venv_itk_build_configurations(self) -> None:
        # TODO: Make this better later currently needs to be called after each platforms update of venv_info_dict
        self.cmake_itk_source_build_configurations.set(
            "Python3_EXECUTABLE:FILEPATH",
            f"{self.venv_info_dict['python_executable']}",
        )
        if self.venv_info_dict["python_include_dir"]:
            self.cmake_itk_source_build_configurations.set(
                "Python3_INCLUDE_DIR:PATH",
                f"{self.venv_info_dict['python_include_dir']}",
            )
            self.cmake_itk_source_build_configurations.set(
                "Python3_INCLUDE_DIRS:PATH",
                f"{self.venv_info_dict['python_include_dir']}",
            )
        if self.venv_info_dict["python_library"]:
            self.cmake_itk_source_build_configurations.set(
                "Python3_LIBRARY:FILEPATH",
                f"{self.venv_info_dict['python_library']}",
            )
            self.cmake_itk_source_build_configurations.set(
                "Python3_SABI_LIBRARY:FILEPATH",
                f"{self.venv_info_dict['python_library']}",
            )

    def run(self) -> None:
        """Run the full build flow for this Python instance."""
        # Use BuildManager to persist and resume build steps
        self.prepare_build_env()
        python_package_build_steps: dict = {
            "01_superbuild_support_components": self.build_superbuild_support_components,
            "02_build_wrapped_itk_cplusplus": self.build_wrapped_itk_cplusplus,
            "03_build_wheels": self.build_itk_python_wheels,
            "04_post_build_fixup": self.post_build_fixup,
            "05_final_import_test": self.final_import_test,
        }
        self.dist_dir.mkdir(parents=True, exist_ok=True)
        build_report_fn: Path = self.dist_dir / f"build_log_{self.py_env}.json"
        build_manager: BuildManager = BuildManager(
            build_report_fn, list(python_package_build_steps.keys())
        )
        build_manager.save()
        for build_step_name, build_step_func in python_package_build_steps.items():
            print("=" * 80)
            print(f"Running build step: {build_step_name}")
            build_manager.run_step(build_step_name, build_step_func)
            build_manager.save()
            print(f"Build step {build_step_name} completed.")
            print("=" * 80)

    def build_superbuild_support_components(self):
        # -----------------------------------------------------------------------
        # Build required components (optional local ITK source, TBB builds) used to populate the archive cache

        # Build up definitions using the builder
        cmake_superbuild_argumets = CMakeArgumentBuilder()
        if self.cmake_compiler_configurations:
            cmake_superbuild_argumets.update(self.cmake_compiler_configurations.items())
        # Add superbuild-specific flags
        cmake_superbuild_argumets.update(
            {
                "ITKPythonPackage_BUILD_PYTHON:BOOL": "OFF",
                "ITKPythonPackage_USE_TBB:BOOL": f"{self._use_tbb}",
                "ITK_SOURCE_DIR:PATH": f"{self.package_env_config['ITK_SOURCE_DIR']}",
                "ITK_GIT_TAG:STRING": f"{self.package_env_config['ITK_GIT_TAG']}",
            }
        )
        # Start from any platform/user-provided defaults
        if self.cmake_cmdline_definitions:
            cmake_superbuild_argumets.update(self.cmake_cmdline_definitions.items())

        cmd = [
            self._cmake_executable,
            "-G",
            "Ninja",
        ]

        cmd += cmake_superbuild_argumets.getCMakeCommandLineArguments()

        cmd += [
            "-S",
            str(self.IPP_SOURCE_DIR / "SuperbuildSupport"),
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
    def _pip_uninstall_itk_wildcard(pip_executable: str | Path):
        """Uninstall all installed packages whose name starts with 'itk'.

        pip does not support shell-style wildcards directly for uninstall, so we:
          - run 'pip list --format=freeze'
          - collect package names whose normalized name starts with 'itk'
          - call 'pip uninstall -y <names...>' if any are found
        """
        pip_executable = str(pip_executable)
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

    def build_itk_python_wheels(self):
        with push_env(
            PATH=f"{self.venv_info_dict['venv_bin_path']}{pathsep}{environ['PATH']}"
        ):
            pyproject_configure = self.SCRIPT_DIR / "pyproject_configure.py"

            # Build wheels
            for wheel_name in self.wheel_names:
                print("#")
                print(f"# Build ITK wheel {wheel_name} from {self.wheel_names}")
                print("#")
                # Configure pyproject.toml
                echo_check_call(
                    [
                        str(self.venv_info_dict["python_executable"]),
                        pyproject_configure,
                        "--env-file",
                        self.env_file,
                        "--output-dir",
                        self.IPP_SOURCE_DIR / "BuildWheelsSupport",
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
                    f"--config-setting=cmake.build-type={self._build_type}",
                ]
                # Build scikit-build defines via builder
                scikitbuild_cmdline_args = CMakeArgumentBuilder()
                scikitbuild_cmdline_args.update(
                    self.cmake_compiler_configurations.items()
                )
                scikitbuild_cmdline_args.update(
                    self.cmake_itk_source_build_configurations.items()
                )
                scikitbuild_cmdline_args.update(
                    {
                        "ITKPythonPackage_USE_TBB:BOOL": f"{self._use_tbb}",
                        "ITKPythonPackage_ITK_BINARY_REUSE:BOOL": "ON",
                        "ITKPythonPackage_WHEEL_NAME:STRING": f"{wheel_name}",
                        "DOXYGEN_EXECUTABLE:FILEPATH": f"{self.package_env_config['DOXYGEN_EXECUTABLE']}",
                    }
                )

                if (
                    self.cmake_cmdline_definitions
                ):  # Do last to override with command line items
                    scikitbuild_cmdline_args.update(
                        self.cmake_cmdline_definitions.items()
                    )
                    # Append all cmake.define entries
                cmd += scikitbuild_cmdline_args.getPythonBuildCommandLineArguments()
                cmd += [self.IPP_SOURCE_DIR / "BuildWheelsSupport"]
                echo_check_call(cmd)

            # Remove unnecessary files for building against ITK
            if self.cleanup:
                bp = Path(
                    self.cmake_itk_source_build_configurations["ITK_BINARY_DIR:PATH"]
                )
                for p in bp.rglob("*"):
                    if p.is_file() and p.suffix in [".cpp", ".xml", ".obj", ".o"]:
                        try:
                            p.unlink()
                        except OSError:
                            pass
                _remove_tree(bp / "Wrapping" / "Generators" / "CastXML")

    def build_wrapped_itk_cplusplus(self):
        # Clean up previous invocations
        if (
            self.cleanup
            and Path(
                self.cmake_itk_source_build_configurations["ITK_BINARY_DIR:PATH"]
            ).exists()
        ):
            _remove_tree(
                Path(self.cmake_itk_source_build_configurations["ITK_BINARY_DIR:PATH"])
            )

        print("#")
        print("# START-Build ITK C++")
        print("#")

        # Build ITK python
        cmd = [
            "cmake",
            "-G",
            "Ninja",
        ]
        # Collect all -D definitions via builder
        defs = CMakeArgumentBuilder()
        defs.update(self.cmake_compiler_configurations.items())
        defs.update(self.cmake_itk_source_build_configurations.items())
        # NOTE Do cmake_cmdline_definitions last so they override internal defaults
        defs.update(self.cmake_cmdline_definitions.items())
        cmd += defs.getCMakeCommandLineArguments()
        cmd += [
            "-S",
            self.ITK_SOURCE_DIR,
            "-B",
            self.cmake_itk_source_build_configurations["ITK_BINARY_DIR:PATH"],
        ]
        echo_check_call(cmd)
        echo_check_call(
            [
                self.venv_info_dict["ninja_executable"],
                "-C",
                self.cmake_itk_source_build_configurations["ITK_BINARY_DIR:PATH"],
            ]
        )
        print("# FINISHED-Build ITK C++")
