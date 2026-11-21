import contextlib
import copy
import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

import build_environment
import wheel_packaging
from build_environment import PythonEnvironment
from build_inputs import (
    build_fingerprint,
    build_inputs,
    module_source_state,
    resolved_itk_commit,
)
from build_jobs import compute_build_jobs, compute_load_limit, physical_memory_gb
from BuildManager import BuildManager
from cmake_argument_builder import CMakeArgumentBuilder, definitions_from_cmake_options
from compiler_cache import (
    compiler_cache_definitions,
    compiler_cache_environment,
    compiler_cache_max_size,
    compiler_cache_session,
    compiler_cache_tool,
)
from dead_strip import dead_strip_cmake_definitions, user_flag_key
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
        msg = f"No wheel was produced in {out_dir}"
        raise RuntimeError(msg)
    mistagged = [w.name for w in built_wheels if f"{py_api}-abi3" not in w.name]
    if mistagged:
        msg = f"Expected {py_api}-abi3 wheels, got: {', '.join(mistagged)}"
        raise RuntimeError(msg)
    return built_wheels


# PyPI rejects larger files.
PYPI_MAX_WHEEL_BYTES: int = 100 * 1000 * 1000

# ITK modules ingested from remote modules. ITK excludes them from its default
# build; the wheels ship them. Override one with -DModule_<name>:BOOL=OFF.
ITK_INGESTED_REMOTE_MODULES: tuple[str, ...] = (
    "AdaptiveDenoising",
    "AnisotropicDiffusionLBR",
    "BoneEnhancement",
    "BoneMorphometry",
    "BSplineGradient",
    "Cuberille",
    "FastBilateral",
    "FixedPointInverseDisplacementField",
    "Fpfh",
    "GenericLabelInterpolator",
    "GrowCut",
    "HigherOrderAccurateGradient",
    "IOFDF",
    "IOMeshMZ3",
    "IOMeshSTL",
    "IOMeshSWC",
    "IOScanco",
    "IOTransformDCMTK",
    "IsotropicWavelets",
    "LabelErodeDilate",
    "MGHIO",
    "MeshNoise",
    "MeshToPolyData",
    "MinimalPathExtraction",
    "Montage",
    "MorphologicalContourInterpolation",
    "MultipleImageIterator",
    "ParabolicMorphology",
    "PhaseSymmetry",
    "PolarTransform",
    "PrincipalComponentsAnalysis",
    "RANSAC",
    "RLEImage",
    "SmoothingRecursiveYvvGaussianFilter",
    "SplitComponents",
    "Strain",
    "SubdivisionQuadEdgeMeshFilter",
    "TextureFeatures",
    "Thickness3D",
    "TotalVariation",
    "TwoProjectionRegistration",
    "VariationalRegistration",
)


def itk_source_build_configuration(
    package_env_config: Mapping[str, Any],
) -> dict[str, str]:
    """Return the CMake definitions every ITK wrapping build is configured with."""
    return {
        "ITK_SOURCE_DIR:PATH": f"{package_env_config['ITK_SOURCE_DIR']}",
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
        "DOXYGEN_EXECUTABLE:FILEPATH": f"{package_env_config['DOXYGEN_EXECUTABLE']}",
        "Module_ITKTBB:BOOL": package_env_config["USE_TBB"],
        "TBB_DIR:PATH": package_env_config["TBB_DIR"],
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
    #: Class-level default for instances built without ``__init__`` (test fixtures).
    module_itk_dir: str = "build"
    uses_tbb: bool = True
    python_env: PythonEnvironment

    def __init__(
        self,
        *,
        platform_env,
        build_dir_root,
        package_env_config: dict[str, Any],
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
        package_env_config["IPP_SOURCE_DIR"] = self.ipp_dir
        IPP_BuildWheelsSupport_DIR: Path = self.ipp_dir / "BuildWheelsSupport"
        package_env_config["IPP_BuildWheelsSupport_DIR"] = IPP_BuildWheelsSupport_DIR

        self.package_env_config = package_env_config
        self.target: TargetPlatform = TargetPlatform.detect(self.package_env_config)

        with (IPP_BuildWheelsSupport_DIR / "WHEEL_NAMES.txt").open(
            encoding="utf-8"
        ) as content:
            self.wheel_names = [wheel_name.strip() for wheel_name in content]
        del package_env_config

        self.cleanup = cleanup
        self.build_itk_tarball_cache = build_itk_tarball_cache
        self.cmake_options = cmake_options
        self.windows_extra_lib_paths = windows_extra_lib_paths
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

        self.package_env_config["BUILD_TYPE"] = "Release"
        self.cmake_cmdline_definitions: CMakeArgumentBuilder = (
            definitions_from_cmake_options(cmake_options or [])
        )

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

        self.compiler_cache_commands: tuple[list[list[str]], list[list[str]]] = (
            [],
            [],
        )
        if self.package_env_config.get("USE_CCACHE", "OFF") == "ON":
            cache_tool = compiler_cache_tool(self.target.os_name)
            cache_exe: Path | None = _which(cache_tool)
            if cache_exe is None:
                msg = f"{cache_tool} was requested but is not on PATH"
                raise RuntimeError(msg)
            self.cmake_compiler_configurations.update(
                compiler_cache_definitions(cache_tool, cache_exe)
            )
            os.environ.update(compiler_cache_environment(cache_tool, os.environ))
            self.compiler_cache_commands = compiler_cache_session(
                cache_tool,
                cache_exe,
                compiler_cache_max_size(cache_tool, os.environ),
            )

        if self.package_env_config.get("DEAD_STRIP", "OFF") == "ON":
            user_defs = self.cmake_cmdline_definitions
            dead_strip_defs = dead_strip_cmake_definitions(
                self.target.os_name, os.environ, user_defs
            )
            self.cmake_compiler_configurations.update(dead_strip_defs)
            # Command-line definitions are applied last, so carry the merged value there.
            for key, value in dead_strip_defs.items():
                user_key = user_flag_key(user_defs, key.split(":")[0])
                if user_key:
                    user_defs.set(user_key, value)

        self.cmake_itk_source_build_configurations.update(
            itk_source_build_configuration(self.package_env_config)
        )
        self.enable_ingested_remote_modules()

    def enable_ingested_remote_modules(self) -> None:
        """Turn on the ingested remote modules in the ITK build configuration."""
        self.cmake_itk_source_build_configurations.update(
            {f"Module_{module}:BOOL": "ON" for module in ITK_INGESTED_REMOTE_MODULES}
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

        if self.itk_module_deps:
            build_module_dependencies(self)

        python_package_build_steps = self.build_step_table()

        self.dist_dir.mkdir(parents=True, exist_ok=True)
        build_report_fn: Path = self.dist_dir / f"build_log_{self.platform_env}.json"
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

    def build_inputs(self) -> dict[str, str]:
        """Return the ITK commit, package version, and fingerprint of this build."""
        cfg = self.package_env_config
        settings: dict[str, str] = {}
        for group, definitions in (
            ("compiler", self.cmake_compiler_configurations),
            ("itk", self.cmake_itk_source_build_configurations),
            ("cmdline", self.cmake_cmdline_definitions),
        ):
            settings.update({f"{group}:{k}": str(v) for k, v in definitions.items()})
        for key in ("USE_CCACHE", "MANYLINUX_VERSION", "CONTAINER_SOURCE"):
            settings[key] = str(cfg.get(key, ""))
        git = str(cfg.get("GIT_EXECUTABLE") or "git")
        module_state = None
        if self.module_source_dir is not None:
            settings["itk_module_deps"] = str(self.itk_module_deps or "")
            module_state = module_source_state(Path(self.module_source_dir), git)
        return build_inputs(
            itk_commit=resolved_itk_commit(
                Path(cfg["ITK_SOURCE_DIR"]), str(cfg["ITK_GIT_TAG"]), git
            ),
            package_version=str(cfg["ITK_PACKAGE_VERSION"]),
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

    def build_superbuild_support_components(self):
        """Configure and build the superbuild support components (ITK source, TBB)."""
        cmake_superbuild_argumets = CMakeArgumentBuilder()
        cmake_superbuild_argumets.update(self.cmake_compiler_configurations.items())
        cmake_superbuild_argumets.update(
            {
                "ITKPythonPackage_USE_TBB:BOOL": self.package_env_config["USE_TBB"],
                "ITK_SOURCE_DIR:PATH": f"{self.package_env_config['ITK_SOURCE_DIR']}",
                "ITK_GIT_TAG:STRING": f"{self.package_env_config['ITK_GIT_TAG']}",
            }
        )
        # Command-line definitions go last so they override the defaults above.
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
        # check=True so a failed superbuild stops here, not later in step 02.
        self.echo_check_call(
            [
                self.package_env_config["CMAKE_EXECUTABLE"],
                "--build",
                str(self.package_env_config["IPP_SUPERBUILD_BINARY_DIR"]),
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
                msg = (
                    f"final_wheel_import_test failed at step {description!r} "
                    f"(exit status {exit_status})"
                )
                raise RuntimeError(msg)
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

    def clone(self):
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
    def build_tarball(self) -> None:
        """Create a compressed archive of the ITK build tree for caching."""
        pass

    def post_build_cleanup(self) -> None:
        """Remove intermediate build artifacts, leaving ``dist/`` intact."""
        wheel_packaging.post_build_cleanup(
            build_dir_root=self.build_dir_root,
            arch=self.package_env_config["ARCH"],
            ipp_source_dir=Path(self.package_env_config["IPP_SOURCE_DIR"]),
            module_preq=self.package_env_config.get("ITK_MODULE_PREQ")
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
            / (
                f"ITK-{self.platform_env}-{self.platform_env}"
                f"_{self.target.build_dir_suffix}"
            )
        )
        self.cmake_itk_source_build_configurations.set(
            "ITK_BINARY_DIR:PATH", itk_binary_build_name.as_posix()
        )

    @property
    def _tbb_prefix(self) -> Path:
        """Return the oneTBB install prefix the support superbuild creates."""
        return Path(self.build_dir_root) / "build" / "oneTBB-prefix"

    def _configure_tbb(self) -> None:
        """Set ``USE_TBB`` and ``TBB_DIR`` from ``uses_tbb``."""
        if self.uses_tbb:
            self.package_env_config["USE_TBB"] = "ON"
            self.package_env_config["TBB_DIR"] = str(
                self._tbb_prefix / "lib" / "cmake" / "TBB"
            )
        else:
            self.package_env_config["USE_TBB"] = "OFF"
            self.package_env_config["TBB_DIR"] = "NOT_FOUND"

    def python_build_wheel_command(self, out_dir: Path, *settings: str) -> list[str]:
        """Return the ``python -m build`` command writing a wheel to *out_dir*.

        *settings* are extra ``--config-setting`` arguments placed before the
        generator choice; callers append CMake definitions and the source.
        """
        return [
            str(self.package_env_config["PYTHON_EXECUTABLE"]),
            "-m",
            "build",
            "--verbose",
            "--wheel",
            "--outdir",
            str(out_dir),
            "--no-isolation",
            "--skip-dependency-check",
            f"--config-setting=cmake.build-type={self.package_env_config['BUILD_TYPE']}",
            *settings,
            *self.python_build_generator_args(),
        ]

    def python_build_generator_args(self) -> list[str]:
        """Extra ``python -m build`` settings choosing the CMake generator."""
        return []

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
                f"wheel in cmake/ITKPythonPackage_BuildWheels.cmake."
            )
            raise RuntimeError(msg)

    def build_external_module_python_wheel(self):
        """Build a wheel for an external ITK remote module via scikit-build-core."""
        self.module_source_dir = self.required_module_source_dir()
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
                if not deps_rewritten:
                    pyproject_orig.unlink()

        py_exe = str(self.package_env_config["PYTHON_EXECUTABLE"])  # Python3_EXECUTABLE

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

        cmd = self.python_build_wheel_command(out_dir)

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
        cmd += defs.getPythonBuildCommandLineArguments()

        # Stable ABI setting if applicable
        if wheel_py_api:
            cmd += [f"--config-setting=wheel.py-api={wheel_py_api}"]

        # Module source directory to build
        cmd += [str(self.module_source_dir)]

        try:
            self.echo_check_call(cmd, check=True)

            built_wheels = verify_stable_abi_wheels(out_dir, wheel_py_api)

            # Repair the module wheels (auditwheel, delocate, or delvewheel).
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
                self.package_env_config,
                wheel_configbuild_dir_root,
                wheel_name,
            )

            cmd = self.python_build_wheel_command(
                self.build_dir_root / "dist",
                f"--config-setting=cmake.source-dir={self.package_env_config['IPP_SOURCE_DIR'] / 'BuildWheelsSupport'}",
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
                    "ITKPythonPackage_USE_TBB:BOOL": self.package_env_config["USE_TBB"],
                    "ITKPythonPackage_ITK_BINARY_REUSE:BOOL": "ON",
                    "ITKPythonPackage_WHEEL_NAME:STRING": f"{wheel_name}",
                    "DOXYGEN_EXECUTABLE:FILEPATH": f"{self.package_env_config['DOXYGEN_EXECUTABLE']}",
                }
            )

            # Do last to override with command line items
            scikitbuild_cmdline_args.update(self.cmake_cmdline_definitions.items())
            cmd += scikitbuild_cmdline_args.getPythonBuildCommandLineArguments()
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

    def echo_check_call(
        self, cmd, use_pixi_env: bool = True, env=None, **kwargs
    ) -> int:
        """Run *cmd* in this build's pixi environment, which is named after ``platform_env``."""
        return build_environment.echo_check_call(
            cmd,
            pixi_env_name=self.platform_env,
            pixi_executable=self.package_env_config["PIXI_EXECUTABLE"],
            run_dir=self.ipp_dir,
            use_pixi_env=use_pixi_env,
            env=env,
            **kwargs,
        )
