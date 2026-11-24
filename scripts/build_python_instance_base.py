import contextlib
import copy
import os
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import build_environment
import wheel_dependency_audit
import wheel_packaging
from build_config import BuildConfig
from build_environment import PythonEnvironment
from build_inputs import (
    build_fingerprint,
    build_inputs,
    module_source_state,
    resolved_itk_commit,
)
from build_jobs import (
    compute_build_jobs,
    compute_link_jobs,
    compute_load_limit,
    compute_lto_jobs,
    job_pool_definitions,
    lto_jobs_definitions,
    physical_memory_gb,
)
from build_manager import BuildManager
from cmake_argument_builder import CMakeArgumentBuilder, definitions_from_cmake_options
from compiler_cache import (
    compiler_cache_definitions,
    compiler_cache_environment,
    compiler_cache_max_size,
    compiler_cache_session,
    compiler_cache_size_setting,
    compiler_cache_tool,
)
from compiler_flags import user_flag_key
from dead_strip import dead_strip_cmake_definitions
from module_dependencies import build_module_dependencies, update_module_itk_deps
from pyproject_configure import (
    STABLE_ABI_TAG,
    PyprojectInputs,
    configure_one_pyproject_file,
)
from target_platform import TargetPlatform
from wheel_builder_utils import (
    remove_tree,
    which,
)
from wheel_profile import WheelProfile, wheel_profile


def verify_stable_abi_wheels(out_dir: Path, py_api: str) -> list[Path]:
    """Return the wheels in *out_dir*, refusing any not tagged ``<py_api>-abi3``.

    Raises
    ------
    RuntimeError
        If no wheel was produced, or any wheel carries a different tag.
    """
    built_wheels = sorted(out_dir.glob("*.whl"))
    if not built_wheels:
        msg = f"No wheel was produced in {out_dir}"
        raise RuntimeError(msg)
    mistagged = [w.name for w in built_wheels if f"{py_api}-abi3" not in w.name]
    if mistagged:
        msg = f"Expected {py_api}-abi3 wheels, got: {', '.join(mistagged)}"
        raise RuntimeError(msg)
    return built_wheels


BUILD_TYPE = "Release"

# PyPI rejects larger files.
PYPI_MAX_WHEEL_BYTES: int = 100 * 1000 * 1000


def use_tbb_setting(tbb_dir: Path | None) -> str:
    """The ``ON``/``OFF`` value of the TBB options for *tbb_dir*."""
    return "OFF" if tbb_dir is None else "ON"


def tbb_dir_setting(tbb_dir: Path | None) -> str:
    """The ``TBB_DIR`` value for *tbb_dir*."""
    return "NOT_FOUND" if tbb_dir is None else str(tbb_dir)


def itk_source_build_configuration(
    config: BuildConfig, tbb_dir: Path | None
) -> dict[str, str]:
    """Return the CMake definitions every ITK wrapping build is configured with."""
    return {
        "ITK_SOURCE_DIR:PATH": f"{config.itk_source_dir}",
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
        # Set for every build so a cached tree can later be installed for module_itk_dir="install".
        "ITK_INSTALL_WRAPPING_DEVELOPMENT_FILES:BOOL": "ON",
        "DOXYGEN_EXECUTABLE:FILEPATH": f"{config.doxygen_executable}",
        "Module_ITKTBB:BOOL": use_tbb_setting(tbb_dir),
        "TBB_DIR:PATH": tbb_dir_setting(tbb_dir),
        # Python settings
        "SKBUILD:BOOL": "ON",
    }


def skip_steps(
    steps: OrderedDict[str, Callable[[], object]], names: frozenset[str] | set[str]
) -> OrderedDict[str, Callable[[], object]]:
    """Return *steps* with each step in *names* renamed ``<name>_skipped`` and a no-op."""
    return OrderedDict(
        ((f"{k}_skipped", lambda: None) if k in names else (k, v))
        for k, v in steps.items()
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
    config : BuildConfig
        The validated build settings.
    cleanup : bool
        Whether to remove intermediate build artifacts.
    build_itk_tarball_cache : bool
        Whether to create a reusable tarball of the ITK build tree.
    cmake_options : list[str]
        Extra ``-D`` options forwarded to CMake.
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
    #: Class-level default for instances built without ``__init__`` (test fixtures).
    module_itk_dir: str = "build"
    uses_tbb: bool = True
    #: oneTBB's CMake package directory, or None when the build uses no TBB.
    tbb_dir: Path | None = None
    python_env: PythonEnvironment

    def __init__(
        self,
        *,
        platform_env: str,
        build_dir_root: Path,
        config: BuildConfig,
        cleanup: bool,
        build_itk_tarball_cache: bool,
        cmake_options: list[str],
        dist_dir: Path,
        module_source_dir: Path | None = None,
        module_dependencies_root_dir: Path | None = None,
        itk_module_deps: str | None = None,
        skip_itk_build: bool | None = None,
        skip_itk_wheel_build: bool | None = None,
        module_itk_dir: str = "build",
    ) -> None:
        if module_itk_dir not in self.MODULE_ITK_DIR_CHOICES:
            msg = (
                f"module_itk_dir must be one of {self.MODULE_ITK_DIR_CHOICES}, "
                f"not {module_itk_dir!r}"
            )
            raise ValueError(msg)
        self.module_itk_dir = module_itk_dir
        # Jobs are bounded by physical memory; see build_jobs.py.
        self.build_node_memory_gb: float | None = physical_memory_gb()
        self.build_node_cpu_count: int = compute_build_jobs(
            os.cpu_count(), self.build_node_memory_gb
        )
        # -l follows the thread count; -l<jobs> would throttle ninja when jobs < threads.
        self.build_load_limit: int = compute_load_limit(os.cpu_count())
        self.build_link_jobs: int = compute_link_jobs(
            self.build_node_cpu_count, self.build_node_memory_gb
        )
        _mem = (
            f"{self.build_node_memory_gb:.1f} GB"
            if self.build_node_memory_gb
            else "unknown"
        )
        print(
            f"# Build parallelism: -j{self.build_node_cpu_count} "
            f"-l{self.build_load_limit} link pool {self.build_link_jobs} "
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
        self.config = config
        self.target: TargetPlatform = TargetPlatform.detect(config.to_environment())

        self.wheel_profile: WheelProfile = wheel_profile(config.itk_source_dir)
        self.wheel_names = self.wheel_profile.wheel_names()

        self.cleanup = cleanup
        self.build_itk_tarball_cache = build_itk_tarball_cache
        self.dist_dir = dist_dir
        # Needed for processing remote modules and their dependencies
        self.module_source_dir: Path | None = (
            Path(module_source_dir) if module_source_dir else None
        )
        self.module_dependencies_root_dir: Path | None = (
            Path(module_dependencies_root_dir) if module_dependencies_root_dir else None
        )
        self.itk_module_deps = itk_module_deps
        self.skip_itk_build = skip_itk_build
        self.skip_itk_wheel_build = skip_itk_wheel_build
        self.prepare_build_env()

        self.cmake_cmdline_definitions: CMakeArgumentBuilder = (
            definitions_from_cmake_options(cmake_options or [])
        )

        self.cmake_compiler_configurations.update(
            {
                "CMAKE_BUILD_TYPE:STRING": BUILD_TYPE,
            }
        )

        self.compiler_cache_commands: tuple[list[list[str]], list[list[str]]] = (
            [],
            [],
        )
        compile_roots = (self.ipp_dir, self.build_dir_root, config.itk_source_dir)
        if config.use_ccache:
            cache_tool = compiler_cache_tool(self.target.os_name)
            cache_exe: Path | None = which(cache_tool)
            if cache_exe is None:
                msg = f"{cache_tool} was requested but is not on PATH"
                raise RuntimeError(msg)
            self.cmake_compiler_configurations.update(
                compiler_cache_definitions(cache_tool, cache_exe)
            )
            os.environ.update(
                compiler_cache_size_setting(cache_tool, cache_exe, os.environ)
            )
            os.environ.update(
                compiler_cache_environment(cache_tool, os.environ, compile_roots)
            )
            self.compiler_cache_commands = compiler_cache_session(
                cache_tool,
                cache_exe,
                compiler_cache_max_size(cache_tool, os.environ),
            )

        user_defs = self.cmake_cmdline_definitions
        flag_defs = self.compiler_flag_definitions(user_defs, compile_roots)
        if config.dead_strip:
            flag_defs.update(
                dead_strip_cmake_definitions(self.target.os_name, os.environ, user_defs)
            )
        flag_defs.update(self.lto_link_definitions(flag_defs))
        self.cmake_compiler_configurations.update(flag_defs)
        self.cmake_compiler_configurations.update(
            job_pool_definitions(self.build_node_cpu_count, self.build_link_jobs)
        )
        # Command-line definitions are applied last, so carry the merged value there.
        for key, value in flag_defs.items():
            user_key = user_flag_key(user_defs, key.split(":")[0])
            if user_key:
                user_defs.set(user_key, value)

        self.cmake_itk_source_build_configurations.update(
            itk_source_build_configuration(config, self.tbb_dir)
        )
        self.enable_ingested_remote_modules()

    def enable_ingested_remote_modules(self) -> None:
        """Turn on the ingested remote modules in the ITK build configuration."""
        self.cmake_itk_source_build_configurations.update(
            {
                f"Module_{module}:BOOL": "ON"
                for module in self.wheel_profile.ingested_remote_modules
            }
        )

    def update_venv_itk_build_configurations(self) -> None:
        """Set ``Python3_ROOT_DIR`` in ITK build configurations from the Python environment."""
        # Guides ITK's find_package(Python3) to the build environment's interpreter.
        self.cmake_itk_source_build_configurations.set(
            "Python3_ROOT_DIR:PATH", f"{self.python_env.root_dir}"
        )

    def build_step_table(self) -> OrderedDict[str, Callable[[], object]]:
        """The ordered build steps for this run, keyed by recorded step name.

        Stages that do not apply are registered under a ``_skipped`` key
        mapped to a no-op, so the step log records that they were bypassed
        on purpose rather than silently absent.
        """
        python_package_build_steps: OrderedDict[str, Callable[[], object]] = (
            OrderedDict(
                {
                    "01_superbuild_support_components": self.build_superbuild_support_components,
                    "02_build_wrapped_itk_cplusplus": self.build_wrapped_itk_cplusplus,
                    "03_build_wheels": self.build_itk_python_wheels,
                    "04_post_build_fixup": self.post_build_fixup,
                    "05_final_import_test": self.final_import_test,
                }
            )
        )

        if self.skip_itk_build:
            # ITK is already built (restored from a cache or installed).
            python_package_build_steps = skip_steps(
                python_package_build_steps, {"02_build_wrapped_itk_cplusplus"}
            )
        if self.skip_itk_wheel_build:
            # Steps 04 and 05 repair and install the ITK wheels from step 03.
            python_package_build_steps = skip_steps(
                python_package_build_steps,
                {"03_build_wheels", "04_post_build_fixup", "05_final_import_test"},
            )

        if self.module_source_dir is not None:
            # Only a module build consumes the install tree.
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
                f"07_build_itk_tarball_cache_{self.config.target.os_name.value}_{self.config.pixi_suffix}"
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

        if self.itk_module_deps:
            build_module_dependencies(
                itk_module_deps=self.itk_module_deps,
                module_source_dir=self.required_module_source_dir(),
                module_dependencies_root_dir=self.module_dependencies_root_dir,
                run=self.echo_check_call,
                build_module=self.build_dependency_module,
            )

        python_package_build_steps = self.build_step_table()

        self.dist_dir.mkdir(parents=True, exist_ok=True)
        build_report_fn: Path = self.build_report_path()
        build_manager: BuildManager = BuildManager(
            build_report_fn,
            list(python_package_build_steps.keys()),
            self.build_inputs(),
        )
        if build_manager.changed_inputs:
            print(
                f"Build inputs changed ({', '.join(build_manager.changed_inputs)}) "
                f"since {build_report_fn} was written: running every step."
            )
        build_manager.save()
        cache_before, cache_after = self.compiler_cache_commands
        for cmd in cache_before:
            self.echo_check_call(cmd, use_pixi_env=False)
        try:
            self._run_build_steps(
                build_manager, build_report_fn, python_package_build_steps
            )
        finally:
            # Statistics are informational: a failure here must not mask the build's.
            for cmd in cache_after:
                self.echo_check_call(cmd, use_pixi_env=False)

    def build_report_path(self) -> Path:
        """Return the step report; each module's is apart from the ITK build's."""
        name = f"build_log_{self.platform_env}"
        if self.module_source_dir is not None:
            name += f"_{Path(self.module_source_dir).name}"
        return self.dist_dir / f"{name}.json"

    def build_dependency_module(self, module_source_dir: Path) -> None:
        """Build the wheel of a dependency module with a copy of this builder."""
        dependency_build = self.clone()
        dependency_build.module_source_dir = module_source_dir
        dependency_build.itk_module_deps = None  # Prevent recursion
        dependency_build.run()

    def build_inputs(self) -> dict[str, str]:
        """Return the ITK commit, package version, and fingerprint of this build."""
        cfg = self.config.to_environment()
        settings: dict[str, str] = {}
        for group, definitions in (
            ("compiler", self.cmake_compiler_configurations),
            ("itk", self.cmake_itk_source_build_configurations),
            ("cmdline", self.cmake_cmdline_definitions),
        ):
            settings.update({f"{group}:{k}": str(v) for k, v in definitions.items()})
        for key in ("USE_CCACHE", "MANYLINUX_VERSION", "CONTAINER_SOURCE"):
            settings[key] = cfg.get(key, "")
        # The platform builders' wheel repair options.
        for option in (
            "windows_extra_lib_paths",
            "windows_exclude_libs",
            "exclude_libs",
        ):
            settings[option] = str(getattr(self, option, ""))
        git = str(self.config.git_executable)
        module_state = None
        if self.module_source_dir is not None:
            settings["itk_module_deps"] = str(self.itk_module_deps or "")
            settings["module_itk_dir"] = self.module_itk_dir
            module_state = module_source_state(Path(self.module_source_dir), git)
        return build_inputs(
            itk_commit=resolved_itk_commit(
                self.config.itk_source_dir, self.config.itk_git_tag, git
            ),
            package_version=self.config.itk_package_version,
            fingerprint=build_fingerprint(self.ipp_dir, settings),
            module_state=module_state,
        )

    def _run_build_steps(
        self,
        build_manager: BuildManager,
        build_report_fn: Path,
        python_package_build_steps: OrderedDict[str, Callable[[], object]],
    ) -> None:
        """Run each build step in order, recording its status in the report."""
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

    def build_superbuild_support_components(self) -> None:
        """Configure and build the superbuild support components (ITK source, TBB)."""
        cmake_superbuild_arguments = CMakeArgumentBuilder()
        cmake_superbuild_arguments.update(self.cmake_compiler_configurations.items())
        cmake_superbuild_arguments.update(
            {
                "ITKPythonPackage_USE_TBB:BOOL": use_tbb_setting(self.tbb_dir),
                "ITK_SOURCE_DIR:PATH": f"{self.config.itk_source_dir}",
                "ITK_GIT_TAG:STRING": f"{self.config.itk_git_tag}",
            }
        )
        # Command-line definitions go last so they override the defaults above.
        cmake_superbuild_arguments.update(self.cmake_cmdline_definitions.items())

        cmd: list[str | Path] = [
            self.config.cmake_executable,
            "-G",
            "Ninja",
        ]

        cmd += cmake_superbuild_arguments.cmake_command_line_arguments()

        cmd += [
            "-S",
            str(self.ipp_dir / "SuperbuildSupport"),
            "-B",
            str(self.config.ipp_superbuild_binary_dir),
        ]

        self.echo_check_call(cmd, check=True)
        # check=True so a failed superbuild stops here, not later in step 02.
        self.echo_check_call(
            [
                self.config.cmake_executable,
                "--build",
                str(self.config.ipp_superbuild_binary_dir),
            ],
            check=True,
        )

    def required_module_source_dir(self) -> Path:
        """Return the remote module's source directory, which must be set."""
        if self.module_source_dir is None:
            msg = "A remote module wheel needs module_source_dir"
            raise RuntimeError(msg)
        return Path(self.module_source_dir)

    def module_dist_dir(self) -> Path:
        """Return the remote module's ``dist/`` directory."""
        return self.required_module_source_dir() / "dist"

    def _repair_output_dir(self, remote_module_wheel: bool) -> Path:
        """Return where a repaired wheel goes: the module's or the main ``dist/``."""
        return (
            self.module_dist_dir()
            if remote_module_wheel
            else self.build_dir_root / "dist"
        )

    def _require_repaired(
        self, tool: str, source: Path, status: int, expected: Path, shown: str
    ) -> None:
        """Raise unless *tool* exited 0 and wrote the *expected* wheel."""
        if status != 0 or not expected.exists():
            msg = (
                f"{tool} repair failed for {source.name} "
                f"(exit status {status}, expected output {shown})"
            )
            raise RuntimeError(msg)

    def final_wheel_import_test(self, installed_dist_dir: Path) -> None:
        """Install and smoke-test all ITK wheels from *installed_dist_dir*.

        Parameters
        ----------
        installed_dist_dir : Path
            Directory containing the built ``.whl`` files to install and
            verify.
        """
        python = self.config.python_executable
        self._pip_uninstall_itk_wildcard(python)
        checks: list[tuple[str, list[str | Path]]] = [
            (
                "pip install itk",
                [
                    python,
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
                [python, "-c", "import itk;"],
            ),
            (
                "instantiate itk.Image",
                [
                    python,
                    "-c",
                    "import itk; image = itk.Image[itk.UC, 2].New()",
                ],
            ),
            (
                "import itk with lazy loading disabled",
                [
                    python,
                    "-c",
                    "import itkConfig; itkConfig.LazyLoading=False; import itk;",
                ],
            ),
            (
                "documentation tests",
                [
                    python,
                    str(self.ipp_dir / "docs" / "code" / "test.py"),
                ],
            ),
        ]
        for description, cmd in checks:
            exit_status = self.echo_check_call(cmd)
            if exit_status != 0:
                msg = (
                    f"final_wheel_import_test failed at step {description!r} "
                    f"(exit status {exit_status})"
                )
                raise RuntimeError(msg)
        print("Documentation tests passed.")

    def _pip_uninstall_itk_wildcard(self, python_executable: str | Path) -> None:
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
        for raw_line in proc.stdout.splitlines():
            line = raw_line.strip()
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
                msg = (
                    f"Failed to uninstall existing ITK packages {packages!r} "
                    f"(exit status {exit_status})"
                )
                raise RuntimeError(msg)

    def clone(self) -> "BuildPythonInstanceBase":
        """Return a deep copy of this instance for building a dependency.

        Uses ``self.__class__`` so the returned object is the same concrete
        subclass as the original (e.g. ``LinuxBuildPythonInstance``).
        """
        cls = self.__class__
        new = cls.__new__(cls)
        new.__dict__ = copy.deepcopy(self.__dict__)
        return new

    @abstractmethod
    def venv_paths(self) -> PythonEnvironment:
        """Return the pixi-managed Python environment the wheels build against."""

    @abstractmethod
    def fixup_wheel(self, filepath: str) -> None:  # pragma: no cover - abstract
        """Apply platform-specific wheel repairs (auditwheel, delocate, delvewheel).

        Parameters
        ----------
        filepath : str
            Path to the ``.whl`` file to fix.
        """

    def fixup_module_wheel(self, filepath: str) -> None:
        """Repair a remote module's wheel; by default as an ITK wheel is."""
        self.fixup_wheel(filepath)

    @abstractmethod
    def build_tarball(self) -> None:
        """Create a compressed archive of the ITK build tree for caching."""
        pass

    def post_build_cleanup(self) -> None:
        """Remove intermediate build artifacts, leaving ``dist/`` intact."""
        wheel_packaging.post_build_cleanup(
            build_dir_root=self.build_dir_root,
            arch=self.config.pixi_suffix,
            ipp_source_dir=self.ipp_dir,
            module_preq=self.config.itk_module_preq
            or os.environ.get("ITK_MODULE_PREQ", ""),
        )

    def prepare_build_env(self) -> None:
        """Skeleton shared by every platform.

        Subclasses vary only in ``uses_tbb`` and ``_configure_toolchain``.
        """
        self.python_env = self.venv_paths()
        self.update_venv_itk_build_configurations()
        self._configure_tbb()
        self._configure_toolchain()

        itk_binary_build_name = (
            self.build_dir_root
            / "build"
            / (f"ITK-{self.platform_env}-{self.platform_env}_{self.target.pixi_suffix}")
        )
        self.cmake_itk_source_build_configurations.set(
            "ITK_BINARY_DIR:PATH", itk_binary_build_name.as_posix()
        )

    @property
    def _tbb_prefix(self) -> Path:
        """Return the oneTBB install prefix the support superbuild creates."""
        return Path(self.build_dir_root) / "build" / "oneTBB-prefix"

    def _configure_tbb(self) -> None:
        """Set ``tbb_dir`` from ``uses_tbb``."""
        self.tbb_dir = (
            self._tbb_prefix / "lib" / "cmake" / "TBB" if self.uses_tbb else None
        )

    def subprocess_environment(self) -> dict[str, str]:
        """The build settings as environment variables, with this builder's own."""
        return {
            **self.config.to_environment(),
            "IPP_SOURCE_DIR": str(self.ipp_dir),
            "IPP_BuildWheelsSupport_DIR": str(self.ipp_dir / "BuildWheelsSupport"),
            "USE_TBB": use_tbb_setting(self.tbb_dir),
            "TBB_DIR": tbb_dir_setting(self.tbb_dir),
            "BUILD_TYPE": BUILD_TYPE,
        }

    def python_build_wheel_command(self, out_dir: Path, *settings: str) -> list[str]:
        """Return the ``python -m build`` command writing a wheel to *out_dir*.

        *settings* are extra ``--config-setting`` arguments placed before the
        generator choice; callers append CMake definitions and the source.
        """
        return [
            str(self.config.python_executable),
            "-m",
            "build",
            "--verbose",
            "--wheel",
            "--outdir",
            str(out_dir),
            "--no-isolation",
            "--skip-dependency-check",
            f"--config-setting=cmake.build-type={BUILD_TYPE}",
            *settings,
            *self.python_build_generator_args(),
        ]

    def python_build_generator_args(self) -> list[str]:
        """Extra ``python -m build`` settings choosing the CMake generator."""
        return []

    def compiler_flag_definitions(
        self, user_defs: CMakeArgumentBuilder, compile_roots: Sequence[Path]
    ) -> dict[str, str]:
        """Return the ``CMAKE_<LANG>_FLAGS`` definitions this platform adds."""
        return {}

    def caps_lto_jobs(self) -> bool:
        """True when the toolchain takes GCC's ``-flto=<n>`` at link time."""
        return False

    def lto_link_definitions(self, flag_defs: Mapping[str, str]) -> dict[str, str]:
        """Linker flags that cap each link's LTRANS processes, when capped at all."""
        if self.build_link_jobs <= 0 or not self.caps_lto_jobs():
            return {}
        return lto_jobs_definitions(
            compute_lto_jobs(self.build_node_cpu_count, self.build_link_jobs),
            flag_defs,
        )

    @abstractmethod
    def _configure_toolchain(self) -> None:  # pragma: no cover - abstract
        """Set platform-specific compiler and deployment values."""

    @abstractmethod
    def post_build_fixup(self) -> None:  # pragma: no cover - abstract
        """Run platform-specific post-build wheel fixups.

        Called after all wheels are built but before the final import
        test. Typically invokes ``fixup_wheel``.
        """
        pass

    def final_import_test(self) -> None:  # pragma: no cover
        """Install and smoke-test the built wheels."""
        self.check_wheel_sizes(self.dist_dir)
        wheel_dependency_audit.check([self.dist_dir], self.wheel_names)
        self.final_wheel_import_test(installed_dist_dir=self.dist_dir)

    def check_wheel_sizes(self, dist_dir: Path) -> None:
        """Fail when a wheel in *dist_dir* is too large to upload to PyPI."""
        oversized = [
            f"{wheel.name}: {wheel.stat().st_size / 1e6:.1f} MB"
            for wheel in sorted(Path(dist_dir).glob("itk*.whl"))
            if wheel.stat().st_size > PYPI_MAX_WHEEL_BYTES
        ]
        if oversized:
            msg = (
                f"Wheels over the {PYPI_MAX_WHEEL_BYTES / 1e6:.0f} MB PyPI "
                f"limit: {'; '.join(oversized)}. Move modules to another "
                f"wheel in BuildWheelsSupport/{self.wheel_profile.name}/wheel_groups.cmake."
            )
            raise RuntimeError(msg)

    def build_external_module_python_wheel(self) -> None:
        """Build a wheel for an external ITK remote module via scikit-build-core."""
        self.module_source_dir = self.required_module_source_dir()
        out_dir = self.module_source_dir / "dist"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Pin ITK dependencies to the version being built; the backup restores the file.
        module_pyproject = self.module_source_dir / "pyproject.toml"
        pyproject_orig = module_pyproject.with_suffix(".toml.orig")
        pyproject_built = module_pyproject.with_suffix(".toml.built")
        deps_rewritten = False
        if module_pyproject.is_file():
            itk_ver = self.config.itk_package_version
            if itk_ver:
                shutil.copy2(module_pyproject, pyproject_orig)
                deps_rewritten = update_module_itk_deps(module_pyproject, itk_ver)
                if not deps_rewritten:
                    pyproject_orig.unlink()

        py_exe = str(self.config.python_executable)

        py_include = str(self.python_env.include_dir)

        # ITK_DIR for the external module: the install tree when asked for,
        # otherwise the configured ITK build tree.
        if self.module_itk_dir == "install":
            itk_build_path = self.installed_itk_dir().as_posix()
        else:
            itk_build_path = (
                self.cmake_itk_source_build_configurations.get("ITK_BINARY_DIR:PATH")
                or ""
            )

        wheel_py_api = STABLE_ABI_TAG

        # A fresh directory keeps wheels left in dist/ out of verification and repair.
        fresh_dir = Path(tempfile.mkdtemp(prefix=".build-", dir=out_dir))
        cmd = self.python_build_wheel_command(fresh_dir)

        # Collect scikit-build CMake definitions
        defs = CMakeArgumentBuilder()
        defs.update(self.cmake_compiler_configurations.items())

        # Required defines for external module build
        if itk_build_path:
            defs.set("ITK_DIR:PATH", str(itk_build_path))
        defs.set("CMAKE_INSTALL_LIBDIR:STRING", "lib")
        defs.set("WRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING", "PythonWheel")
        defs.set("PY_SITE_PACKAGES_PATH:PATH", ".")
        defs.set("BUILD_TESTING:BOOL", "OFF")
        defs.set("Python3_EXECUTABLE:FILEPATH", py_exe)
        defs.set("Python3_INCLUDE_DIR:PATH", py_include)

        # Pass Python library paths when explicitly known (Windows)
        if self.python_env.library is not None:
            defs.set("Python3_LIBRARY:FILEPATH", str(self.python_env.library))
        if self.python_env.sabi_library is not None:
            defs.set("Python3_SABI_LIBRARY:FILEPATH", str(self.python_env.sabi_library))

        # Allow command-line cmake -D overrides to win last
        defs.update(self.cmake_cmdline_definitions.items())

        # Append all cmake.define entries to the build cmd
        cmd += defs.python_build_command_line_arguments()

        # Stable ABI setting if applicable
        if wheel_py_api:
            cmd += [f"--config-setting=wheel.py-api={wheel_py_api}"]

        # Module source directory to build
        cmd += [str(self.module_source_dir)]

        try:
            self.echo_check_call(cmd, check=True)

            built_wheels = [
                wheel.replace(out_dir / wheel.name)
                for wheel in verify_stable_abi_wheels(fresh_dir, wheel_py_api)
            ]

            # Repair the module wheels (auditwheel, delocate, or delvewheel).
            for wheel in built_wheels:
                self.fixup_module_wheel(str(wheel))
        finally:
            shutil.rmtree(fresh_dir, ignore_errors=True)
            # Restore original pyproject.toml so the working tree stays clean
            if deps_rewritten and pyproject_orig.is_file():
                shutil.copy2(module_pyproject, pyproject_built)
                shutil.move(str(pyproject_orig), str(module_pyproject))
                print(
                    f"Restored {module_pyproject} "
                    f"(modified version saved as {pyproject_built.name})"
                )

    def build_itk_python_wheels(self) -> None:
        """Build every ITK Python wheel of the wheel profile."""
        earlier = wheel_packaging.move_earlier_wheels(
            self.build_dir_root / "dist", datetime.now().strftime("%Y%m%d_%H%M%S")
        )
        if earlier:
            print(f"Moved wheels of an earlier run to {earlier}")
        for wheel_name in self.wheel_names:
            print("#")
            print(f"# Build ITK wheel {wheel_name} from {self.wheel_names}")
            print("#")
            # Configure pyproject.toml
            wheel_configbuild_dir_root: Path = (
                self.build_dir_root
                / "wheelbuilds"
                / f"{wheel_name}_{self.platform_env}"
            )
            wheel_configbuild_dir_root.mkdir(parents=True, exist_ok=True)
            configure_one_pyproject_file(
                str(self.ipp_dir / "scripts"),
                PyprojectInputs(
                    itk_source_dir=self.config.itk_source_dir,
                    itk_git_tag=self.config.itk_git_tag,
                    itk_package_version=self.config.itk_package_version,
                ),
                wheel_configbuild_dir_root,
                wheel_name,
            )

            cmd = self.python_build_wheel_command(
                self.build_dir_root / "dist",
                f"--config-setting=cmake.source-dir={self.ipp_dir / 'BuildWheelsSupport'}",
                f"--config-setting=build-dir={wheel_configbuild_dir_root / 'build'}",
            )
            # Build scikit-build defines via builder
            scikitbuild_cmdline_args = CMakeArgumentBuilder()
            scikitbuild_cmdline_args.update(self.cmake_compiler_configurations.items())
            scikitbuild_cmdline_args.update(
                self.cmake_itk_source_build_configurations.items()
            )
            scikitbuild_cmdline_args.update(
                {
                    "ITKPythonPackage_USE_TBB:BOOL": use_tbb_setting(self.tbb_dir),
                    "ITKPythonPackage_ITK_BINARY_REUSE:BOOL": "ON",
                    "ITKPythonPackage_WHEEL_NAME:STRING": f"{wheel_name}",
                    "ITKPythonPackage_WHEEL_PROFILE:STRING": self.wheel_profile.name,
                    "DOXYGEN_EXECUTABLE:FILEPATH": f"{self.config.doxygen_executable}",
                }
            )

            # Do last to override with command line items
            scikitbuild_cmdline_args.update(self.cmake_cmdline_definitions.items())
            cmd += scikitbuild_cmdline_args.python_build_command_line_arguments()
            # The location of the generated pyproject.toml file
            cmd += [str(wheel_configbuild_dir_root)]
            self.echo_check_call(cmd, check=True)

            # Remove unnecessary files for building against ITK
            if self.cleanup:
                bp = Path(
                    self.cmake_itk_source_build_configurations["ITK_BINARY_DIR:PATH"]
                )
                for p in bp.rglob("*"):
                    if p.is_file() and p.suffix in [".cpp", ".xml", ".obj", ".o"]:
                        with contextlib.suppress(OSError):
                            p.unlink()
                remove_tree(bp / "Wrapping" / "Generators" / "CastXML")

    def build_wrapped_itk_cplusplus(self) -> None:
        """Configure and build the ITK C++ libraries with Python wrapping."""
        # Clean up previous invocations
        if (
            self.cleanup
            and Path(
                self.cmake_itk_source_build_configurations["ITK_BINARY_DIR:PATH"]
            ).exists()
        ):
            remove_tree(
                Path(self.cmake_itk_source_build_configurations["ITK_BINARY_DIR:PATH"])
            )

        print("#")
        print("# START-Build ITK C++")
        print("#")

        # Build ITK python
        cmd: list[str | Path] = [
            self.config.cmake_executable,
            "-G",
            "Ninja",
        ]
        # Collect all -D definitions via builder
        defs = CMakeArgumentBuilder()
        defs.update(self.cmake_compiler_configurations.items())
        defs.update(self.cmake_itk_source_build_configurations.items())
        # NOTE Do cmake_cmdline_definitions last so they override internal defaults
        defs.update(self.cmake_cmdline_definitions.items())
        cmd += defs.cmake_command_line_arguments()
        cmd += [
            "-S",
            self.config.itk_source_dir,
            "-B",
            self.cmake_itk_source_build_configurations["ITK_BINARY_DIR:PATH"],
        ]
        self.echo_check_call(cmd, check=True)
        self.echo_check_call(
            [
                self.config.ninja_executable,
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
            msg = (
                f"No installed ITK under {prefix}: expected "
                f"lib/cmake/ITK-<version>/ITKConfig.cmake. The install step "
                f"(cmake --install <ITK build tree>) has not produced one."
            )
            raise RuntimeError(msg)
        itk_dir = configs[-1].parent
        required = ("ITKModuleExternal.cmake", "Wrapping/CMakeLists.txt")
        missing = [name for name in required if not (itk_dir / name).is_file()]
        if missing:
            msg = (
                f"Installed ITK at {itk_dir} cannot build a remote module: "
                f"missing {missing}. ITK must install its module build files "
                f"and wrapping infrastructure (configure with "
                f"ITK_INSTALL_WRAPPING_DEVELOPMENT_FILES=ON on an ITK that "
                f"supports it)."
            )
            raise RuntimeError(msg)
        return itk_dir

    def install_wrapped_itk_cplusplus(self) -> None:
        """Install the ITK build tree so a module can use it as ``ITK_DIR``."""
        prefix = self.itk_install_prefix()
        print("#")
        print(f"# START-Install ITK C++ -> {prefix}")
        print("#")
        self.echo_check_call(
            [
                self.config.cmake_executable,
                "--install",
                self.cmake_itk_source_build_configurations["ITK_BINARY_DIR:PATH"],
                "--prefix",
                str(prefix),
            ],
            check=True,
        )
        itk_dir = self.installed_itk_dir()
        print(f"# FINISHED-Install ITK C++: ITK_DIR={itk_dir}")

    def echo_check_call(
        self,
        cmd: Sequence[str | Path],
        use_pixi_env: bool = True,
        env: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> int:
        """Run *cmd* in this build's pixi environment, which is named after ``platform_env``."""
        return build_environment.echo_check_call(
            cmd,
            pixi_env_name=self.platform_env,
            pixi_executable=self.config.pixi_executable,
            run_dir=self.ipp_dir,
            use_pixi_env=use_pixi_env,
            env=env,
            **kwargs,
        )
