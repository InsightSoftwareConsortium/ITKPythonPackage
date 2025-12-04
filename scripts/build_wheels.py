#!/usr/bin/env python

import argparse
import sys
from pathlib import Path

from dotenv import dotenv_values

from windows_build_python_instance import WindowsBuildPythonInstance
from macos_build_python_instance import MacOSBuildPythonInstance
from linux_build_python_instance import LinuxBuildPythonInstance
from wheel_builder_utils import (
    detect_platform,
)


SCRIPT_DIR = Path(__file__).parent
# TODO: Hard-coded module must be 1 direectory above checkedout ITKPythonPackage
# MODULE_EXAMPLESROOT_DIR: Path = SCRIPT_DIR.parent.parent.resolve()

IPP_SOURCE_DIR = SCRIPT_DIR.parent.resolve()
IPP_SUPERBUILD_BINARY_DIR = IPP_SOURCE_DIR / "build" / "ITK-source"
package_env_config = dotenv_values(IPP_SOURCE_DIR / "build" / "package.env")
ITK_SOURCE_DIR = package_env_config["ITK_SOURCE_DIR"]

print(f"SCRIPT_DIR: {SCRIPT_DIR}")
print(f"ROOT_DIR: {IPP_SOURCE_DIR}")
print(f"ITK_SOURCE: {IPP_SUPERBUILD_BINARY_DIR}")

sys.path.insert(0, str(SCRIPT_DIR / "internal"))

OS_NAME: str = "UNKNOWN"
ARCH: str = "UNKNOWN"


def build_one_python_instance(
    py_env,
    wheel_names,
    platform_name: str,
    platform_architechture: str,
    cleanup: bool,
    cmake_options: list[str],
    windows_extra_lib_paths: list[str],
):
    """
    Backwards-compatible wrapper that now delegates to the new OOP builders.
    """
    platform = platform_name.lower()
    if platform == "windows":
        builder_cls = WindowsBuildPythonInstance
    elif platform in ("darwin", "mac", "macos", "osx"):
        builder_cls = MacOSBuildPythonInstance
    elif platform == "linux":
        builder_cls = LinuxBuildPythonInstance
    else:
        raise ValueError(f"Unknown platform {platform_name}")

    # Pass helper function callables and dist dir to avoid circular imports
    builder = builder_cls(
        py_env=py_env,
        wheel_names=wheel_names,
        platform_name=platform_name,
        platform_architechture=platform_architechture,
        ipp_source_dir=IPP_SOURCE_DIR,
        ipp_superbuild_binary_dir=IPP_SUPERBUILD_BINARY_DIR,
        itk_source_dir=ITK_SOURCE_DIR,
        script_dir=SCRIPT_DIR,
        package_env_config=package_env_config,
        cleanup=cleanup,
        cmake_options=cmake_options,
        windows_extra_lib_paths=windows_extra_lib_paths,
        dist_dir=IPP_SOURCE_DIR / "dist",
    )
    builder.run()


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
        dest="cleanup",
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
    args = parser.parse_args()

    with open(SCRIPT_DIR / "WHEEL_NAMES.txt", "r", encoding="utf-8") as content:
        wheel_names = [wheel_name.strip() for wheel_name in content.readlines()]

    for py_env in args.py_envs:
        build_one_python_instance(
            py_env,
            wheel_names,
            OS_NAME,
            ARCH,
            args.cleanup,
            args.cmake_options,
            args.lib_paths,
        )


if __name__ == "__main__":
    main()
