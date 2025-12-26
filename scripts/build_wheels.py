#!/usr/bin/env python3
from __future__ import (
    annotations,
)  # Needed for python 3.9 to support python 3.10 style typehints

import os
import subprocess
import sys
import argparse
from pathlib import Path


from wheel_builder_utils import (
    detect_platform,
    run_commandLine_subprocess,
    default_manylinux,
    compute_itk_package_version,
    resolve_oci_exe,
    _which,
)


def remotemodulebuildandtestaction() -> dict[str,str]:
    ITKRemoteModuleBuildTestPackageAction_ENV_MAPPING: dict[str, str] = {
        "ITK_PACKAGE_VERSION": "inputs.itk-wheel-tag",#
        "ITKPYTHONPACKAGE_TAG":"inputs.itk-python-package-tag", #
        "ITKPYTHONPACKAGE_ORG": "inputs.itk-python-package-org", #
        "ITK_MODULE_PREQ": "inputs.itk-module-deps",#
        "CMAKE_OPTIONS" : "inputs.cmake-options", #
        "MANYLINUX_PLATFORM": "matrix.manylinux-platform", #--- No longer used, computed internally
        "MANYLINUX_VERSION": "computed as first part of MANYLINUX_PLATFORM",#
        "TARGET_ARCH": "computed as second part of MANYLINUX_PLATFORM",# --- No longer used, computed internally
        "MACOSX_DEPLOYMENT_TARGET": "inputs.macosx-deployment-target"
    }
    remote_module_build_dict: dict[str, str] = {}
    for key in ITKRemoteModuleBuildTestPackageAction_ENV_MAPPING.keys():
        remote_module_build_dict[key] =  os.environ.get(key,"")
    return remote_module_build_dict

    """
        ITK_PACKAGE_VERSION=${ITK_PACKAGE_VERSION} ITKPYTHONPACKAGE_TAG=${ITKPYTHONPACKAGE_TAG} ITKPYTHONPACKAGE_ORG=${ITKPYTHONPACKAGE_ORG} ITK_MODULE_PREQ=${ITK_MODULE_PREQ} IPP_DOWNLOAD_GIT_TAG=${IPP_DOWNLOAD_GIT_TAG} IPP_DOWNLOAD_ORG=${IPP_DOWNLOAD_ORG} ./dockcross-manylinux-download-cache-and-build-module-wheels.sh cp3${{ matrix.python3-minor-version }} $CMAKE_OPTIONS
    """


if sys.version_info < (3, 9):
    sys.stderr.write(
        "Python 3.9+ required for the python packaging script execution.\n"
    )
    sys.exit(1)


def in_pixi_env() -> bool:
    """
    Determine if we are running inside a pixi enviornment.
    Returns
    -------
    """
    return "PIXI_ENVIRONMENT_NAME" in os.environ and "PIXI_PROJECT_ROOT" in os.environ

def get_default_platform_build(default_python_version:str = "py311") -> str:
    from_pixi = os.get("PIXI_ENVIRONMENT_NAME", None)
    if from_pixi:
        return from_pixi
    else:
        if os.name == "windows":
            return f"windows-{default_python_version}"
        elif os.name == "linux":
            return f"linux-{default_python_version}"
        elif os.name == "macos":
            return f"macos-{default_python_version}"

def build_wheels_main() -> None:
    os_name, arch = detect_platform()
    ipp_script_dir: Path = Path(__file__).parent
    ipp_dir : Path = ipp_script_dir.parent
    if ipp_dir/".pixi"/"bin":
        os.environ["PATH"] = str(ipp_dir/".pixi"/"bin") + os.pathsep + os.environ["PATH"]

    remote_module_build_dict = remotemodulebuildandtestaction()
    parser = argparse.ArgumentParser(
        description="Driver script to build ITK Python wheels."
    )
    parser.add_argument(
        "--platform-env",
        default=get_default_platform_build("py311"),
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
        default=remote_module_build_dict["CMAKE_OPTIONS"],
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
        help="Build an uploadable tarball.  The tarball can be used as a cache for remote module builds.",
    )

    # set the default build_dir_root to a very short path on windows to avoid path too long errors
    default_build_dir_root = ipp_dir.parent / "ITKPythonPackage-build" if os_name != "windows"  else Path("C:") / "BDR"
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
        default=os.environ.get("ITK_GIT_TAG", os.environ.get("ITK_PACKAGE_VERSION","main")),
        help="""
        - 'ITK_GIT_TAG': Tag/branch/hash for the ITK source code to use in packaging.
           Which ITK git tag/hash/branch to use as reference for building wheels/modules
           https://github.com/InsightSoftwareConsortium/ITK.git@${ITK_GIT_TAG}
           Examples: v5.4.0, v5.2.1.post1, 0ffcaed12552, my-testing-branch
           See available release tags at https://github.com/InsightSoftwareConsortium/ITKPythonBuilds/tags
        """,
    )

    # set the default build_dir_root to a very short path on windows to avoid path too long errors
    default_itk_source_dir =  ipp_dir.parent / "ITKPythonPackage-build" / "ITK" if os_name != "windows" else Path("C:") / "BDR"/"ITK"
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

    parser.add_argument(
        "--itk-pythonpackage-org",
        type=str,
        default=remote_module_build_dict["ITK_PYTHONPACKAGE_ORG"],
        help="""
         - 'ITKPYTHONPACKAGE_ORG':Github organization or user to use for ITKPythonPackage build scripts
           Which script version to use in generating python packages
           https://github.com/InsightSoftwareConsortium/${ITKPYTHONPACKAGE_ORG}/ITKPythonPackage.git@${ITKPYTHONPACKAGE_TAG}
           build script source. Default is InsightSoftwareConsortium.
           Ignored if ITKPYTHONPACKAGE_TAG is empty.
           (in github action ITKRemoteModuleBuildTestPackage itk-python-package-org is used to set this value)
         """,
    )

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
    parser.add_argument(
        "--no-pixi-test",
        action="store_false",
        help="""
         -  Option to indicate that pixi is not required for building.  This means that the development
         environment must supply all the required resources outside of pixi.
         """,
    )
    parser.add_argument(
        "--install-local-pixi",
        action="store_true",
        help="""
            Installs pixi locally if not found and quits.
         """,
    )

    args = parser.parse_args()

    print("=" * 80)
    print("=" * 80)
    print("= Building Wheels")
    print("=" * 80)
    print("=" * 80)

    # Historical dist_dir name for compatibility with ITKRemoteModuleBuildTestPackageAction
    _ipp_dir_path: Path = Path(__file__).resolve().parent.parent
    dist_dir: Path = Path(args.build_dir_root) / "dist"

    # Platform detection
    binary_ext: str = ".exe" if os_name == "windows" else ""
    os.environ["PATH"] = (
        str(_ipp_dir_path / ".pixi" / "bin") + os.pathsep + os.environ.get("PATH", "")
    )
    pixi_exec_path: Path = _which("pixi" + binary_ext)
    pixi_bin_path: Path = pixi_exec_path.parent
    # Required executables (paths recorded)
    # platform_pixi_packages = ["doxygen", "ninja", "cmake", "git"]
    # if os_name == "linux":
    #     platform_pixi_packages += ["patchelf"]
    #
    # missing_packages: list[str] = []
    # for ppp in platform_pixi_packages:
    #     # Search for binaries  herefull_path: Path = pixi_exec_path / (ppp + binary_ext)
    #     if not full_path.is_file():
    #         missing_packages.append(ppp)
    # if len(missing_packages) > 0:
    #   print diagnostic messaging and exit

    # NOT NEEDED
    # ipp_latest_tag: str = get_git_id(
    #     _ipp_dir_path, pixi_exec_path, os.environ, os.environ.get("ITKPYTHONPACKAGE_TAG", "v0.0.0")
    # )

    package_env_config: dict[str, str | Path | None] = {}

    args.build_dir_root = Path(args.build_dir_root)
    if args.itk_source_dir is None:
        args.itk_source_dir = args.build_dir_root / "ITK-source" / "ITK"

    args.itk_source_dir = Path(args.itk_source_dir)
    package_env_config["ITK_SOURCE_DIR"] = Path(args.itk_source_dir)

    ipp_superbuild_binary_dir: Path = args.build_dir_root / "build" / "ITK-support-bld"
    package_env_config["IPP_SUPERBUILD_BINARY_DIR"] = ipp_superbuild_binary_dir

    package_env_config["OS_NAME"] = os_name
    package_env_config["ARCH"] = arch

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
    package_env_config["PIXI_EXECUTABLE"] = _which("pixi")
    package_env_config["CMAKE_EXECUTABLE"] = _which("cmake")
    package_env_config["NINJA_EXECUTABLE"] = _which("ninja")
    package_env_config["DOXYGEN_EXECUTABLE"] = _which("doxygen")

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
                    f"WARNING: environment variable MANYLINUX_VERSION={manylinux_version} is changed to comand line value of {manylinux_version}."
                )
            package_env_config["MANYLINUX_VERSION"] = manylinux_version
            image_tag, manylinux_image_name, container_source = default_manylinux(
                manylinux_version, os_name, target_arch, os.environ.copy()
            )
            package_env_config["IMAGE_TAG"] = image_tag
            package_env_config["MANYLINUX_IMAGE_NAME"] = manylinux_image_name
            package_env_config["CONTAINER_SOURCE"] = container_source
            package_env_config["TARGET_ARCH"] = target_arch

            # Native builds without dockercross need a separate dist dir to avoid conflicts with manylinux
            # dist_dir = IPP_SOURCE_DIR / f"{platform}_dist"
            if os.environ.get("CROSS_TRIPLE", None) is None:
                print(
                    f"ERROR: MANYLINUX_VERSION={manylinux_version} but not building in dockcross."
                )
                sys.exit(1)

        builder_cls = LinuxBuildPythonInstance
    else:
        raise ValueError(f"Unknown platform {platform}")

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
    )
    builder.run()


if __name__ == "__main__":
    build_wheels_main()
