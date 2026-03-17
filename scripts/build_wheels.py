#!/usr/bin/env python
import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

from wheel_builder_utils import (
    _which,
    compute_itk_package_version,
    default_manylinux,
    detect_platform,
    get_default_platform_build,
    resolve_oci_exe,
    run_commandLine_subprocess,
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
        Default ``"10.7"`` is outdated but provides backward
        compatibility.

    Returns
    -------
    dict[str, str]
        A mapping of active configuration keys to their values, sourced
        from environment variables with sensible defaults.
    """
    env_defaults: dict[str, str] = {
        "ITK_PACKAGE_VERSION": "auto",
        "ITK_MODULE_PREQ": "",
        "CMAKE_OPTIONS": "",
        "MANYLINUX_VERSION": "",
        "MACOSX_DEPLOYMENT_TARGET": "10.7",
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
    os_name, arch = detect_platform()
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
               linux-py310, linux-py311,
               manylinux228-py310, manylinux228-py311,
               windows-py310, windows-py311,
               macosx-py310, macosx-py311
            """
        ),
    )
    parser.add_argument(
        "--cleanup",
        dest="cleanup",
        action="store_true",
        help="""
        'ITK_MODULE_NO_CLEANUP': Option to skip cleanup steps.
         =1 <- Leave temporary build files in place after completion, 0 <- remove temporary build files
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
        - 'ITK_PACKAGE_VERSION' A valid PEP440 version string for the itk packages generated.
          The default is to automatically generate a PEP440 version automatically based on relative
          versioning from the latest tagged release.
          (in github action ITKRemoteModuleBuildTestPackage itk-wheel-tag is used to set this value)
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

    args = parser.parse_args()

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
    pixi_exec_path: Path = _which("pixi" + binary_ext)
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
    package_env_config["ARCH"] = arch

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

    run_commandLine_subprocess(
        ["git", "fetch", "--tags", "origin"],
        cwd=args.itk_source_dir,
        env=os.environ.copy(),
    )
    try:
        run_commandLine_subprocess(
            ["git", "checkout", args.itk_git_tag],
            cwd=args.itk_source_dir,
            env=os.environ.copy(),
        )
    except subprocess.CalledProcessError:
        print(f"WARNING: Failed to checkout {args.itk_git_tag}, reverting to 'main':")
        run_commandLine_subprocess(
            ["git", "checkout", "main"],
            cwd=args.itk_source_dir,
            env=os.environ.copy(),
        )

    if (
        args.itk_package_version == "auto"
        or args.itk_package_version is None
        or len(args.itk_package_version) == 0
    ):
        args.itk_package_version = os.environ.get(
            "ITK_PACKAGE_VERSION",
            compute_itk_package_version(
                args.itk_source_dir, args.itk_git_tag, pixi_exec_path, os.environ
            ),
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
    package_env_config["PIXI_EXECUTABLE"] = _which("pixi")
    package_env_config["CMAKE_EXECUTABLE"] = _which("cmake")
    package_env_config["NINJA_EXECUTABLE"] = _which("ninja")
    package_env_config["DOXYGEN_EXECUTABLE"] = _which("doxygen")
    package_env_config["GIT_EXECUTABLE"] = _which("git")

    # reliably find the python executable in pixi
    cmd = [
        package_env_config["PIXI_EXECUTABLE"],
        "run",
        "-e",
        args.platform_env,
        "python",
        "-c",
        "import sys; print(sys.executable)",
    ]
    package_env_config["PYTHON_EXECUTABLE"] = run_commandLine_subprocess(
        cmd, env=os.environ.copy()
    ).stdout.strip()

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

        # Manylinux/docker bits for Linux
        target_arch = os.environ.get("TARGET_ARCH") or arch

        manylinux_version: str = args.manylinux_version
        if manylinux_version and len(manylinux_version) > 0:
            if (
                os.environ.get("MANYLINUX_VERSION", manylinux_version)
                != manylinux_version
            ):
                print(
                    f"WARNING: environment variable MANYLINUX_VERSION={manylinux_version} is changed to command line value of {manylinux_version}."
                )
            package_env_config["MANYLINUX_VERSION"] = manylinux_version
            image_tag, manylinux_image_name, container_source = default_manylinux(
                manylinux_version, os_name, target_arch, os.environ.copy()
            )
            package_env_config["IMAGE_TAG"] = image_tag
            package_env_config["MANYLINUX_IMAGE_NAME"] = manylinux_image_name
            package_env_config["CONTAINER_SOURCE"] = container_source
            package_env_config["TARGET_ARCH"] = target_arch

            # Native builds without dockcross need a separate dist dir to avoid conflicts with manylinux
            # dist_dir = IPP_SOURCE_DIR / f"{platform}_dist"
            # For the aarch64 manylinux builds, the CROSS_TRIPLE environment variable is unset
            if os.environ.get("CROSS_TRIPLE", None) is None and target_arch not in (
                "arm64",
                "aarch64",
            ):
                msg: str = (
                    f"ERROR: MANYLINUX_VERSION={manylinux_version} and TARGET_ARCH={target_arch} but not building in dockcross."
                )
                raise RuntimeError(msg)

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
    )
    builder.run()


if __name__ == "__main__":
    build_wheels_main()
