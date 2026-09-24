import copy
import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path

import build_environment
import wheel_packaging
from build_jobs import compute_build_jobs, compute_load_limit, physical_memory_gb
from BuildManager import BuildManager
from cmake_argument_builder import CMakeArgumentBuilder
from module_dependencies import build_module_dependencies, update_module_itk_deps
from pyproject_configure import STABLE_ABI_TAG, configure_one_pyproject_file
from target_platform import TargetPlatform
from wheel_builder_utils import (
    _remove_tree,
    _which,
)


def verify_stable_abi_wheels(out_dir: Path, py_api: str) -> list[Path]:
    """Return the wheels in *out_dir*, refusing any not tagged ``<py_api>-abi3``.

    Raises
    ------
    RuntimeError
        If no wheel was produced, or any wheel carries a different tag.
    """
    built_wheels = sorted(out_dir.glob("*.whl"))
    if not built_wheels:
        raise RuntimeError(f"No wheel was produced in {out_dir}")
    mistagged = [w.name for w in built_wheels if f"{py_api}-abi3" not in w.name]
    if mistagged:
        raise RuntimeError(
            f"Expected {py_api}-abi3 wheels, got: {', '.join(mistagged)}"
        )
    return built_wheels


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
    module_itk_dir : {"build", "install"}, optional
        Which ITK tree a remote module is configured against. ``"build"``
        (the default) passes the ITK build tree as ``ITK_DIR``.
        ``"install"`` first runs ``cmake --install`` on that build tree and
        passes the resulting ``<prefix>/lib/cmake/ITK-<version>`` instead,
        which requires an ITK that installs its module build files and
        wrapping infrastructure (``ITK_INSTALL_WRAPPING_DEVELOPMENT_FILES``).
    """

    MODULE_ITK_DIR_CHOICES = ("build", "install")
    #: Class-level default so instances created without ``__init__`` (as the
    #: test fixtures do) still take the historical build-tree path.
    module_itk_dir: str = "build"

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
        module_itk_dir: str = "build",
    ) -> None:
        if module_itk_dir not in self.MODULE_ITK_DIR_CHOICES:
            raise ValueError(
                f"module_itk_dir must be one of {self.MODULE_ITK_DIR_CHOICES}, "
                f"not {module_itk_dir!r}"
            )
        self.module_itk_dir = module_itk_dir
        # Jobs are bounded by physical memory, not just CPU count: ITK's
        # wrapping units are template-heavy, and cpu_count() jobs on a box
        # with ~2 GB RAM per thread thrashes instead of building faster.
        # See build_jobs.py; ITK_BUILD_JOBS / ITK_BUILD_LOAD_LIMIT override.
        self.build_node_memory_gb: float | None = physical_memory_gb()
        self.build_node_cpu_count: int = compute_build_jobs(
            os.cpu_count(), self.build_node_memory_gb
        )
        # -l is a CPU budget, keyed to the thread count, never to the
        # memory-derived job count: ninja honours -l on Windows, and
        # -l<jobs> on a box with more threads than jobs throttles ninja to
        # a crawl whenever a saturating compile pushes load past <jobs>.
        self.build_load_limit: int = compute_load_limit(os.cpu_count())
        _mem = (
            f"{self.build_node_memory_gb:.1f} GB"
            if self.build_node_memory_gb
            else "unknown"
        )
        print(
            f"# Build parallelism: -j{self.build_node_cpu_count} "
            f"-l{self.build_load_limit} "
            f"(cpus={os.cpu_count()}, ram={_mem})"
        )
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
        self.target: TargetPlatform = TargetPlatform.detect(self.package_env_config)

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
                "ITK_DEFAULT_THREADER:STRING": "Pool",
                "ITK_WRAP_PYTHON:BOOL": "ON",
                "ITK_WRAP_DOC:BOOL": "ON",
                # Install the module build files and wrapping infrastructure
                # so a remote module can be configured against the install
                # tree (module_itk_dir="install"). Only an ITK that carries
                # that support honours it; elsewhere CMake reports the
                # variable as unused and the build is unchanged. Set for every
                # build so a cached build tree can be installed later.
                "ITK_INSTALL_WRAPPING_DEVELOPMENT_FILES:BOOL": "ON",
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

    def build_step_table(self) -> OrderedDict[str, Callable]:
        """The ordered build steps for this run, keyed by recorded step name.

        Stages that do not apply are registered under a ``_skipped`` key
        mapped to a no-op, so the step log records that they were bypassed
        on purpose rather than silently absent.
        """
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
            # Steps 04 and 05 act on the ITK wheels that step 03 produces:
            # 04 repairs itk_core and 05 pip-installs from dist/ and imports
            # the result. When 03 is skipped -- the remote-module path, which
            # takes ITK from a cache that deliberately excludes wheels --
            # there is nothing for either to act on. Left registered, 05
            # fails with "Could not find a version that satisfies the
            # requirement itk (from versions: none)" and the module wheel
            # in step 06 is never built. It only *looked* like it worked on a
            # machine whose dist/ still held wheels from an earlier ITK build.
            skipped_when_no_itk_wheels = {
                "03_build_wheels": "03_build_wheels_skipped",
                "04_post_build_fixup": "04_post_build_fixup_skipped",
                "05_final_import_test": "05_final_import_test_skipped",
            }
            python_package_build_steps = OrderedDict(
                (
                    (skipped_when_no_itk_wheels[k], (lambda: None))
                    if k in skipped_when_no_itk_wheels
                    else (k, v)
                )
                for k, v in python_package_build_steps.items()
            )

        if self.module_source_dir is not None:
            # A module built against an *installed* ITK needs the install
            # tree to exist first. The step is registered (or recorded as
            # skipped) only when a module is being built, since nothing else
            # consumes the install tree.
            if self.module_itk_dir == "install":
                python_package_build_steps["06_install_wrapped_itk_cplusplus"] = (
                    self.install_wrapped_itk_cplusplus
                )
            else:
                python_package_build_steps[
                    "06_install_wrapped_itk_cplusplus_skipped"
                ] = lambda: None
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
        if self.cleanup and not self.build_itk_tarball_cache:
            # Cleanup globs dist/ITKPythonBuilds-*.tar*, so it is incompatible
            # with the step that publishes that cache.
            python_package_build_steps["08_post_build_cleanup"] = (
                self.post_build_cleanup
            )
        return python_package_build_steps

    def run(self) -> None:
        """Run the full build flow for this Python instance."""
        # Use BuildManager to persist and resume build steps

        # HACK
        if self.itk_module_deps:
            build_module_dependencies(self)

        python_package_build_steps = self.build_step_table()

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

        self.echo_check_call(cmd, check=True)
        # check=True: a failed superbuild (a oneTBB download that never
        # completed, for instance) was recorded as a done step, and the run
        # then failed in step 02 with "Could not find ... TBBConfig.cmake",
        # far from the cause.
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
            check=True,
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
        self._pip_uninstall_itk_wildcard(self.package_env_config["PYTHON_EXECUTABLE"])
        checks = [
            (
                "pip install itk",
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
                ],
            ),
            (
                "import itk",
                [self.package_env_config["PYTHON_EXECUTABLE"], "-c", "import itk;"],
            ),
            (
                "instantiate itk.Image",
                [
                    self.package_env_config["PYTHON_EXECUTABLE"],
                    "-c",
                    "import itk; image = itk.Image[itk.UC, 2].New()",
                ],
            ),
            (
                "import itk with lazy loading disabled",
                [
                    self.package_env_config["PYTHON_EXECUTABLE"],
                    "-c",
                    "import itkConfig; itkConfig.LazyLoading=False; import itk;",
                ],
            ),
            (
                "documentation tests",
                [
                    self.package_env_config["PYTHON_EXECUTABLE"],
                    str(
                        self.package_env_config["IPP_SOURCE_DIR"]
                        / "docs"
                        / "code"
                        / "test.py"
                    ),
                ],
            ),
        ]
        for description, cmd in checks:
            exit_status = self.echo_check_call(cmd)
            if exit_status != 0:
                raise RuntimeError(
                    f"final_wheel_import_test failed at step {description!r} "
                    f"(exit status {exit_status})"
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
            exit_status = self.echo_check_call(
                [python_executable, "-m", "pip", "uninstall", "-y", *packages]
            )
            if exit_status != 0:
                raise RuntimeError(
                    f"Failed to uninstall existing ITK packages {packages!r} "
                    f"(exit status {exit_status})"
                )

    def find_unix_exectable_paths(
        self,
        venv_dir: Path,
    ) -> tuple[str, str, str, str, str]:
        """Delegate to the module-level implementation."""
        return build_environment.find_unix_exectable_paths(venv_dir)

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
        """Remove intermediate build artifacts, leaving ``dist/`` intact."""
        wheel_packaging.post_build_cleanup(self)

    def prepare_build_env(self) -> None:
        """Skeleton shared by every platform.

        Subclasses vary only in ``_configure_toolchain``.
        """
        self.venv_paths()
        self.update_venv_itk_build_configurations()
        self._configure_toolchain()

        build_root = self.build_dir_root / "build"
        downloaded = build_root / (
            f"ITK-{self.platform_env}-{self.platform_env}"
            f"_{self.target.build_dir_suffix}"
        )
        if downloaded.exists():
            itk_binary_build_name = downloaded
        else:
            itk_binary_build_name = build_root / (
                f"ITK-{self.platform_env}-{self.get_pixi_environment_name()}"
                f"_{self.target.build_dir_suffix}"
            )
        self.cmake_itk_source_build_configurations.set(
            "ITK_BINARY_DIR:PATH", itk_binary_build_name.as_posix()
        )

    def _configure_toolchain(self) -> None:
        """Set platform-specific TBB, compiler, and deployment values."""
        raise NotImplementedError

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
                deps_rewritten = update_module_itk_deps(module_pyproject, itk_ver)

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

        # ITK_DIR for the external module: the install tree when asked for,
        # otherwise the configured ITK build tree.
        if self.module_itk_dir == "install":
            itk_build_path = self.installed_itk_dir().as_posix()
        else:
            itk_build_path = self.cmake_itk_source_build_configurations.get(
                "ITK_BINARY_DIR:PATH",
                "",
            )

        wheel_py_api = STABLE_ABI_TAG

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

        if self.target.os_name == "windows":
            # pixi's conda-forge vs2022 activation exports
            # CMAKE_GENERATOR="Visual Studio 17 2022", which scikit-build-core
            # honours. That multi-config generator makes ITK's wrapping
            # file(GENERATE) calls collide: "Evaluation file to be written
            # multiple times with different content" on *.castxml.inc. ITK
            # itself is configured with -G Ninja, so match it here. Passing -G
            # explicitly also makes CMake ignore the ambient
            # CMAKE_GENERATOR_PLATFORM/TOOLSET, which Ninja would reject.
            cmd.append("--config-setting=cmake.args=-GNinja")

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
            self.echo_check_call(cmd, check=True)

            built_wheels = verify_stable_abi_wheels(out_dir, wheel_py_api)

            # Post-process produced wheels (e.g., delocate on macOS x86_64)
            for wheel in built_wheels:
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
            if self.target.os_name == "windows":
                # Same reason as the remote-module build below: pixi's
                # vs2022 activation exports CMAKE_GENERATOR="Visual Studio
                # 17 2022", scikit-build-core honours it, and the ITK wheels
                # were being built with MSBuild while ITK itself used Ninja.
                # An explicit -G also makes CMake ignore the ambient
                # CMAKE_GENERATOR_PLATFORM/TOOLSET that Ninja would reject.
                cmd.append("--config-setting=cmake.args=-GNinja")
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
            self.echo_check_call(cmd, check=True)

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
        self.echo_check_call(cmd, check=True)
        self.echo_check_call(
            [
                self.package_env_config["NINJA_EXECUTABLE"],
                f"-j{self.build_node_cpu_count}",
                f"-l{self.build_load_limit}",
                "-C",
                self.cmake_itk_source_build_configurations["ITK_BINARY_DIR:PATH"],
            ],
            check=True,
        )
        print("# FINISHED-Build ITK C++")

    def itk_install_prefix(self) -> Path:
        """Where ``cmake --install`` places the ITK install tree.

        A sibling of the build tree, so a cache of ``build/`` carries it.
        """
        bld = Path(self.cmake_itk_source_build_configurations["ITK_BINARY_DIR:PATH"])
        return bld.with_name(f"{bld.name}-install")

    def installed_itk_dir(self) -> Path:
        """``ITK_DIR`` inside the install tree, verified usable for a module.

        Raises
        ------
        RuntimeError
            If no installed ITK exists under the prefix, or it lacks the
            module build files and wrapping infrastructure a remote module
            needs (an ITK without ``ITK_INSTALL_WRAPPING_DEVELOPMENT_FILES``
            installs neither, and the module's first ``include`` fails).
        """
        prefix = self.itk_install_prefix()
        configs = sorted((prefix / "lib" / "cmake").glob("ITK-*/ITKConfig.cmake"))
        if not configs:
            raise RuntimeError(
                f"No installed ITK under {prefix}: expected "
                f"lib/cmake/ITK-<version>/ITKConfig.cmake. The install step "
                f"(cmake --install <ITK build tree>) has not produced one."
            )
        itk_dir = configs[-1].parent
        required = ("ITKModuleExternal.cmake", "Wrapping/CMakeLists.txt")
        missing = [name for name in required if not (itk_dir / name).is_file()]
        if missing:
            raise RuntimeError(
                f"Installed ITK at {itk_dir} cannot build a remote module: "
                f"missing {missing}. ITK must install its module build files "
                f"and wrapping infrastructure (configure with "
                f"ITK_INSTALL_WRAPPING_DEVELOPMENT_FILES=ON on an ITK that "
                f"supports it)."
            )
        return itk_dir

    def install_wrapped_itk_cplusplus(self) -> None:
        """Install the ITK build tree so a module can use it as ``ITK_DIR``."""
        prefix = self.itk_install_prefix()
        print("#")
        print(f"# START-Install ITK C++ -> {prefix}")
        print("#")
        self.echo_check_call(
            [
                self.package_env_config["CMAKE_EXECUTABLE"],
                "--install",
                self.cmake_itk_source_build_configurations["ITK_BINARY_DIR:PATH"],
                "--prefix",
                str(prefix),
            ],
            check=True,
        )
        itk_dir = self.installed_itk_dir()
        print(f"# FINISHED-Install ITK C++: ITK_DIR={itk_dir}")

    def create_posix_tarball(self):
        """Create a compressed tarball of the ITK Python build tree."""
        wheel_packaging.create_posix_tarball(self)

    def get_pixi_environment_name(self):
        """Delegate, naming the pixi environment for this build."""
        return build_environment.get_pixi_environment_name(self.platform_env)

    def echo_check_call(
        self, cmd, use_pixi_env: bool = True, env=None, **kwargs
    ) -> int:
        """Delegate, supplying this build's pixi environment name."""
        return build_environment.echo_check_call(
            cmd,
            pixi_env_name=self.get_pixi_environment_name(),
            pixi_executable=self.package_env_config["PIXI_EXECUTABLE"],
            run_dir=self.ipp_dir,
            use_pixi_env=use_pixi_env,
            env=env,
            **kwargs,
        )
