#!/usr/bin/env python3
import os
import sys


from build_one_python_factory import build_one_python_instance
from generate_build_environment import generate_build_environment
from wheel_builder_utils import read_env_file, detect_platform

if sys.version_info < (3, 10):
    sys.stderr.write(
        "Python 3.10+ required for the python packaging script execution.\n"
    )
    sys.exit(1)

import argparse
from pathlib import Path


def _set_main_variable_names(
    SCRIPT_DIR: Path, PACKAGE_ENV_FILE: Path
) -> dict[str, str | Path | None]:
    # TODO: Hard-coded module must be 1 direectory above checked out ITKPythonPackage
    # MODULE_EXAMPLESROOT_DIR: Path = SCRIPT_DIR.parent.parent.resolve()

    # Primarily needed for docker-cross to fill in CMAKE_EXECUTABLE, NINJA_EXECUTABLE, and DOXYGEN_EXECUTABLE
    # from the environment defaults
    generate_build_environment_update_args = ["-o", str(PACKAGE_ENV_FILE)]
    if not PACKAGE_ENV_FILE.exists():
        generate_build_environment_update_args.extend(["-i", str(PACKAGE_ENV_FILE)])
    generate_build_environment(generate_build_environment_update_args)

    PACKAGE_ENV_FILE = Path(os.environ.get("PACKAGE_ENV_FILE", PACKAGE_ENV_FILE))
    package_env_config: dict[str, str | Path | None] = read_env_file(PACKAGE_ENV_FILE)
    package_env_config["PACKAGE_ENV_FILE"] = PACKAGE_ENV_FILE

    sys.path.insert(0, str(SCRIPT_DIR / "internal"))
    package_env_config["SCRIPT_DIR"] = SCRIPT_DIR

    IPP_SOURCE_DIR = SCRIPT_DIR.parent.resolve()
    package_env_config["IPP_SOURCE_DIR"] = IPP_SOURCE_DIR

    IPP_BuildWheelsSupport_DIR = IPP_SOURCE_DIR / "BuildWheelsSupport"
    package_env_config["IPP_BuildWheelsSupport_DIR"] = IPP_BuildWheelsSupport_DIR

    IPP_SUPERBUILD_BINARY_DIR = IPP_SOURCE_DIR / "build" / "ITK-source"
    package_env_config["IPP_SUPERBUILD_BINARY_DIR"] = IPP_SUPERBUILD_BINARY_DIR

    OS_NAME, ARCH = detect_platform()
    package_env_config["OS_NAME"] = OS_NAME
    package_env_config["ARCH"] = ARCH

    return package_env_config


def main() -> None:
    SCRIPT_DIR: Path = Path(__file__).parent
    parser = argparse.ArgumentParser(
        description="Driver script to build ITK Python wheels."
    )
    parser.add_argument(
        "--py-envs",
        nargs="+",
        default=None,
        help=(
            "A list of python environments to build for:\n"
            + "    - Windows: Python versions like '310-x64' '311-x64'.\n"
            + " macOS & linux: names or paths of venvs under 'venvs/'. like '3.11' or 'cp311'"
        ),
    )
    parser.add_argument(
        "--no-cleanup",
        dest="no_cleanup",
        action="store_false",
        help="Do not clean up temporary build files.",
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
        "--module-dependancies-root-dir",
        type=Path,
        default=None,
        help="Path to the root directory for module dependancies.\n"
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
    parser.add_argument(
        "--package-env-file",
        type=str,
        default=f"{SCRIPT_DIR}/build/package.env",
        help=".env file with parameters used to control builds, default to build/package.env for native builds\n"
        + "and is commonly set to /work/dist/container_package.env for dockercross builds.",
    )

    args = parser.parse_args()
    print("=" * 80)
    print("=" * 80)
    print("= Building Wheels")
    print("=" * 80)
    print("=" * 80)
    package_env_config = _set_main_variable_names(
        SCRIPT_DIR=SCRIPT_DIR, PACKAGE_ENV_FILE=Path(args.package_env_file)
    )

    with open(
        package_env_config["IPP_BuildWheelsSupport_DIR"] / "WHEEL_NAMES.txt",
        "r",
        encoding="utf-8",
    ) as content:
        wheel_names = [wheel_name.strip() for wheel_name in content.readlines()]

    normalized_python_versions: list[str] = [
        p.replace("cp3", "3.") for p in args.py_envs
    ]

    for py_env in normalized_python_versions:
        build_one_python_instance(
            py_env,
            wheel_names,
            package_env_config,
            args.no_cleanup,
            args.build_itk_tarball_cache,
            args.cmake_options,
            args.lib_paths,
            args.module_source_dir,
            args.module_dependancies_root_dir,
            args.itk_module_deps,
        )


if __name__ == "__main__":
    main()
