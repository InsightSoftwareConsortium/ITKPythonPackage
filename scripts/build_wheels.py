#!/usr/bin/env python3
from __future__ import (
    annotations,
)  # Needed for python 3.9 to support python 3.10 style typehints

import os
import subprocess
import sys


from wheel_builder_utils import (
    detect_platform,
    run_commandLine_subprocess,
    default_manylinux,
    compute_itk_package_version,
    resolve_oci_exe,
)

if sys.version_info < (3, 9):
    sys.stderr.write(
        "Python 3.9+ required for the python packaging script execution.\n"
    )
    sys.exit(1)

import argparse
from pathlib import Path


def main() -> None:
    ipp_script_dir: Path = Path(__file__).parent
    parser = argparse.ArgumentParser(
        description="Driver script to build ITK Python wheels."
    )
    parser.add_argument(
        "--platform-env",
        nargs="+",
        default=None,
        help=(
            """A platform environment name or path: 
               linux-py39, linux-py310, linux-py311,
               manylinux228-py39, manylinux228-py310, manylinux228-py311,
               windows-py39, windows-py310, windows-py311,
               macos-py39, macos-py310, macos-py311
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
    parser.add_argument(
        "cmake_options",
        nargs="*",
        help="Extra options to pass to CMake, e.g. -DBUILD_SHARED_LIBS:BOOL=OFF.\n"
        "   These will override defaults if duplicated",
    )
    parser.add_argument(
        "--module-source-dir",
        type=Path,
        default=None,
        help="Path to the (remote) module source directory to build.",
    )
    parser.add_argument(
        "--module-dependencies-root-dir",
        type=Path,
        default=None,
        help="Path to the root directory for module dependencies.\n"
        + "This is the path where a remote module dependencies (other remote modules)\n"
        + "are searched for, or automatically git cloned to.",
    )
    parser.add_argument(
        "--itk-module-deps",
        type=str,
        default=None,
        help="Semicolon-delimited list of a remote modules dependencies.\n"
        + "'gitorg/repo@tag:gitorg/repo@tag:gitorg/repo@tag'\n"
        + "These are set in ITKRemoteModuleBuildTestPackageAction:itk-module-deps github actions."
        + "and were historically set as an environment variable ITK_MODULE_PREQ.",
    )
    parser.add_argument(
        "--build-itk-tarball-cache",
        dest="build_itk_tarball_cache",
        action="store_true",
        help="Build an uploadable tarball.  The tarball can be used as a cache for remote module builds.",
    )
    # parser.add_argument(
    #     "--package-env-file",
    #     type=str,
    #     default=f"",
    #     help=".env file with parameters used to control builds, default to build/package.env for native builds\n"
    #     + "and is commonly set to /work/dist/container_package.env for dockercross builds.",
    # )

    default_build_dir_root = Path(ipp_script_dir).parent / "ITKPythonPackage-build"
    parser.add_argument(
        "--build-dir-root",
        type=str,
        default=f"{default_build_dir_root}",
        help="The root of the build resources.",
    )
    parser.add_argument(
        "--manylinux-version",
        type=str,
        default="",
        help="default manylinux version, if empty, build native linux instead of cross compiling",
    )

    parser.add_argument(
        "--itk-git-tag",
        type=str,
        default=os.environ.get("ITK_GIT_TAG", "main"),
        help="""
        - 'ITK_GIT_TAG': Tag/branch/hash for the ITK source code to use in packaging.
           Which ITK git tag/hash/branch to use as reference for building wheels/modules
           https://github.com/InsightSoftwareConsortium/ITK.git@${ITK_GIT_TAG}
           Examples: v5.4.0, v5.2.1.post1, 0ffcaed12552, my-testing-branch
           See available release tags at https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/tags
        """,
    )

    parser.add_argument(
        "--itk-source-dir",
        type=str,
        default=os.environ.get("ITK_SOURCE_DIR", None),
        help="""
        - 'ITK_SOURCE_DIR':  When building different 'flavor' of ITK python packages
          on a given platform, explicitly setting the ITK_SOURCE_DIR options allow to
          speed up source-code downloads by re-using an existing repository.
          If the requested directory does not exist, manually clone and checkout ${ITK_GIT_TAG}""",
    )

    parser.add_argument(
        "--itk-package-version",
        type=str,
        default=None,
        help="""
        - 'ITK_PACKAGE_VERSION' A valid PEP440 version string for the itk packages generated.
          The default is to automatically generate a PEP440 version automatically based on relative
          versioning from the latest tagged release.
          (in github action ITKRemoteModuleBuildTestPackage itk-wheel-tag is used to set this value)
       """,
    )

    # parser.add_argument(
    #     "--itk-pythonpackage-org",
    #     type=str,
    #     default=None,
    #     help="""
    #      - 'ITKPYTHONPACKAGE_ORG':Github organization or user to use for ITKPythonPackage build scripts
    #        Which script version to use in generating python packages
    #        https://github.com/InsightSoftwareConsortium/${ITKPYTHONPACKAGE_ORG}/ITKPythonPackage.git@${ITKPYTHONPACKAGE_TAG}
    #        build script source. Default is InsightSoftwareConsortium.
    #        Ignored if ITKPYTHONPACKAGE_TAG is empty.
    #        (in github action ITKRemoteModuleBuildTestPackage itk-python-package-org is used to set this value)
    #      """,
    # )

    parser.add_argument(
        "--use-sudo",
        action="store_true",
        help="""
         - Enable if running docker requires sudo privileges
         """,
    )

    parser.add_argument(
        "--use-ccache",
        action="store_true",
        help="""
         -  Option to indicate that ccache should be used
         """,
    )

    args = parser.parse_args()
    print("=" * 80)
    print("=" * 80)
    print("= Building Wheels")
    print("=" * 80)
    print("=" * 80)

    package_env_config: dict[str, str | Path | None] = {}

    args.build_dir_root = Path(args.build_dir_root)
    if args.itk_source_dir is None:
        args.itk_source_dir = args.build_dir_root / "ITK-source" / "ITK"

    args.itk_source_dir = Path(args.itk_source_dir)
    package_env_config["ITK_SOURCE_DIR"] = Path(args.itk_source_dir)

    # Historical dist_dir name for compatibility with ITKRemoteModuleBuildTestPackageAction
    _ipp_dir_path: Path = Path(__file__).resolve().parent.parent
    dist_dir = args.build_dir_root / "dist"

    ipp_superbuild_binary_dir: Path = args.build_dir_root / "build" / "ITK-support-bld"
    package_env_config["IPP_SUPERBUILD_BINARY_DIR"] = ipp_superbuild_binary_dir

    os_name, arch = detect_platform()
    package_env_config["OS_NAME"] = os_name
    package_env_config["ARCH"] = arch

    # Set pixi home and pixi bin path
    pixi_home: Path = _ipp_dir_path / ".pixi"
    pixi_home.mkdir(parents=True, exist_ok=True)
    os.environ["PIXI_HOME"] = str(pixi_home)
    pixi_bin_path: Path = pixi_home / "bin"
    os.environ["PATH"] = str(pixi_bin_path) + os.pathsep + os.environ.get("PATH", "")

    # Platform detection
    os_name, arch = detect_platform()
    binary_ext: str = ".exe" if os_name == "windows" else ""

    pixi_bin_name: str = "pixi" + binary_ext
    # Attempt to find an existing pixi binary on the system first (cross-platform)
    pixi_exec_path: Path = pixi_bin_path / pixi_bin_name

    # If not found, we will install into the local build .pixi
    if pixi_exec_path.exists():
        print("Previous install of pixi will be used.")
    else:
        if os_name == "windows":

            # Use PowerShell to install pixi on Windows
            result = run_commandLine_subprocess(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    "irm -UseBasicParsing https://pixi.sh/install.ps1 | iex",
                ],
                env=os.environ.copy(),
            )
            if result.returncode != 0:
                raise RuntimeError(f"Failed to install pixi: {result.stderr}")
        else:
            pixi_install_script: Path = pixi_home / "pixi_install.sh"
            result = run_commandLine_subprocess(
                [
                    "curl",
                    "-fsSL",
                    "https://pixi.sh/install.sh",
                    "-o",
                    str(pixi_install_script),
                ]
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Failed to download {pixi_install_script}: {result.stderr}"
                )

            result = run_commandLine_subprocess(
                [
                    "/bin/sh",
                    str(pixi_install_script),
                ],
                env=os.environ.copy(),
            )
            if result.returncode != 0:
                raise RuntimeError(f"Failed to install pixi: {result.stderr}")
            del pixi_install_script

        if not pixi_exec_path.exists():
            raise RuntimeError(
                f"Failed to install {pixi_exec_path} pixi into {pixi_exec_path}"
            )

    # Required executables (paths recorded)
    platform_pixi_packages = ["doxygen", "ninja", "cmake"]
    if os_name == "linux":
        platform_pixi_packages += ["patchelf"]
    if os_name == "windows":
        # Git is not always available in PowerShell by default
        platform_pixi_packages += ["git"]

    missing_packages: list[str] = []

    for ppp in platform_pixi_packages:
        full_path: Path = pixi_exec_path / (ppp + binary_ext)
        if not full_path.is_file():
            missing_packages.append(ppp)
    if len(missing_packages) > 0:
        run_commandLine_subprocess(
            [
                pixi_exec_path,
                "global",
                "install",
            ]
            + platform_pixi_packages
        )

    # NOT NEEDED
    # ipp_latest_tag: str = get_git_id(
    #     _ipp_dir_path, pixi_exec_path, os.environ, os.environ.get("ITKPYTHONPACKAGE_TAG", "v0.0.0")
    # )

    # ITK repo handling

    if not args.itk_source_dir.exists():
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
        # try fetch then checkout
        print(f"WARNING: Failed to checkout {args.itk_git_tag}, reverting to 'main':")
        run_commandLine_subprocess(
            ["git", "checkout", args.itk_git_tag],
            cwd=args.itk_source_dir,
            env=os.environ.copy(),
        )

    itk_package_version: str = os.environ.get(
        "ITK_PACKAGE_VERSION",
        compute_itk_package_version(
            args.itk_source_dir, args.itk_git_tag, pixi_exec_path, os.environ
        ),
    )

    # ITKPythonPackage origin/tag
    # itkpp_org = os.environ.get("ITKPYTHONPACKAGE_ORG", "InsightSoftwareConsortium")
    # itkpp_tag = os.environ.get("ITKPYTHONPACKAGE_TAG", ipp_latest_tag)

    # NO_SUDO, ITK_MODULE_NO_CLEANUP, USE_CCACHE
    no_sudo = os.environ.get("NO_SUDO", "0")
    module_no_cleanup = os.environ.get("ITK_MODULE_NO_CLEANUP", "1")
    use_ccache = os.environ.get("USE_CCACHE", "0")
    itk_module_preq = os.environ.get("ITK_MODULE_PREQ", "")

    package_env_config["BUILD_DIR_ROOT"] = str(args.build_dir_root)
    package_env_config["ITK_GIT_TAG"] = args.itk_git_tag
    package_env_config["ITK_SOURCE_DIR"] = args.itk_source_dir
    package_env_config["ITK_PACKAGE_VERSION"] = itk_package_version
    # package_env_config["ITKPYTHONPACKAGE_ORG"] = itkpp_org
    # package_env_config["ITKPYTHONPACKAGE_TAG"] = itkpp_tag
    package_env_config["ITK_MODULE_PREQ"] = itk_module_preq
    package_env_config["NO_SUDO"] = no_sudo
    package_env_config["ITK_MODULE_NO_CLEANUP"] = module_no_cleanup
    package_env_config["USE_CCACHE"] = use_ccache
    package_env_config["PIXI_EXECUTABLE"] = pixi_bin_path / ("pixi" + binary_ext)
    package_env_config["CMAKE_EXECUTABLE"] = pixi_bin_path / ("cmake" + binary_ext)
    package_env_config["NINJA_EXECUTABLE"] = pixi_bin_path / ("ninja" + binary_ext)
    package_env_config["DOXYGEN_EXECUTABLE"] = pixi_bin_path / ("doxygen" + binary_ext)

    # Manylinux/docker bits for Linux

    if os_name == "linux":

        target_arch = os.environ.get("TARGET_ARCH") or arch

        manylinux_version, image_tag, manylinux_image_name, container_source = (
            default_manylinux(os_name, target_arch, os.environ.copy())
        )
        oci_exe = resolve_oci_exe(os.environ.copy())
        package_env_config["MANYLINUX_VERSION"] = manylinux_version
        package_env_config["IMAGE_TAG"] = image_tag
        package_env_config["MANYLINUX_IMAGE_NAME"] = manylinux_image_name
        package_env_config["CONTAINER_SOURCE"] = container_source
        package_env_config["TARGET_ARCH"] = target_arch
    else:
        oci_exe = os.environ.get("OCI_EXE", "")
    package_env_config["OCI_EXE"] = oci_exe
    del oci_exe

    # -------------
    platform = package_env_config["OS_NAME"].lower()
    if platform == "windows":
        from windows_build_python_instance import WindowsBuildPythonInstance

        builder_cls = WindowsBuildPythonInstance
    elif platform in ("darwin", "mac", "macos", "osx"):
        from macos_build_python_instance import MacOSBuildPythonInstance

        builder_cls = MacOSBuildPythonInstance
    elif platform == "linux":
        from linux_build_python_instance import LinuxBuildPythonInstance

        manylinux_version: str = package_env_config.get("MANYLINUX_VERSION", "")
        # Native builds without dockercross need a separate dist dir to avoid conflicts with manylinux
        # dist_dir = IPP_SOURCE_DIR / f"{platform}_dist"
        if len(manylinux_version) > 0 and (
            os.environ.get("CROSS_TRIPLE", None) is None
        ):
            print(
                f"ERROR: MANYLINUX_VERSION={manylinux_version} but not building in dockcross."
            )
            sys.exit(1)

        builder_cls = LinuxBuildPythonInstance
    else:
        raise ValueError(f"Unknown platform {platform}")

    for each_platform in args.platform_env:
        print(f"Building wheels for platform: {each_platform}")
        # Pass helper function callables and dist dir to avoid circular imports
        builder = builder_cls(
            platform_env=each_platform,
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
        )
        builder.run()


if __name__ == "__main__":
    main()
