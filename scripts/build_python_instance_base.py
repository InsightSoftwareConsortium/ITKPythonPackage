import copy
import os
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Callable
from os import environ
from pathlib import Path

from BuildManager import BuildManager
from cmake_argument_builder import CMakeArgumentBuilder
from pyproject_configure import configure_one_pyproject_file
from wheel_builder_utils import (
    _remove_tree,
    _which,
    get_default_platform_build,
    run_commandLine_subprocess,
)


class BuildPythonInstanceBase(ABC):
    """Abstract base class to build wheels for a single Python environment.

    Concrete subclasses implement platform-specific details (environment
    setup, wheel fixup, tarball creation) while this class provides the
    shared build orchestration, CMake configuration, and wheel-building
    logic.

    Parameters
    ----------
    platform_env : str
        Platform/environment identifier (e.g. ``'manylinux228-py311'``).
    build_dir_root : Path
        Root directory for all build artifacts.
    package_env_config : dict
        Mutable configuration dictionary populated throughout the build.
    cleanup : bool
        Whether to remove intermediate build artifacts.
    build_itk_tarball_cache : bool
        Whether to create a reusable tarball of the ITK build tree.
    cmake_options : list[str]
        Extra ``-D`` options forwarded to CMake.
    windows_extra_lib_paths : list[str]
        Additional library paths for Windows wheel fixup (delvewheel).
    dist_dir : Path
        Output directory for built wheel files.
    module_source_dir : Path, optional
        Path to an external ITK remote module to build.
    module_dependencies_root_dir : Path, optional
        Directory where remote module dependencies are cloned.
    itk_module_deps : str, optional
        Colon-delimited dependency specifications for remote modules.
    skip_itk_build : bool, optional
        Skip the ITK C++ build step.
    skip_itk_wheel_build : bool, optional
        Skip the ITK wheel build step.
    """

    def __init__(
        self,
        *,
        platform_env,
        build_dir_root,
        package_env_config: dict,
        cleanup: bool,
        build_itk_tarball_cache: bool,
        cmake_options: list[str],
        windows_extra_lib_paths: list[str],
        dist_dir: Path,
        module_source_dir: Path | None = None,
        module_dependencies_root_dir: Path | None = None,
        itk_module_deps: str | None = None,
        skip_itk_build: bool | None = None,
        skip_itk_wheel_build: bool | None = None,
    ) -> None:
        self.build_node_cpu_count: int = os.cpu_count() or 1
        self.platform_env = platform_env
        self.ipp_dir = Path(__file__).parent.parent

        self.build_dir_root = build_dir_root
        self.cmake_itk_source_build_configurations: CMakeArgumentBuilder = (
            CMakeArgumentBuilder()
        )
        self.cmake_compiler_configurations: CMakeArgumentBuilder = (
            CMakeArgumentBuilder()
        )
        # TODO: Partial refactoring cleanup later
        package_env_config["IPP_SOURCE_DIR"] = self.ipp_dir
        IPP_BuildWheelsSupport_DIR: Path = self.ipp_dir / "BuildWheelsSupport"
        package_env_config["IPP_BuildWheelsSupport_DIR"] = IPP_BuildWheelsSupport_DIR

        self.package_env_config = package_env_config

        # declare this dict before self.prepare_build_env() or dict will be empty in later functions
        self.venv_info_dict = {
            # Filled in for each platform and each pyenvs
            # "python_executable": None,
            # "python_include_dir": None,
            # "python_library": None,
            # "venv_bin_path": None,
            # "venv_base_dir": None,
        }

        with open(
            IPP_BuildWheelsSupport_DIR / "WHEEL_NAMES.txt",
            encoding="utf-8",
        ) as content:
            self.wheel_names = [
                wheel_name.strip() for wheel_name in content.readlines()
            ]
        del package_env_config

        self.cleanup = cleanup
        self.build_itk_tarball_cache = build_itk_tarball_cache
        self.cmake_options = cmake_options
        self.windows_extra_lib_paths = windows_extra_lib_paths
        self.dist_dir = dist_dir
        # Needed for processing remote modules and their dependencies
        self.module_source_dir: Path = (
            Path(module_source_dir) if module_source_dir else None
        )
        self.module_dependencies_root_dir: Path = (
            Path(module_dependencies_root_dir) if module_dependencies_root_dir else None
        )
        self.itk_module_deps = itk_module_deps
        self.skip_itk_build = skip_itk_build
        self.skip_itk_wheel_build = skip_itk_wheel_build
        self.prepare_build_env()

        self.package_env_config["BUILD_TYPE"] = "Release"
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

        self.cmake_compiler_configurations.update(
            {
                "CMAKE_BUILD_TYPE:STRING": self.package_env_config["BUILD_TYPE"],
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
                "Module_ITKTBB:BOOL": self.package_env_config["USE_TBB"],
                "TBB_DIR:PATH": self.package_env_config["TBB_DIR"],
                # Python settings
                "SKBUILD:BOOL": "ON",
            }
        )

    def update_venv_itk_build_configurations(self) -> None:
        """Set ``Python3_ROOT_DIR`` in ITK build configurations from venv info."""
        # Python3_EXECUTABLE, Python3_INCLUDE_DIR, and Python3_LIBRARY are validated
        # and resolved by find_package(Python3) in cmake/ITKPythonPackage_SuperBuild.cmake
        # when not already defined. Python3_ROOT_DIR is set here to guide that search.
        self.cmake_itk_source_build_configurations.set(
            "Python3_ROOT_DIR:PATH", f"{self.venv_info_dict['python_root_dir']}"
        )

    def run(self) -> None:
        """Run the full build flow for this Python instance."""
        # Use BuildManager to persist and resume build steps

        # HACK
        if self.itk_module_deps:
            self._build_module_dependencies()

        python_package_build_steps: OrderedDict[str, Callable] = OrderedDict(
            {
                "01_superbuild_support_components": self.build_superbuild_support_components,
                "02_build_wrapped_itk_cplusplus": self.build_wrapped_itk_cplusplus,
                "03_build_wheels": self.build_itk_python_wheels,
                "04_post_build_fixup": self.post_build_fixup,
                "05_final_import_test": self.final_import_test,
            }
        )

        if self.skip_itk_build:
            # Skip these steps if we are in the CI environment
            python_package_build_steps = OrderedDict(
                (
                    ("02_build_wrapped_itk_cplusplus_skipped", (lambda: None))
                    if k == "02_build_wrapped_itk_cplusplus"
                    else (k, v)
                )
                for k, v in python_package_build_steps.items()
            )
        if self.skip_itk_wheel_build:
            python_package_build_steps = OrderedDict(
                (
                    ("03_build_wheels_skipped", (lambda: None))
                    if k == "03_build_wheels"
                    else (k, v)
                )
                for k, v in python_package_build_steps.items()
            )

        if self.module_source_dir is not None:
            python_package_build_steps[
                f"06_build_external_module_wheel_{self.module_source_dir.name}"
            ] = self.build_external_module_python_wheel
        else:
            python_package_build_steps["06_build_external_module_wheel_skipped"] = (
                lambda: None
            )
        if self.build_itk_tarball_cache:
            python_package_build_steps[
                f"07_build_itk_tarball_cache_{self.package_env_config['OS_NAME']}_{self.package_env_config['ARCH']}"
            ] = self.build_tarball

        self.dist_dir.mkdir(parents=True, exist_ok=True)
        build_report_fn: Path = self.dist_dir / f"build_log_{self.platform_env}.json"
        build_manager: BuildManager = BuildManager(
            build_report_fn, list(python_package_build_steps.keys())
        )
        build_manager.save()
        for build_step_name, build_step_func in python_package_build_steps.items():
            print("=" * 80)
            print(
                f"Running build step: {build_step_name}:  recording status in {build_report_fn}"
            )
            # always force_rerun of the tarball step if requested
            build_manager.run_step(
                build_step_name,
                build_step_func,
                force_rerun=("tarball_cache" in build_step_name),
            )
            build_manager.save()
            print(
                f"Build step {build_step_name} completed.  Edit {build_report_fn} to rerun step."
            )
            print("=" * 80)

    def build_superbuild_support_components(self):
        """Configure and build the superbuild support components (ITK source, TBB)."""
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
                "ITKPythonPackage_USE_TBB:BOOL": self.package_env_config["USE_TBB"],
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
                self.package_env_config["CMAKE_EXECUTABLE"],
                "--build",
                # "--load-average",
                # str(self.build_node_cpu_count),
                # "--parallel",
                # str(self.build_node_cpu_count),
                str(self.package_env_config["IPP_SUPERBUILD_BINARY_DIR"]),
            ],
        )

    def fixup_wheels(self, lib_paths: str = ""):
        """Apply platform-specific fixups to ``itk_core`` wheels for TBB linkage."""
        # TBB library fix-up (applies to itk_core wheel)
        tbb_wheel = "itk_core"
        for wheel in (self.build_dir_root / "dist").glob(f"{tbb_wheel}*.whl"):
            self.fixup_wheel(str(wheel), lib_paths)

    def final_wheel_import_test(self, installed_dist_dir: Path):
        """Install and smoke-test all ITK wheels from *installed_dist_dir*.

        Parameters
        ----------
        installed_dist_dir : Path
            Directory containing the built ``.whl`` files to install and
            verify.
        """
        exit_status = self.echo_check_call(
            [
                self.package_env_config["PYTHON_EXECUTABLE"],
                "-m",
                "pip",
                "install",
                "itk",
                "--no-cache-dir",
                "--no-index",
                "-f",
                str(installed_dist_dir),
            ]
        )
        if exit_status == 0:
            print("Wheels successfully installed.")
        else:
            print(f"Failed to install wheels: {exit_status}")
        # Basic imports
        self.echo_check_call(
            [self.package_env_config["PYTHON_EXECUTABLE"], "-c", "import itk;"]
        )
        self.echo_check_call(
            [
                self.package_env_config["PYTHON_EXECUTABLE"],
                "-c",
                "import itk; image = itk.Image[itk.UC, 2].New()",
            ]
        )
        self.echo_check_call(
            [
                self.package_env_config["PYTHON_EXECUTABLE"],
                "-c",
                "import itkConfig; itkConfig.LazyLoading=False; import itk;",
            ]
        )
        # Full doc tests
        self.echo_check_call(
            [
                self.package_env_config["PYTHON_EXECUTABLE"],
                str(
                    self.package_env_config["IPP_SOURCE_DIR"]
                    / "docs"
                    / "code"
                    / "test.py"
                ),
            ]
        )
        print("Documentation tests passed.")

    def _pip_uninstall_itk_wildcard(self, python_executable: str | Path):
        """Uninstall all installed packages whose name starts with 'itk'.

        pip does not support shell-style wildcards directly for uninstall, so we:
          - run 'pip list --format=freeze'
          - collect package names whose normalized name starts with 'itk'
          - call 'pip uninstall -y <names...>' if any are found
        """
        python_executable = str(python_executable)
        try:
            proc = subprocess.run(
                [python_executable, "-m", "pip", "list", "--format=freeze"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            print(
                f"Warning: failed to list packages with pip at {python_executable}: {e}"
            )
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
            self.echo_check_call(
                [python_executable, "-m", "pip", "uninstall", "-y", *packages]
            )

    def find_unix_exectable_paths(
        self,
        venv_dir: Path,
    ) -> tuple[str, str, str, str, str]:
        """Resolve Python interpreter and virtualenv paths on Unix.

        Parameters
        ----------
        venv_dir : Path
            Root of the Python virtual environment.

        Returns
        -------
        tuple[str, str, str, str, str]
            ``(python_executable, python_include_dir, python_library,
            venv_bin_path, venv_base_dir)``.

        Raises
        ------
        FileNotFoundError
            If the Python executable does not exist under *venv_dir*.
        """
        python_executable = venv_dir / "bin" / "python"
        if not python_executable.exists():
            raise FileNotFoundError(f"Python executable not found: {python_executable}")

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
            str(python_include_dir),
            str(python_library),
            str(venv_bin_path),
            str(venv_dir),
        )

    def clone(self):
        """Return a deep copy of this instance for building a dependency.

        Uses ``self.__class__`` so the returned object is the same concrete
        subclass as the original (e.g. ``LinuxBuildPythonInstance``).
        """
        cls = self.__class__
        new = cls.__new__(cls)
        new.__dict__ = copy.deepcopy(self.__dict__)
        return new

    def venv_paths(self) -> None:
        """Populate ``venv_info_dict`` from the pixi-managed Python interpreter.

        Default Unix implementation shared by Linux and macOS.  Windows
        overrides this method with its own path conventions.
        """
        primary_python_base_dir = Path(
            self.package_env_config["PYTHON_EXECUTABLE"]
        ).parent.parent
        (
            python_executable,
            python_include_dir,
            python_library,
            venv_bin_path,
            venv_base_dir,
        ) = self.find_unix_exectable_paths(primary_python_base_dir)
        self.venv_info_dict = {
            "python_executable": python_executable,
            "python_include_dir": python_include_dir,
            "python_library": python_library,
            "venv_bin_path": venv_bin_path,
            "venv_base_dir": venv_base_dir,
            "python_root_dir": primary_python_base_dir,
        }

    @abstractmethod
    def fixup_wheel(
        self, filepath, lib_paths: str = "", remote_module_wheel: bool = False
    ):  # pragma: no cover - abstract
        """Apply platform-specific wheel repairs (auditwheel, delocate, delvewheel).

        Parameters
        ----------
        filepath : str
            Path to the ``.whl`` file to fix.
        lib_paths : str, optional
            Additional library search paths (semicolon-delimited on Windows).
        remote_module_wheel : bool, optional
            True when fixing a wheel for an external remote module.
        """
        pass

    @abstractmethod
    def build_tarball(self):
        """Create a compressed archive of the ITK build tree for caching."""
        pass

    def post_build_cleanup(self) -> None:
        """Remove intermediate build artifacts, leaving ``dist/`` intact.

        Actions:
        - remove oneTBB-prefix (symlink or dir)
        - remove ITKPythonPackage/, tools/, _skbuild/, build/
        - remove top-level *.egg-info
        - remove ITK-* build tree and tarballs
        - if ITK_MODULE_PREQ is set, remove cloned module dirs
        """
        base = Path(self.package_env_config["IPP_SOURCE_DIR"])

        def rm(tree_path: Path):
            try:
                _remove_tree(tree_path)
            except Exception:
                pass

        # 1) unlink oneTBB-prefix if it's a symlink or file
        tbb_prefix_dir = base / "oneTBB-prefix"
        try:
            if tbb_prefix_dir.is_symlink() or tbb_prefix_dir.is_file():
                tbb_prefix_dir.unlink(missing_ok=True)  # type: ignore[arg-type]
            elif tbb_prefix_dir.exists():
                rm(tbb_prefix_dir)
        except Exception:
            pass

        # 2) standard build directories
        for rel in ("ITKPythonPackage", "tools", "_skbuild", "build"):
            rm(base / rel)

        # 3) egg-info folders at top-level
        for p in base.glob("*.egg-info"):
            rm(p)

        # 4) ITK build tree and tarballs
        target_arch = self.package_env_config["ARCH"]
        for p in base.glob(f"ITK-*-{self.package_env_config}_{target_arch}"):
            rm(p)

        # Tarballs
        for p in base.glob(f"ITKPythonBuilds-{self.package_env_config}*.tar.zst"):
            rm(p)

        # 5) Optional module prerequisites cleanup (ITK_MODULE_PREQ)
        # Format: "InsightSoftwareConsortium/ITKModuleA@v1.0:Kitware/ITKModuleB@sha"
        itk_preq = self.package_env_config.get("ITK_MODULE_PREQ") or environ.get(
            "ITK_MODULE_PREQ", ""
        )
        if itk_preq:
            for entry in itk_preq.split(":"):
                entry = entry.strip()
                if not entry:
                    continue
                try:
                    module_name = entry.split("@", 1)[0].split("/", 1)[1]
                except Exception:
                    continue
                rm(base / module_name)

    @abstractmethod
    def prepare_build_env(self) -> None:  # pragma: no cover - abstract
        """Set up platform-specific build environment and CMake configurations.

        Must populate ``self.venv_info_dict``, configure TBB settings,
        and set the ITK binary build directory in
        ``self.cmake_itk_source_build_configurations``.
        """
        pass

    @abstractmethod
    def post_build_fixup(self) -> None:  # pragma: no cover - abstract
        """Run platform-specific post-build wheel fixups.

        Called after all wheels are built but before the final import
        test. Typically invokes ``fixup_wheel`` or ``fixup_wheels``.
        """
        pass

    def final_import_test(self) -> None:  # pragma: no cover
        """Install and smoke-test the built wheels."""
        self.final_wheel_import_test(installed_dist_dir=self.dist_dir)

    @abstractmethod
    def discover_python_venvs(
        self, platform_os_name: str, platform_architechure: str
    ) -> list[str]:
        """Return available Python environment names for the given platform.

        Parameters
        ----------
        platform_os_name : str
            Operating system identifier.
        platform_architechure : str
            CPU architecture identifier.

        Returns
        -------
        list[str]
            Sorted list of discovered environment names.
        """
        pass

    @staticmethod
    def _update_module_itk_deps(pyproject_path: Path, itk_version: str) -> bool:
        """Rewrite ITK dependency pins in a remote module's pyproject.toml.

        Replaces hard-coded ITK sub-package version pins (e.g.
        ``itk-io == 5.4.*``) with a pin matching the ITK version being
        built against (e.g. ``itk-io >= 5.4``).  This ensures that
        wheels produced for ITK 6 can be installed alongside ITK 6
        packages without pip dependency conflicts.

        .. note:: Strategy 1 (build-time rewrite) — interim solution.

           This approach rewrites the module's pyproject.toml on disk,
           builds the wheel, then restores the original. It works today
           with zero changes to remote modules but is inherently fragile
           (regex-based, modifies the source tree).

           **Plan to migrate to Strategy 3 (scikit-build-core dynamic
           metadata provider):**

           1. Create a small installable package ``itk-build-metadata``
              that implements the scikit-build-core dynamic metadata
              provider interface (see scikit-build-core docs:
              ``tool.scikit-build.metadata.<field>.provider``).

           2. The provider inspects the build environment at wheel-build
              time to discover the ITK version — either from the
              ``ITK_PACKAGE_VERSION`` env var (set by this build system),
              from ``ITKConfig.cmake`` on ``CMAKE_PREFIX_PATH``, or from
              an already-installed ``itk-core`` package.

           3. It emits the correct ``Requires-Dist`` entries (e.g.
              ``itk-io >= 5.4``) into the wheel metadata without
              touching ``pyproject.toml`` on disk at all.

           4. Remote modules opt in by declaring dynamic dependencies::

                [project]
                dynamic = ["dependencies"]

                [tool.scikit-build.metadata.dependencies]
                provider = "itk_build_metadata"
                provider-path = "."   # or from installed package

           5. Roll out incrementally: update ITKModuleTemplate first,
              then migrate existing modules via the ``/update-itk-deps``
              skill (in REMOTE_MODULES/.claude/skills/). Modules that
              have not migrated continue to work via this Strategy 1
              fallback, so both approaches coexist during the transition.

           6. Once all ~60 remote modules have adopted Strategy 3,
              this method can be removed.

        Parameters
        ----------
        pyproject_path : Path
            Path to the module's ``pyproject.toml``.
        itk_version : str
            The ITK PEP 440 version string being built (e.g. ``6.0.0b2``).
            Used to compute the minimum major version for the ``>=`` pin.

        Returns
        -------
        bool
            *True* if any dependency was rewritten.
        """
        import re

        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib  # Python < 3.11

        with open(pyproject_path, "rb") as f:
            pyproject_data = tomllib.load(f)

        # --- Strategy 3: module declares dynamic dependencies -----------------
        dynamic_fields = (
            pyproject_data.get("project", {}).get("dynamic", [])
        )
        if "dependencies" in dynamic_fields:
            # The module has opted into dynamic dependency resolution.
            # Set ITK_PACKAGE_VERSION in the environment so the
            # scikit-build-core metadata provider (itk-build-metadata)
            # can emit the correct Requires-Dist at build time.
            os.environ["ITK_PACKAGE_VERSION"] = itk_version
            print(
                f"Strategy 3: {pyproject_path.name} declares "
                f"dynamic=[\"dependencies\"]; set ITK_PACKAGE_VERSION="
                f"{itk_version} for metadata provider"
            )
            return False  # no file modification needed

        # --- Strategy 1: build-time rewrite (fallback) ------------------------
        text = pyproject_path.read_text(encoding="utf-8")

        # Only rewrite ITK *base* sub-packages whose versions are tied to
        # the ITK release.  Remote module cross-deps (e.g.
        # itk-meshtopolydata == 0.12.*) are versioned independently and
        # must NOT be rewritten — flag them for manual review instead.
        _ITK_BASE_PACKAGES = (
            "itk-core",
            "itk-numerics",
            "itk-io",
            "itk-filtering",
            "itk-registration",
            "itk-segmentation",
        )
        _base_pkg_alt = "|".join(re.escape(p) for p in _ITK_BASE_PACKAGES)
        pattern = re.compile(
            rf'"({_base_pkg_alt})\s*==\s*[\d]+\.[\d]+\.\*"'
        )

        # Warn about pinned remote-module cross-deps that may also need
        # attention but should not be auto-rewritten.
        cross_dep_pattern = re.compile(
            r'"(itk-[a-z][a-z0-9-]*)\s*==\s*[\d]+\.[\d]+\.\*"'
        )
        for m in cross_dep_pattern.finditer(text):
            pkg = m.group(1)
            if pkg not in _ITK_BASE_PACKAGES:
                print(
                    f"  WARNING: {pyproject_path.name} pins remote module "
                    f"cross-dep {m.group(0)} — review manually"
                )

        # Determine the minimum version floor from the ITK version being built.
        # Pin to vMAJOR.MINOR of the ITK version so the wheel is only
        # installable alongside the ITK series it was compiled against.
        # For "6.0.0b2.post757" -> "6.0", for "5.4.0" -> "5.4".
        parts = itk_version.split(".")
        try:
            min_floor = f"{parts[0]}.{parts[1]}"
        except IndexError:
            min_floor = itk_version

        changed = False
        def _replace(m: re.Match) -> str:
            nonlocal changed
            changed = True
            pkg = m.group(1)
            return f'"{pkg} >= {min_floor}"'

        new_text = pattern.sub(_replace, text)
        if changed:
            pyproject_path.write_text(new_text, encoding="utf-8")
            print(
                f"Strategy 1: Updated ITK dependency pins in {pyproject_path} "
                f"(>= {min_floor} for ITK {itk_version})"
            )
        return changed

    def build_external_module_python_wheel(self):
        """Build a wheel for an external ITK remote module via scikit-build-core."""
        self.module_source_dir = Path(self.module_source_dir)
        out_dir = self.module_source_dir / "dist"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Dynamically update ITK dependency pins to match the version being built.
        # Back up the original pyproject.toml so the working tree is restored
        # after the wheel is produced.
        module_pyproject = self.module_source_dir / "pyproject.toml"
        pyproject_orig = module_pyproject.with_suffix(".toml.orig")
        pyproject_whl = module_pyproject.with_suffix(".toml.whl")
        deps_rewritten = False
        if module_pyproject.is_file():
            itk_ver = self.package_env_config.get("ITK_PACKAGE_VERSION", "")
            if itk_ver:
                shutil.copy2(module_pyproject, pyproject_orig)
                deps_rewritten = self._update_module_itk_deps(
                    module_pyproject, itk_ver
                )

        # Ensure venv tools are first in PATH
        py_exe = str(self.package_env_config["PYTHON_EXECUTABLE"])  # Python3_EXECUTABLE

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
            f"--config-setting=cmake.build-type={self.package_env_config['BUILD_TYPE']}",
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

        # Pass Python library paths when explicitly known (Windows)
        py_library = self.venv_info_dict.get("python_library", "")
        if py_library:
            defs.set("Python3_LIBRARY:FILEPATH", str(py_library))
        py_sabi_library = self.venv_info_dict.get("python_sabi_library", "")
        if py_sabi_library:
            defs.set("Python3_SABI_LIBRARY:FILEPATH", str(py_sabi_library))

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

        try:
            self.echo_check_call(cmd)

            # Post-process produced wheels (e.g., delocate on macOS x86_64)
            for wheel in out_dir.glob("*.whl"):
                self.fixup_wheel(str(wheel), remote_module_wheel=True)
        finally:
            # Restore original pyproject.toml so the working tree stays clean
            if deps_rewritten and pyproject_orig.is_file():
                shutil.copy2(module_pyproject, pyproject_whl)
                shutil.move(str(pyproject_orig), str(module_pyproject))
                print(
                    f"Restored {module_pyproject} "
                    f"(modified version saved as {pyproject_whl.name})"
                )

    def build_itk_python_wheels(self):
        """Build all ITK Python wheels listed in ``WHEEL_NAMES.txt``."""
        # Build wheels
        for wheel_name in self.wheel_names:
            print("#")
            print(f"# Build ITK wheel {wheel_name} from {self.wheel_names}")
            print("#")
            # Configure pyproject.toml
            wheel_configbuild_dir_root: Path = (
                self.build_dir_root
                / "wheelbuilds"
                / f"{wheel_name}_{self.get_pixi_environment_name()}"
            )
            wheel_configbuild_dir_root.mkdir(parents=True, exist_ok=True)
            configure_one_pyproject_file(
                str(self.ipp_dir / "scripts"),
                self.package_env_config,
                wheel_configbuild_dir_root,
                wheel_name,
            )

            # Generate wheel using
            cmd = [
                str(self.package_env_config["PYTHON_EXECUTABLE"]),
                "-m",
                "build",
                "--verbose",
                "--wheel",
                "--outdir",
                str(self.build_dir_root / "dist"),
                "--no-isolation",
                "--skip-dependency-check",
                f"--config-setting=cmake.build-type={self.package_env_config['BUILD_TYPE']}",
                f"--config-setting=cmake.source-dir={self.package_env_config['IPP_SOURCE_DIR'] / 'BuildWheelsSupport'}",
                f"--config-setting=build-dir={wheel_configbuild_dir_root/'build'}",
            ]
            # Build scikit-build defines via builder
            scikitbuild_cmdline_args = CMakeArgumentBuilder()
            scikitbuild_cmdline_args.update(self.cmake_compiler_configurations.items())
            scikitbuild_cmdline_args.update(
                self.cmake_itk_source_build_configurations.items()
            )
            scikitbuild_cmdline_args.update(
                {
                    "ITKPythonPackage_USE_TBB:BOOL": self.package_env_config["USE_TBB"],
                    "ITKPythonPackage_ITK_BINARY_REUSE:BOOL": "ON",
                    "ITKPythonPackage_WHEEL_NAME:STRING": f"{wheel_name}",
                    "DOXYGEN_EXECUTABLE:FILEPATH": f"{self.package_env_config['DOXYGEN_EXECUTABLE']}",
                }
            )

            if (
                self.cmake_cmdline_definitions
            ):  # Do last to override with command line items
                scikitbuild_cmdline_args.update(self.cmake_cmdline_definitions.items())
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
        """Configure and build the ITK C++ libraries with Python wrapping."""
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
                self.package_env_config["NINJA_EXECUTABLE"],
                f"-j{self.build_node_cpu_count}",
                f"-l{self.build_node_cpu_count}",
                "-C",
                self.cmake_itk_source_build_configurations["ITK_BINARY_DIR:PATH"],
            ]
        )
        print("# FINISHED-Build ITK C++")

    def _build_module_dependencies(self):
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
        print(f"Building module dependencies: {self.itk_module_deps}")
        self.module_dependencies_root_dir.mkdir(parents=True, exist_ok=True)

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
        for _current_entry, entry in enumerate(normalized):
            if len(entry) == 0:
                continue
            print(f"Get dependency module information for {entry}")
            org = entry.split("/", 1)[0]
            repo_tag = entry.split("/", 1)[1]
            repo = repo_tag.split("@", 1)[0]
            tag = repo_tag.split("@", 1)[1] if "@" in repo_tag else ""

            upstream = f"https://github.com/{org}/{repo}.git"
            dependant_module_clone_dir = (
                self.module_dependencies_root_dir / repo
                if self.module_dependencies_root_dir
                else module_root / repo
            )
            if not dependant_module_clone_dir.exists():
                self.echo_check_call(
                    ["git", "clone", upstream, dependant_module_clone_dir]
                )

            # Checkout requested tag
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
                msg: str = (
                    f"Old sci-kit-build with setup.py is no longer supported for {dependant_module_clone_dir} at {tag}"
                )
                raise RuntimeError(msg)

            # Clone the current build environment and modify for the current module
            dependent_module_build_setup = self.clone()
            dependent_module_build_setup.module_source_dir = Path(
                dependant_module_clone_dir
            )
            dependent_module_build_setup.itk_module_deps = None  # Prevent recursion
            dependent_module_build_setup.run()

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

        Warns if directory structure doesn't match expected layout for GitHub Actions.
        """
        arch_postfix: str = f"{self.package_env_config['ARCH']}"
        # Fixup platform name for macOS, eventually need to standardize on macosx naming convention
        platform_name: str = get_default_platform_build().split("-")[0]
        tar_name: str = f"ITKPythonBuilds-{platform_name}-{arch_postfix}.tar"
        itk_packaging_reference_dir = self.build_dir_root.parent

        tar_path: Path = itk_packaging_reference_dir / tar_name
        zst_path: Path = itk_packaging_reference_dir / f"{tar_name}.zst"

        itk_resources_build_dir: Path = self.build_dir_root
        ipp_source_dir: Path = self.package_env_config["IPP_SOURCE_DIR"]

        # Validate directory structure and determine tarball strategy
        issues = []

        # Try to use relative paths first
        try:
            rel_build = itk_resources_build_dir.relative_to(itk_packaging_reference_dir)
            rel_ipp = ipp_source_dir.relative_to(itk_packaging_reference_dir)
        except ValueError:
            # Fall back to absolute paths
            rel_build = itk_resources_build_dir
            rel_ipp = ipp_source_dir
            itk_packaging_reference_dir = Path(
                "/"
            )  # Tar from root when using absolute paths

        if itk_resources_build_dir.parent != ipp_source_dir.parent:
            issues.append("Build and source dirs are not siblings")

        if ipp_source_dir.name != "ITKPythonPackage":
            issues.append(
                f"Source dir is '{ipp_source_dir.name}', expected 'ITKPythonPackage'"
            )

        # Issue consolidated warning for compatibility issues
        if issues:
            print("\n" + "=" * 70)
            print("WARNING: Tarball will NOT be compatible with GitHub Actions")
            print("=" * 70)
            for issue in issues:
                print(f"  * {issue}")
            print(
                "\nExpected structure: <parent>/{ITKPythonPackage, ITKPythonPackage-build}"
            )
            print(f"Current: Build={itk_resources_build_dir}")
            print(f"         Source={ipp_source_dir}")
            print(
                "\nTarball will be created for local reuse but may not work in CI/CD."
            )
            print("=" * 70 + "\n")

        # Build tarball include paths
        tarball_include_paths = [
            str(rel_build),
            str(rel_ipp),
        ]

        if tar_path.exists():
            print(f"Removing existing tarball {tar_path}")
            tar_path.unlink()
        if zst_path.exists():
            print(f"Removing existing zstd tarball {zst_path}")
            zst_path.unlink()

        # Create tarball
        self.echo_check_call(
            [
                "tar",
                "-C",
                str(itk_packaging_reference_dir),
                "-cf",
                str(tar_path),
                "--exclude=*.o",
                "--exclude=*.whl",  # Do not include built wheels
                "--exclude=*/dist/*",  # Do not include the dist whl output directory
                "--exclude=*/wheelbuilds/*",  # Do not include the wheelbuild support directory
                "--exclude=*/__pycache__/*",  # Do not include __pycache__
                "--exclude=install_manifest_*.txt",  # Do not include install manifest files
                "--exclude=._*",  # Exclude mac dot files
                "--exclude=*/.git/*",
                "--exclude=*/.idea/*",
                "--exclude=*/.pixi/*",
                "--exclude=*/castxml_inputs/*",
                "--exclude=*/Wrapping/Modules/*",
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

        print(f"Tarball created: {zst_path}")
        if issues:
            print("Compatibility warnings above - review before using in CI/CD")

    def get_pixi_environment_name(self):
        """Return the pixi environment name for this build instance.

        The pixi environment name is the same as the platform_env and
        is related to the environment setups defined in pixi.toml
        in the root of this git directory that contains these scripts.
        """
        return self.platform_env

    def echo_check_call(
        self,
        cmd: list[str | Path] | tuple[str | Path] | str | Path,
        use_pixi_env: bool = True,
        env=None,
        **kwargs: dict,
    ) -> int:
        """Print the command, then run subprocess.check_call.

        Parameters
        ----------
        cmd :
            Command to execute, same as subprocess.check_call.
        **kwargs :
            Additional keyword arguments forwarded to subprocess.check_call.
        """

        pixi_environment: str = self.get_pixi_environment_name()
        pixi_executable: Path = self.package_env_config["PIXI_EXECUTABLE"]
        pixi_run_preamble: list[str] = []
        pixi_run_dir: Path = self.ipp_dir
        pixi_env: dict[str, str] = os.environ.copy()
        if env is not None:
            pixi_env.update(env)
        pixi_env.update(
            {
                "PIXI_HOME": str(pixi_run_dir / ".pixi"),
            }
        )
        # if self.pa == "windows":
        #     pixi_env.update(
        #         {
        #             "TEMP": "C:\Temp",
        #             "TMP": "C:\Temp",
        #         }
        #     )

        if pixi_environment and use_pixi_env:
            pixi_run_preamble = [
                str(pixi_executable),
                "run",
                "-e",
                pixi_environment,
                "--",
            ]

        # convert all items to strings (i.e. Path() to str)
        cmd = pixi_run_preamble + [str(c) for c in cmd]
        # Prepare a friendly command-line string for display
        try:
            if isinstance(cmd, list | tuple):
                display_cmd = " ".join(cmd)
            else:
                display_cmd = str(cmd)
        except Exception as e:
            display_cmd = f"{str(cmd)}\nERROR: {e}"
            sys.exit(1)
        print(f">>Start Running: cd {pixi_run_dir} && {display_cmd}")
        print("^" * 60)
        print(cmd)
        print("^" * 60)
        print(kwargs)
        print("^" * 60)
        process_completion_info: subprocess.CompletedProcess = (
            run_commandLine_subprocess(cmd, env=pixi_env, cwd=pixi_run_dir, **kwargs)
        )
        cmd_return_status: int = process_completion_info.returncode
        print("^" * 60)
        print(f"<<Finished Running: cmd_return_status={cmd_return_status}")
        print(" ====== stdout =====")
        stdout_val = process_completion_info.stdout
        if isinstance(stdout_val, bytes):
            print(stdout_val.decode("utf-8"))
        else:
            print(stdout_val)
        print(" ====== stderr =====")
        stderr_val = process_completion_info.stderr
        if isinstance(stderr_val, bytes):
            print(stderr_val.decode("utf-8"))
        else:
            print(stderr_val)
        print(" ===================")
        return cmd_return_status
