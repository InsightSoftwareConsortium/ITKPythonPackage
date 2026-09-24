#!/usr/bin/env python
import argparse
import os
import shlex
import sys
from pathlib import Path

from target_platform import Arch, TargetPlatform
from wheel_builder_utils import (
    abort_if_wrong_pixi_environment,
    compute_itk_package_version,
    get_default_platform_build,
    resolve_oci_exe,
    run_commandLine_subprocess,
    which_required,
    which_required_in_pixi_env,
)


def remotemodulebuildandtestaction() -> dict[str, str]:
    """Collect GitHub Actions environment variables for remote module builds.

    The following environment variables are defined by the
    ``ITKRemoteModuleBuildTestPackageAction`` GitHub Action.  Variables
    marked *active* are read from the environment with a default
    fallback; those marked *not used* are documented here for
    cross-reference but are no longer consumed at runtime.

    Environment Variables
    ---------------------
    ITK_PACKAGE_VERSION : str  (active)
        PEP 440 version string for ITK packages.
        GitHub Action source: ``inputs.itk-wheel-tag``.
        Default ``"auto"`` triggers automatic version computation.
    ITKPYTHONPACKAGE_TAG : str  (not used — GitHub Actions scripts only)
        Git tag for ITKPythonPackage checkout.
        GitHub Action source: ``inputs.itk-python-package-tag``.
    ITKPYTHONPACKAGE_ORG : str  (not used — GitHub Actions scripts only)
        GitHub organization owning ITKPythonPackage.
        GitHub Action source: ``inputs.itk-python-package-org``.
    ITK_MODULE_PREQ : str  (active)
        Colon-delimited list of remote module dependencies.
        GitHub Action source: ``inputs.itk-module-deps``.
    CMAKE_OPTIONS : str  (active)
        Extra options forwarded to CMake.
        GitHub Action source: ``inputs.cmake-options``.
    MANYLINUX_PLATFORM : str  (not used — computed internally)
        Full manylinux platform string (e.g. ``"manylinux_2_28-x64"``).
        GitHub Action source: ``matrix.manylinux-platform``.
    MANYLINUX_VERSION : str  (active)
        Manylinux specification (e.g. ``"_2_28"``).  Historically
        computed as the first part of ``MANYLINUX_PLATFORM``.
    TARGET_ARCH : str  (not used — computed internally)
        Target architecture (e.g. ``"x64"``).  Historically computed
        as the second part of ``MANYLINUX_PLATFORM``.
    MACOSX_DEPLOYMENT_TARGET : str  (active)
        Minimum macOS version for wheel compatibility.
        GitHub Action source: ``inputs.macosx-deployment-target``.
        Default ``"14.0"`` matches the arm64-only macOS wheel target.

    Returns
    -------
    dict[str, str]
        A mapping of active configuration keys to their values, sourced
        from environment variables with sensible defaults.
    """
    env_defaults: dict[str, str] = {
        "ITK_PACKAGE_VERSION": "gitauto",
        "ITK_MODULE_PREQ": "",
        "CMAKE_OPTIONS": "",
        "MANYLINUX_VERSION": "",
        "MACOSX_DEPLOYMENT_TARGET": "14.0",
    }
    return {key: os.environ.get(key, default) for key, default in env_defaults.items()}


def in_pixi_env() -> bool:
    """Check whether the process is running inside a pixi environment.

    Returns
    -------
    bool
        True if both ``PIXI_ENVIRONMENT_NAME`` and ``PIXI_PROJECT_ROOT``
        are set in the environment.
    """
    return "PIXI_ENVIRONMENT_NAME" in os.environ and "PIXI_PROJECT_ROOT" in os.environ


def get_effective_command_line(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> str:
    """Reconstruct a reproducible command line from parsed arguments.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        The argument parser used to parse *args*.
    args : argparse.Namespace
        Parsed command-line arguments.

    Returns
    -------
    str
        A shell-safe command string suitable for logging or re-execution
        inside a pixi environment.
    """
    pixi_executable: str = os.environ.get("PIXI_EXE", "pixi")
    effective_command = [
        pixi_executable,
        "run",
        "-e",
        args.platform_env,
        "--",
        sys.executable,
        sys.argv[0],
    ]
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        dest = action.dest
        value = getattr(args, dest, None)
        if value is None:
            continue
        if action.option_strings:
            option_string = action.option_strings[0]
            if isinstance(action, argparse._StoreTrueAction):
                if value:
                    effective_command.append(option_string)
            elif isinstance(action, argparse._StoreFalseAction):
                if not value:
                    effective_command.append(option_string)
            else:
                if isinstance(value, list):
                    if value:
                        effective_command.append(option_string)
                        effective_command.extend([str(v) for v in value])
                else:
                    effective_command.append(option_string)
                    effective_command.append(str(value))
        else:
            if isinstance(value, list):
                effective_command.extend([str(v) for v in value])
            else:
                effective_command.append(str(value))
    return shlex.join(effective_command)


def build_wheels_main() -> None:
    """Entry point: parse arguments, configure, and run the wheel build."""
    # Pre-parse: the command line has not been read yet, so ambient
    # MANYLINUX_VERSION must not influence this resolution.
    target = TargetPlatform.detect(os.environ, manylinux_version="")
    os_name = target.os_name
    ipp_script_dir: Path = Path(__file__).parent
    ipp_dir: Path = ipp_script_dir.parent
    if (ipp_dir / ".pixi" / "bin").exists():
        os.environ["PATH"] = (
            str(ipp_dir / ".pixi" / "bin") + os.pathsep + os.environ["PATH"]
        )

    remote_module_build_dict = remotemodulebuildandtestaction()
    parser = argparse.ArgumentParser(
        description="Driver script to build ITK Python wheels."
    )
    parser.add_argument(
        "--platform-env",
        default=get_default_platform_build("py311"),
        help=(
            """A platform environment name or path:
               linux-py311,
               manylinux228-py311,
               windows-py311,
               macosx-py311
            """
        ),
    )
    parser.add_argument(
        "--cleanup",
        dest="cleanup",
        action="store_true",
        help="""
        Remove temporary build files (intermediate objects, generated
        sources, CastXML output) once the build completes. Omitted, the
        files are kept. Ignored when --build-itk-tarball-cache is given,
        because the cache step needs those files.
        """,
    )
    parser.add_argument(
        "--lib-paths",
        nargs=1,
        default="",
        help=(
            "Windows only: semicolon-delimited library directories for delvewheel to include in module wheel"
        ),
    )
    _cmake_options_default = remote_module_build_dict["CMAKE_OPTIONS"]
    parser.add_argument(
        "cmake_options",
        nargs="*",
        default=shlex.split(_cmake_options_default) if _cmake_options_default else [],
        help="Extra options to pass to CMake, e.g. -DBUILD_SHARED_LIBS:BOOL=OFF.\n"
        "   These will override defaults if duplicated",
    )
    parser.add_argument(
        "--module-source-dir",
        type=str,
        default=None,
        help="Path to the (remote) module source directory to build.",
    )
    parser.add_argument(
        "--module-dependencies-root-dir",
        type=str,
        default=None,
        help="Path to the root directory for module dependencies.\n"
        + "This is the path where a remote module dependencies (other remote modules)\n"
        + "are searched for, or automatically git cloned to.",
    )
    parser.add_argument(
        "--itk-module-deps",
        type=str,
        default=remote_module_build_dict["ITK_MODULE_PREQ"],
        help="Semicolon-delimited list of a remote modules dependencies.\n"
        + "'gitorg/repo@tag:gitorg/repo@tag:gitorg/repo@tag'\n"
        + "These are set in ITKRemoteModuleBuildTestPackageAction:itk-module-deps github actions."
        + "and were historically set as an environment variable ITK_MODULE_PREQ.",
    )

    parser.add_argument(
        "--build-itk-tarball-cache",
        dest="build_itk_tarball_cache",
        action="store_true",
        default=False,
        help="Build an uploadable tarball.  The tarball can be used as a cache for remote module builds.",
    )
    parser.add_argument(
        "--no-build-itk-tarball-cache",
        dest="build_itk_tarball_cache",
        action="store_false",
        help="Do not build an uploadable tarball.  The tarball can be used as a cache for remote module builds.",
    )

    # set the default build_dir_root to a very short path on Windows to avoid path too long errors
    default_build_dir_root = (
        ipp_dir.parent / "ITKPythonPackage-build"
        if os_name != "windows"
        else Path("C:/") / "BDR"
    )
    parser.add_argument(
        "--build-dir-root",
        type=str,
        default=f"{default_build_dir_root}",
        help="The root of the build resources.",
    )
    parser.add_argument(
        "--manylinux-version",
        type=str,
        default=remote_module_build_dict["MANYLINUX_VERSION"],
        help="default manylinux version (_2_28, _2_34, ...), if empty, build native linux instead of cross compiling",
    )

    parser.add_argument(
        "--itk-git-tag",
        type=str,
        default=os.environ.get(
            "ITK_GIT_TAG", os.environ.get("ITK_PACKAGE_VERSION", "main")
        ),
        help="""
        - 'ITK_GIT_TAG': Tag/branch/hash for the ITK source code to use in packaging.
           Which ITK git tag/hash/branch to use as reference for building wheels/modules
           https://github.com/InsightSoftwareConsortium/ITK.git@${ITK_GIT_TAG}
           Examples: v5.4.0, v5.2.1.post1, 0ffcaed12552, my-testing-branch
           See available release tags at https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/tags
        """,
    )

    # set the default build_dir_root to a very short path on Windows to avoid path too long errors
    default_itk_source_dir = (
        ipp_dir.parent / "ITKPythonPackage-build" / "ITK"
        if os_name != "windows"
        else Path("C:/") / "BDR" / "ITK"
    )
    parser.add_argument(
        "--itk-source-dir",
        type=str,
        default=os.environ.get("ITK_SOURCE_DIR", str(default_itk_source_dir)),
        help="""
        - 'ITK_SOURCE_DIR':  When building different 'flavor' of ITK python packages
          on a given platform, explicitly setting the ITK_SOURCE_DIR options allow to
          speed up source-code downloads by re-using an existing repository.
          If the requested directory does not exist, manually clone and checkout ${ITK_GIT_TAG}""",
    )

    parser.add_argument(
        "--itk-package-version",
        type=str,
        default=remote_module_build_dict["ITK_PACKAGE_VERSION"],
        help="""
        - 'ITK_PACKAGE_VERSION' A valid PEP440 version string for the itk packages
          generated, or 'gitauto' to derive one from the ITK source repository with
          git describe.
          Any other value is used as given, which is what a source tree restored from
          a build cache needs: such a tree carries no repository, so 'gitauto' cannot
          work there.
          (in github action ITKRemoteModuleBuildTestPackage itk-wheel-tag sets this)
       """,
    )

    if os_name == "darwin":
        parser.add_argument(
            "--macosx-deployment-target",
            type=str,
            default=remote_module_build_dict["MACOSX_DEPLOYMENT_TARGET"],
            help="""
            The MacOSX deployment target to use for building wheels.
             """,
        )

    parser.add_argument(
        "--use-sudo",
        action="store_true",
        dest="use_sudo",
        default=False,
        help="""
         - Enable if running docker requires sudo privileges
         """,
    )
    parser.add_argument(
        "--no-use-sudo",
        action="store_false",
        dest="use_sudo",
        help="""
         - Enable if running docker requires sudo privileges
         """,
    )

    parser.add_argument(
        "--use-ccache",
        action="store_true",
        dest="use_ccache",
        default=False,
        help="""
         -  Option to indicate that ccache should be used
         """,
    )
    parser.add_argument(
        "--no-use-ccache",
        action="store_false",
        dest="use_ccache",
        help="""
         -  Option to indicate that ccache should not be used
         """,
    )

    parser.add_argument(
        "--skip-itk-build",
        action="store_true",
        dest="skip_itk_build",
        default=False,
        help="""
         -  Option to skip the ITK C++ build step (Step 2)
         """,
    )

    parser.add_argument(
        "--no-skip-itk-build",
        action="store_false",
        dest="skip_itk_build",
        help="""
         -  Option to not skip the ITK C++ build step (Step 2)
         """,
    )

    parser.add_argument(
        "--skip-itk-wheel-build",
        action="store_true",
        dest="skip_itk_wheel_build",
        default=False,
        help="""
         -  Option to skip the ITK wheel build step (Step 3)
         """,
    )

    parser.add_argument(
        "--no-skip-itk-wheel-build",
        action="store_false",
        dest="skip_itk_wheel_build",
        help="""
         -  Option to not skip the ITK wheel build step (Step 3)
         """,
    )

    parser.add_argument(
        "--module-itk-dir",
        dest="module_itk_dir",
        choices=("build", "install"),
        default="build",
        help="""
         -  Which ITK tree a remote module (Step 6) is configured against.
            'build' (default) passes the ITK build tree as ITK_DIR.
            'install' first runs 'cmake --install' on that build tree and
            passes <prefix>/lib/cmake/ITK-<version> instead; it needs an ITK
            that installs its module build files and wrapping infrastructure
            (ITK_INSTALL_WRAPPING_DEVELOPMENT_FILES).
         """,
    )

    args = parser.parse_args()

    abort_if_wrong_pixi_environment(args.platform_env)

    # Dependencies are cloned here. A caller that names module dependencies but
    # leaves this empty would otherwise reach the clone step with None, so
    # derive it from the build root rather than failing there.
    if not args.module_dependencies_root_dir:
        args.module_dependencies_root_dir = (
            Path(args.build_dir_root) / "MODULE_DEPENDENCIES"
        )

    # Historical dist_dir name for compatibility with ITKRemoteModuleBuildTestPackageAction
    _ipp_dir_path: Path = Path(__file__).resolve().parent.parent
    dist_dir: Path = Path(args.build_dir_root) / "dist"

    # Platform detection
    binary_ext: str = ".exe" if os_name == "windows" else ""
    env_bin_dir: str = "Scripts" if os_name == "windows" else "bin"

    env_path = _ipp_dir_path / ".pixi" / "envs" / args.platform_env
    # multiple locations the executables can be at on Windows
    env_subdirs = (
        [env_bin_dir, "Library/bin"] if os_name == "windows" else [env_bin_dir]
    )

    os.environ["PATH"] = os.pathsep.join(
        [
            *[str(env_path / d) for d in env_subdirs],
            str(_ipp_dir_path / ".pixi" / "bin"),
            os.environ.get("PATH", ""),
        ]
    )
    pixi_exec_path: Path = which_required("pixi" + binary_ext)
    package_env_config: dict[str, str | Path | None] = {}

    args.build_dir_root = Path(args.build_dir_root)
    if str(args.build_dir_root) != str(default_build_dir_root) and str(
        args.itk_source_dir
    ) == str(default_itk_source_dir):
        args.itk_source_dir = args.build_dir_root / "ITK"

    args.itk_source_dir = Path(args.itk_source_dir)
    package_env_config["ITK_SOURCE_DIR"] = Path(args.itk_source_dir)

    ipp_superbuild_binary_dir: Path = args.build_dir_root / "build" / "ITK-support-bld"
    package_env_config["IPP_SUPERBUILD_BINARY_DIR"] = ipp_superbuild_binary_dir

    package_env_config["OS_NAME"] = os_name
    package_env_config["ARCH"] = target.pixi_suffix

    # ITK repo handling

    if not Path(args.itk_source_dir).exists():
        args.itk_source_dir.parent.mkdir(parents=True, exist_ok=True)
        print(f"Cloning ITK into {args.itk_source_dir}...")
        run_result = run_commandLine_subprocess(
            [
                "git",
                "clone",
                "https://github.com/InsightSoftwareConsortium/ITK.git",
                str(args.itk_source_dir),
            ],
            cwd=_ipp_dir_path,
            env=os.environ.copy(),
        )
        if run_result.returncode != 0:
            raise RuntimeError(f"Failed to clone ITK: {run_result.stderr}")

    # A tree restored from a build cache has no usable repository: the cache
    # excludes .git contents but keeps the directory, so ask git rather than
    # testing the path. Its sources already match the prebuilt binaries, so
    # there is nothing to fetch.
    itk_source_is_repository = (
        run_commandLine_subprocess(
            ["git", "rev-parse", "--git-dir"],
            cwd=args.itk_source_dir,
            env=os.environ.copy(),
        ).returncode
        == 0
    )
    if not itk_source_is_repository:
        print(
            f"WARNING: {args.itk_source_dir} is not a git repository; using "
            f"its sources as they are and not checking out "
            f"{args.itk_git_tag!r}."
        )
    else:
        fetch_result = run_commandLine_subprocess(
            ["git", "fetch", "--tags", "origin"],
            cwd=args.itk_source_dir,
            env=os.environ.copy(),
        )
        if fetch_result.returncode != 0:
            raise RuntimeError(
                f"Failed to fetch ITK tags in {args.itk_source_dir}: "
                f"{fetch_result.stderr}"
            )
        checkout_result = run_commandLine_subprocess(
            ["git", "checkout", args.itk_git_tag],
            cwd=args.itk_source_dir,
            env=os.environ.copy(),
        )
        if checkout_result.returncode != 0:
            # A failed checkout leaves HEAD untouched, so keep what is already
            # there rather than forcing 'main'. When the ITK tree is restored
            # from a build cache (--skip-itk-build), its commit matches the
            # prebuilt binaries; moving the source to 'main' silently
            # desynchronises the headers from the libraries compiled against
            # them. Remote-module builds hit this routinely, because
            # ITK_GIT_TAG defaults to ITK_PACKAGE_VERSION, which is an
            # ITKPythonBuilds release tag and never resolves inside ITK.
            head_result = run_commandLine_subprocess(
                ["git", "rev-parse", "HEAD"],
                cwd=args.itk_source_dir,
                env=os.environ.copy(),
            )
            resolved = head_result.stdout.strip() if head_result.returncode == 0 else ""
            print(
                f"WARNING: Failed to checkout {args.itk_git_tag}; keeping the "
                f"commit already checked out ({resolved or 'unknown'}): "
                f"{checkout_result.stderr}"
            )
            if resolved:
                args.itk_git_tag = resolved

    # 'gitauto' asks for the version to be derived from the source repository;
    # anything else is an override and is used as given. The override is what
    # makes a cache-restored source tree usable, since it carries no repository.
    # 'auto' is the former spelling of the sentinel.
    if args.itk_package_version in (None, "", "gitauto", "auto"):
        args.itk_package_version = compute_itk_package_version(
            args.itk_source_dir, args.itk_git_tag, pixi_exec_path, os.environ
        )

    # ITKPythonPackage origin/tag
    # NO_SUDO, ITK_MODULE_NO_CLEANUP, USE_CCACHE
    no_sudo = os.environ.get("NO_SUDO", "0")
    module_no_cleanup = os.environ.get("ITK_MODULE_NO_CLEANUP", "1")
    use_ccache = os.environ.get("USE_CCACHE", "0")

    package_env_config["BUILD_DIR_ROOT"] = str(args.build_dir_root)
    package_env_config["ITK_GIT_TAG"] = args.itk_git_tag
    package_env_config["ITK_SOURCE_DIR"] = args.itk_source_dir
    package_env_config["ITK_PACKAGE_VERSION"] = args.itk_package_version
    if os_name == "darwin":
        package_env_config["MACOSX_DEPLOYMENT_TARGET"] = args.macosx_deployment_target
    else:
        package_env_config["MACOSX_DEPLOYMENT_TARGET"] = "RELEVANT_FOR_MACOS_ONLY"
    package_env_config["ITK_MODULE_PREQ"] = args.itk_module_deps
    package_env_config["NO_SUDO"] = no_sudo
    package_env_config["ITK_MODULE_NO_CLEANUP"] = module_no_cleanup
    package_env_config["USE_CCACHE"] = use_ccache
    pixi_executable = which_required("pixi")
    package_env_config["PIXI_EXECUTABLE"] = pixi_executable
    # Build tools come from the target environment, not the launching one, so a
    # stray same-named executable on PATH cannot be handed to CMake.
    for config_key, tool_name in (
        ("CMAKE_EXECUTABLE", "cmake"),
        ("NINJA_EXECUTABLE", "ninja"),
        ("DOXYGEN_EXECUTABLE", "doxygen"),
        ("GIT_EXECUTABLE", "git"),
    ):
        package_env_config[config_key] = which_required_in_pixi_env(
            tool_name, pixi_executable, args.platform_env
        )

    # reliably find the python interpreter in pixi
    if os.environ.get("PIXI_ENVIRONMENT_NAME") == args.platform_env:
        # Already running inside the requested environment: the entry points
        # invoke this script via ``pixi run -e <env> python build_wheels.py``,
        # so sys.executable is the interpreter being probed for. Nesting a
        # second ``pixi run`` re-prepends the environment's directories to an
        # already-activated PATH, which on Windows overflows the cmd.exe
        # 8191-character line limit ("The input line is too long").
        package_env_config["PYTHON_EXECUTABLE"] = sys.executable
    else:
        cmd = [
            package_env_config["PIXI_EXECUTABLE"],
            "run",
            "-e",
            args.platform_env,
            "python",
            "-c",
            "import sys; print(sys.executable)",
        ]
        python_probe = run_commandLine_subprocess(cmd, env=os.environ.copy())
        if python_probe.returncode != 0 or not python_probe.stdout.strip():
            raise RuntimeError(
                f"Could not resolve the python interpreter for pixi environment "
                f"{args.platform_env!r}: {python_probe.stderr}"
            )
        package_env_config["PYTHON_EXECUTABLE"] = python_probe.stdout.strip()

    oci_exe = resolve_oci_exe(os.environ.copy())
    package_env_config["OCI_EXE"] = oci_exe
    del oci_exe

    # -------------
    platform = package_env_config["OS_NAME"].lower()
    if platform == "windows":
        from windows_build_python_instance import WindowsBuildPythonInstance

        builder_cls = WindowsBuildPythonInstance
    elif platform in ("darwin", "mac", "macos", "macosx", "osx"):
        from macos_build_python_instance import MacOSBuildPythonInstance

        builder_cls = MacOSBuildPythonInstance
    elif platform == "linux":
        from linux_build_python_instance import LinuxBuildPythonInstance

        # Manylinux/docker bits for Linux. The command line wins over the
        # environment, so pin it before the target is resolved.
        if args.manylinux_version:
            os.environ["MANYLINUX_VERSION"] = args.manylinux_version
        target = TargetPlatform.detect(os.environ)
        package_env_config["ARCH"] = target.pixi_suffix
        if args.manylinux_version:
            package_env_config["MANYLINUX_VERSION"] = args.manylinux_version
            image = target.container_image
            package_env_config["MANYLINUX_IMAGE_NAME"] = image.name
            package_env_config["CONTAINER_SOURCE"] = image.reference
            package_env_config["TARGET_ARCH"] = target.arch.value
            if (
                os.environ.get("CROSS_TRIPLE") is None
                and target.arch is not Arch.AARCH64
            ):
                raise RuntimeError(
                    f"ERROR: MANYLINUX_VERSION={args.manylinux_version} "
                    f"and TARGET_ARCH={target.arch.value} but not "
                    f"building in dockcross."
                )

        builder_cls = LinuxBuildPythonInstance
    else:
        raise ValueError(f"Unknown platform {platform}")

    print("=" * 80)
    print("=" * 80)
    print("= Building Wheels with effective command line")
    print("\n\n")
    cmdline: str = f"{get_effective_command_line(parser, args)}"
    args.build_dir_root.mkdir(parents=True, exist_ok=True)
    with open(
        args.build_dir_root / f"effective_cmdline_{args.platform_env}.sh", "w"
    ) as f:
        f.write("#!/bin/bash\n")
        f.write(
            "# Generated by build_wheels.py as documentation for describing how these wheels were created.\n"
        )
        f.write(cmdline)
        f.write("\n")
    print(f"cmdline: {cmdline}")
    print("\n\n\n\n")
    print("=" * 80)
    print("=" * 80)
    print(f"Building wheels for platform: {args.platform_env}")
    # Pass helper function callables and dist dir to avoid circular imports
    builder = builder_cls(
        platform_env=args.platform_env,
        build_dir_root=args.build_dir_root,
        package_env_config=package_env_config,
        cleanup=args.cleanup,
        build_itk_tarball_cache=args.build_itk_tarball_cache,
        cmake_options=args.cmake_options,
        windows_extra_lib_paths=args.lib_paths,
        dist_dir=dist_dir,
        module_source_dir=args.module_source_dir,
        module_dependencies_root_dir=args.module_dependencies_root_dir,
        itk_module_deps=args.itk_module_deps,
        skip_itk_build=args.skip_itk_build,
        skip_itk_wheel_build=args.skip_itk_wheel_build,
        module_itk_dir=args.module_itk_dir,
    )
    builder.run()


if __name__ == "__main__":
    build_wheels_main()
