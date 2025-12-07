#!/usr/bin/env python3

import sys

from wheel_builder_utils import (
    set_main_variable_names,
)
from build_one_python_factory import build_one_python_instance

if sys.version_info < (3, 10):
    sys.stderr.write(
        "Python 3.10+ required for the python packaging script execution.\n"
    )
    sys.exit(1)

import argparse
from pathlib import Path

from wheel_builder_utils import detect_platform

(
    SCRIPT_DIR,
    IPP_SOURCE_DIR,
    IPP_BuildWheelsSupport_DIR,
    IPP_SUPERBUILD_BINARY_DIR,
    package_env_config,
    ITK_SOURCE_DIR,
    OS_NAME,
    ARCH,
) = set_main_variable_names(Path(__file__).parent)


def main() -> None:

    global OS_NAME, ARCH
    # Platform detection
    OS_NAME, ARCH = detect_platform()

    parser = argparse.ArgumentParser(
        description="Driver script to build ITK Python wheels."
    )
    parser.add_argument(
        "--py-envs",
        nargs="+",
        default=None,
        help=(
            "Windows: Python versions like '39-x64'. macOS: names or paths of venvs under 'venvs/'."
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
        help="Extra options to pass to CMake, e.g. -DBUILD_SHARED_LIBS:BOOL=OFF",
    )
    parser.add_argument(
        "--module-source-dir",
        type=Path,
        default=None,
        help="Path to the module source directory",
    )
    parser.add_argument(
        "--module-dependancies-root-dir",
        type=Path,
        default=None,
        help="Path to the root directory for module dependancies",
    )
    parser.add_argument(
        "--itk-module-deps",
        type=str,
        default=None,
        help="Semicolon-delimited list of ITK module dependencies",
    )
    args = parser.parse_args()

    with open(
        IPP_BuildWheelsSupport_DIR / "WHEEL_NAMES.txt", "r", encoding="utf-8"
    ) as content:
        wheel_names = [wheel_name.strip() for wheel_name in content.readlines()]

    normalized_python_versions: list[str] = [
        p.replace("cp3", "3.") for p in args.py_envs
    ]

    for py_env in normalized_python_versions:
        build_one_python_instance(
            py_env,
            wheel_names,
            OS_NAME,
            ARCH,
            args.no_cleanup,
            args.cmake_options,
            args.lib_paths,
            args.module_source_dir,
            args.module_dependancies_root_dir,
            args.itk_module_deps,
        )


if __name__ == "__main__":
    main()
