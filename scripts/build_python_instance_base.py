from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod
from subprocess import check_call as subprocess_check_call
from typing import Iterable

import shutil
import subprocess
from pathlib import Path
from os import environ, pathsep
from cmake_argument_builder import CMakeArgumentBuilder

from BuildManager import BuildManager
from wheel_builder_utils import (
    _remove_tree,
    push_env,
    _which,
    push_dir,
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
        build_dir_root,
        wheel_names: Iterable[str],
        package_env_config: dict,
        cleanup: bool,
        build_itk_tarball_cache: bool,
        cmake_options: list[str],
        windows_extra_lib_paths: list[str],
        dist_dir: Path,
        module_source_dir: Path | None = None,
        module_dependancies_root_dir: Path | None = None,
        itk_module_deps: str | None = None,
    ) -> None:
        self.build_node_cpu_count: int = os.cpu_count() or 1

        self.py_env = py_env
        self.build_dir_root = build_dir_root
        self.wheel_names = list(wheel_names)
        self.package_env_config = package_env_config
        del package_env_config

        self.cleanup = False
        self.build_itk_tarball_cache = build_itk_tarball_cache
        self.cmake_options = cmake_options
        # NEVER CLEANUP FOR DEBUGGGING cleanup
        self.windows_extra_lib_paths = windows_extra_lib_paths
        self.dist_dir = self.build_dir_root / dist_dir
        # Needed for processing remote modules and their dependancies
        self.module_source_dir: Path = (
            Path(module_source_dir) if module_source_dir else None
        )
        self.module_dependancies_root_dir: Path = (
            Path(module_dependancies_root_dir) if module_dependancies_root_dir else None
        )
        self.itk_module_deps = itk_module_deps

        self._use_tbb = "ON"
        self._build_type = "Release"
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
                "ITK_SOURCE_DIR:PATH": f"{self.package_env_config['ITK_SOURCE_DIR']}",
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
                "TBB_DIR:PATH": f'{self.package_env_config.get("TBB_DIR", None)}',
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

        # HACK
        if self.itk_module_deps:
            self._build_module_dependancies()

        python_package_build_steps: dict = {
            "01_superbuild_support_components": self.build_superbuild_support_components,
            "02_build_wrapped_itk_cplusplus": self.build_wrapped_itk_cplusplus,
            "03_build_wheels": self.build_itk_python_wheels,
            "04_post_build_fixup": self.post_build_fixup,
            "05_final_import_test": self.final_import_test,
        }
        if self.module_source_dir is not None:
            python_package_build_steps[
                f"06_build_external_module_wheel_{self.module_source_dir.name}"
            ] = self.build_external_module_python_wheel
        if self.build_itk_tarball_cache:
            python_package_build_steps[
                f"07_build_itk_tarball_cache_{self.package_env_config['OS_NAME']}_{self.package_env_config['ARCH']}"
            ] = self.build_tarball

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
            self.package_env_config["CMAKE_EXECUTABLE"],
            "-G",
            "Ninja",
        ]

        cmd += cmake_superbuild_argumets.getCMakeCommandLineArguments()

        cmd += [
            "-S",
            str(self.package_env_config["IPP_SOURCE_DIR"] / "SuperbuildSupport"),
            "-B",
            str(self.package_env_config["IPP_SUPERBUILD_BINARY_DIR"]),
        ]

        self.echo_check_call(cmd)
        self.echo_check_call(
            [
                self.venv_info_dict["ninja_executable"],
                f"-j{self.build_node_cpu_count}",
                f"-l{self.build_node_cpu_count}",
                "-C",
                str(self.package_env_config["IPP_SUPERBUILD_BINARY_DIR"]),
            ]
        )

    def fixup_wheels(self, lib_paths: str = ""):
        # TBB library fix-up (applies to itk_core wheel)
        tbb_wheel = "itk_core"
        for wheel in (self.build_dir_root / "dist").glob(f"{tbb_wheel}*.whl"):
            self.fixup_wheel(str(wheel), lib_paths)

    def final_wheel_import_test(self, installed_dist_dir: Path):
        self.echo_check_call(
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
        self.echo_check_call(
            [self.venv_info_dict["python_executable"], "-c", "import itk;"]
        )
        self.echo_check_call(
            [
                self.venv_info_dict["python_executable"],
                "-c",
                "import itk; image = itk.Image[itk.UC, 2].New()",
            ]
        )
        self.echo_check_call(
            [
                self.venv_info_dict["python_executable"],
                "-c",
                "import itkConfig; itkConfig.LazyLoading=False; import itk;",
            ]
        )
        # Full doc tests
        self.echo_check_call(
            [
                self.venv_info_dict["python_executable"],
                str(
                    self.package_env_config["IPP_SOURCE_DIR"]
                    / "docs"
                    / "code"
                    / "test.py"
                ),
            ]
        )
        print("Documentation tests passed.")

    def _pip_uninstall_itk_wildcard(self, pip_executable: str | Path):
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
            self.echo_check_call([pip_executable, "uninstall", "-y", *packages])

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
    def clone(self):
        # each subclass must implement this method that is used to clone itself
        pass

    @abstractmethod
    def venv_paths(self):
        pass

    @abstractmethod
    def fixup_wheel(self, filepath, lib_paths: str = ""):  # pragma: no cover - abstract
        pass

    @abstractmethod
    def build_tarball(self):
        pass

    @abstractmethod
    def post_build_cleanup(self):
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

    def build_external_module_python_wheel(self):
        self.module_source_dir = Path(self.module_source_dir)
        out_dir = self.module_source_dir / "dist"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Ensure venv tools are first in PATH
        with push_env(
            PATH=f"{self.venv_info_dict['venv_bin_path']}{pathsep}{environ['PATH']}"
        ):
            py_exe = str(self.venv_info_dict["python_executable"])  # Python3_EXECUTABLE

            # Compute Python include directory (Python3_INCLUDE_DIR)
            py_include = self.venv_info_dict.get("python_include_dir", "")
            if not py_include:
                try:
                    py_include = (
                        subprocess.check_output(
                            [
                                py_exe,
                                "-c",
                                "import sysconfig; print(sysconfig.get_paths()['include'])",
                            ],
                            text=True,
                        ).strip()
                        or ""
                    )
                except Exception:
                    py_include = ""

            # Determine platform-specific settings (macOS)
            config_settings: dict[str, str] = {}

            # ITK build path for external modules: prefer configured ITK binary dir
            itk_build_path = self.cmake_itk_source_build_configurations.get(
                "ITK_BINARY_DIR:PATH",
                "",
            )

            # wheel.py-api for stable ABI when Python >= 3.11
            try:
                py_minor = int(
                    subprocess.check_output(
                        [py_exe, "-c", "import sys; print(sys.version_info.minor)"],
                        text=True,
                    ).strip()
                )
            except Exception:
                py_minor = 0
            wheel_py_api = f"cp3{py_minor}" if py_minor >= 11 else ""

            # Base build command
            cmd = [
                py_exe,
                "-m",
                "build",
                "--verbose",
                "--wheel",
                "--outdir",
                str(out_dir),
                "--no-isolation",
                "--skip-dependency-check",
                f"--config-setting=cmake.build-type={self._build_type}",
            ]

            # Collect scikit-build CMake definitions
            defs = CMakeArgumentBuilder()
            defs.update(self.cmake_compiler_configurations.items())
            # Propagate macOS specific defines if any were set above
            for k, v in config_settings.items():
                defs.set(k, v)

            # Required defines for external module build
            if itk_build_path:
                defs.set("ITK_DIR:PATH", str(itk_build_path))
            defs.set("CMAKE_INSTALL_LIBDIR:STRING", "lib")
            defs.set("WRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING", "PythonWheel")
            defs.set("PY_SITE_PACKAGES_PATH:PATH", ".")
            defs.set("BUILD_TESTING:BOOL", "OFF")
            defs.set("Python3_EXECUTABLE:FILEPATH", py_exe)
            if py_include:
                defs.set("Python3_INCLUDE_DIR:PATH", py_include)

            # Allow command-line cmake -D overrides to win last
            if self.cmake_cmdline_definitions:
                defs.update(self.cmake_cmdline_definitions.items())

            # Append all cmake.define entries to the build cmd
            cmd += defs.getPythonBuildCommandLineArguments()

            # Stable ABI setting if applicable
            if wheel_py_api:
                cmd += [f"--config-setting=wheel.py-api={wheel_py_api}"]

            # Module source directory to build
            cmd += [self.module_source_dir]

            self.echo_check_call(cmd)

            # Post-process produced wheels (e.g., delocate on macOS x86_64)
            for wheel in out_dir.glob("*.whl"):
                self.fixup_wheel(str(wheel))

    def build_itk_python_wheels(self):
        with push_env(
            PATH=f"{self.venv_info_dict['venv_bin_path']}{pathsep}{environ['PATH']}"
        ):
            pyproject_configure = (
                self.package_env_config["SCRIPT_DIR"] / "pyproject_configure.py"
            )

            # Build wheels
            for wheel_name in self.wheel_names:
                print("#")
                print(f"# Build ITK wheel {wheel_name} from {self.wheel_names}")
                print("#")
                # Configure pyproject.toml
                wheel_configbuild_dir_root: Path = (
                    self.build_dir_root
                    / f"wheelbuilds"
                    / f"{wheel_name}_{self.get_pixi_environment_name()}"
                )
                wheel_configbuild_dir_root.mkdir(parents=True, exist_ok=True)
                self.echo_check_call(
                    [
                        str(self.venv_info_dict["python_executable"]),
                        pyproject_configure,
                        "--env-file",
                        self.package_env_config.get("PACKAGE_ENV_FILE"),
                        "--output-dir",
                        wheel_configbuild_dir_root,
                        "--build-dir-root",
                        self.build_dir_root,
                        wheel_name,
                    ]
                )

                # Generate wheel using
                cmd = [
                    str(self.venv_info_dict["python_executable"]),
                    "-m",
                    "build",
                    "--verbose",
                    "--wheel",
                    "--outdir",
                    str(self.build_dir_root / "dist"),
                    "--no-isolation",
                    "--skip-dependency-check",
                    f"--config-setting=cmake.build-type={self._build_type}",
                    f"--config-setting=cmake.source-dir={self.package_env_config['IPP_SOURCE_DIR'] / 'BuildWheelsSupport'}",
                    f"--config-setting=build-dir={wheel_configbuild_dir_root/'build'}",
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
                # The location of the generated pyproject.toml file
                cmd += [wheel_configbuild_dir_root]
                self.echo_check_call(cmd)

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
            self.package_env_config["CMAKE_EXECUTABLE"],
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
            self.package_env_config["ITK_SOURCE_DIR"],
            "-B",
            self.cmake_itk_source_build_configurations["ITK_BINARY_DIR:PATH"],
        ]
        self.echo_check_call(cmd)
        self.echo_check_call(
            [
                self.venv_info_dict["ninja_executable"],
                f"-j{self.build_node_cpu_count}",
                f"-l{self.build_node_cpu_count}",
                "-C",
                self.cmake_itk_source_build_configurations["ITK_BINARY_DIR:PATH"],
            ]
        )
        print("# FINISHED-Build ITK C++")

    def _build_module_dependancies(self):
        """
        Build prerequisite ITK external modules, mirroring the behavior of
        the platform shell scripts that use the ITK_MODULE_PREQ environment.

        Accepted formats in self.itk_module_deps (colon-delimited):
          - "MeshToPolyData@v0.10.0"  -> defaults to
            "InsightSoftwareConsortium/ITKMeshToPolyData@v0.10.0"
          - "InsightSoftwareConsortium/ITKMeshToPolyData@v0.10.0"

        For each dependency, clone the repository, checkout the given tag,
        invoke the platform download-cache-and-build script, then copy
        headers and wrapping input files into the current module tree
        (include/ and wrapping/), similar to the bash implementations.
        """

        if len(self.itk_module_deps) == 0:
            return
        print(f"Building module dependancies: {self.itk_module_deps}")
        self.module_dependancies_root_dir.mkdir(parents=True, exist_ok=True)

        # Normalize entries to "Org/Repo@Tag"
        def _normalize(entry: str) -> str:
            entry = entry.strip()
            if not entry:
                return ""
            if "/" in entry:
                # Already Org/Repo@Tag
                return entry
            # Short form: Name@Tag -> InsightSoftwareConsortium/ITKName@Tag
            try:
                name, tag = entry.split("@", 1)
            except ValueError:
                # If no tag, pass-through (unexpected)
                return entry
            repo = f"ITK{name}"
            return f"InsightSoftwareConsortium/{repo}@{tag}"

        # Ensure working directories exist
        module_root = Path(self.module_source_dir).resolve()
        include_dir = module_root / "include"
        wrapping_dir = module_root / "wrapping"
        include_dir.mkdir(parents=True, exist_ok=True)
        wrapping_dir.mkdir(parents=True, exist_ok=True)

        dep_entries = [e for e in (s for s in self.itk_module_deps.split(":")) if e]
        normalized = [_normalize(e) for e in dep_entries]
        normalized = [e for e in normalized if e]

        # Build each dependency in order
        for current_entry, entry in enumerate(normalized):
            if len(entry) == 0:
                continue
            print(f"Get dependency module information for {entry}")
            org = entry.split("/", 1)[0]
            repo_tag = entry.split("/", 1)[1]
            repo = repo_tag.split("@", 1)[0]
            tag = repo_tag.split("@", 1)[1] if "@" in repo_tag else ""

            upstream = f"https://github.com/{org}/{repo}.git"
            dependant_module_clone_dir = (
                self.module_dependancies_root_dir / repo
                if self.module_dependancies_root_dir
                else module_root / repo
            )
            if not dependant_module_clone_dir.exists():
                self.echo_check_call(
                    ["git", "clone", upstream, dependant_module_clone_dir]
                )

            # Checkout requested tag
            with push_env():
                self.echo_check_call(
                    [
                        "git",
                        "-C",
                        dependant_module_clone_dir,
                        "fetch",
                        "--all",
                        "--tags",
                    ]
                )
                if tag:
                    self.echo_check_call(
                        ["git", "-C", dependant_module_clone_dir, "checkout", tag]
                    )

                if (dependant_module_clone_dir / "setup.py").exists():
                    print(
                        f"Old sci-kit-build with setup.py is no longer supported for {dependant_module_clone_dir} at {tag}"
                    )
                    sys.exit(1)

                # Clonen the current build environment, and modify for current module
                dependannt_module_build_setup = self.clone()
                dependannt_module_build_setup.module_source_dir = Path(
                    dependant_module_clone_dir
                )
                dependannt_module_build_setup.itk_module_deps = (
                    None  # Prevent recursion
                )
                dependannt_module_build_setup.run()

            # After building dependency, copy includes and wrapping files
            # 1) Top-level include/* -> include/
            dep_include = dependant_module_clone_dir / "include"
            if dep_include.exists():
                for src in dep_include.rglob("*"):
                    if src.is_file():
                        rel = src.relative_to(dep_include)
                        dst = include_dir / rel
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            shutil.copy2(src, dst)
                        except Exception:
                            pass

            # 2) Any */build/*/include/* -> include/
            for sub in dependant_module_clone_dir.rglob("*build*/**/include"):
                if sub.is_dir():
                    for src in sub.rglob("*"):
                        if src.is_file():
                            rel = src.relative_to(sub)
                            dst = include_dir / rel
                            dst.parent.mkdir(parents=True, exist_ok=True)
                            try:
                                shutil.copy2(src, dst)
                            except Exception:
                                pass

            # 3) Wrapping templates (*.in, *.init) -> wrapping/
            dep_wrapping = dependant_module_clone_dir / "wrapping"
            if dep_wrapping.exists():
                for pattern in ("*.in", "*.init"):
                    for src in dep_wrapping.rglob(pattern):
                        if src.is_file():
                            dst = wrapping_dir / src.name
                            try:
                                shutil.copy2(src, dst)
                            except Exception:
                                pass

    def create_posix_tarball(self):
        """Create a compressed tarball of the ITK Python build tree.

        Mirrors the historical scripts/*-build-tarball.sh behavior:
        - zstd compress with options (-10 -T6 --long=31)
        """
        arch_postfix = f"-{self.package_env_config['ARCH']}"
        tar_name = (
            f"ITKPythonBuilds-{self.get_pixi_environment_name()}-{arch_postfix}.tar"
        )
        itk_packaging_reference_dir = self.build_dir_root.parent

        tar_path: Path = itk_packaging_reference_dir / tar_name
        zst_path: Path = itk_packaging_reference_dir / f"{tar_name}.zst"

        itk_resources_build_dir: Path = self.build_dir_root
        tarball_include_paths = [
            itk_resources_build_dir.relative_to(itk_packaging_reference_dir),
            self.package_env_config["IPP_SOURCE_DIR"].relative_to(
                itk_packaging_reference_dir
            ),
        ]

        # Create tarball of
        self.echo_check_call(
            [
                "tar",
                "-C",
                itk_packaging_reference_dir,
                "-cf",
                str(tar_path),
                '--exclude="*.o"',  # Do not include object files
                '--exclude="*/__pycache__/"',  # Do not include __pycache__
                '--exclude="*/.git/"',
                '--exclude="*/.idea/"',
                '--exclude="*/.pixi/"',
                '--exclude="*/CastXML/"',
                '--exclude="*/castxml_inputs/"',
                '--exclude="*/Wrapping/Modules/"',
                *tarball_include_paths,
            ]
        )

        # Compress with zstd
        self.echo_check_call(
            [
                "zstd",
                "-f",
                "-10",
                "-T6",
                "--long=31",
                str(tar_path),
                "-o",
                str(zst_path),
            ]
        )

    @abstractmethod
    def get_pixi_environment_name(self):
        pass

    def echo_check_call(
        self,
        cmd: list[str | Path] | tuple[str | Path] | str | Path,
        **kwargs: dict,
    ) -> int:
        """Print the command then run subprocess.check_call.

        Parameters
        ----------
        cmd :
            Command to execute, same as subprocess.check_call.
        **kwargs :
            Additional keyword arguments forwarded to subprocess.check_call.
        """

        pixi_environment: str = self.get_pixi_environment_name()
        if pixi_environment != "macos":
            print(f"$ pixi run {pixi_environment}")
        pixi_run_preamble: list[str] = []
        env = {"PIXI_HOME": str(self.build_dir_root / ".pixi")}
        if self.package_env_config.get("CXX", None) is not None:
            env["CXX"] = str(self.package_env_config["CXX"])
        if self.package_env_config.get("CC", None) is not None:
            env["CC"] = str(self.package_env_config["CC"])
        if pixi_environment:
            pixi_run_preamble = [
                str(self.build_dir_root / "build" / ".pixi" / "bin" / "pixi"),
                "run",
                "-e",
                pixi_environment,
            ]

            # convert all items to strings (i.e. Path() to str)
        cmd = pixi_run_preamble + [str(c) for c in cmd]
        # Prepare a friendly command-line string for display
        try:
            if isinstance(cmd, (list, tuple)):
                display_cmd = " ".join(cmd)
            else:
                display_cmd = str(cmd)
        except Exception as e:
            display_cmd = str(cmd)
        print(f">>Start Running: {display_cmd} in {Path.cwd()}")
        print("^" * 60)
        print(cmd)
        print("^" * 60)
        print(kwargs)
        print("^" * 60)
        try:
            cmd_return_status: int = subprocess_check_call(
                cmd, env=env, cwd=self.package_env_config["IPP_SOURCE_DIR"], **kwargs
            )
        except subprocess.CalledProcessError as e:
            print(f"Command Failed: {e}")
            raise e
        print("^" * 60)
        print(f"<<Finished Running: cmd_return_status={cmd_return_status}")
        return cmd_return_status
