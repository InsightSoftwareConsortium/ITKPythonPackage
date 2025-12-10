from __future__ import annotations

import os
import sys

from pathlib import Path


def build_one_python_instance(
    py_env,
    wheel_names,
    package_env_config,
    cleanup: bool,
    build_itk_tarball_cache: bool,
    cmake_options: list[str],
    windows_extra_lib_paths: list[str],
    module_source_dir: Path | None = None,
    module_dependancies_root_dir: Path | None = None,
    itk_module_deps: str | None = None,
):
    """
    Backwards-compatible wrapper that now delegates to the new OOP builders.
    """
    platform = package_env_config["OS_NAME"].lower()

    # Historical dist_dir name for compatibility with ITKRemoteModuleBuildTestPackageAction
    dist_dir = package_env_config["IPP_SOURCE_DIR"] / "dist"
    if platform == "windows":
        from windows_build_python_instance import WindowsBuildPythonInstance

        builder_cls = WindowsBuildPythonInstance
    elif platform in ("darwin", "mac", "macos", "osx"):
        from macos_build_python_instance import MacOSBuildPythonInstance

        builder_cls = MacOSBuildPythonInstance
    elif platform == "linux":
        from linux_build_python_instance import LinuxBuildPythonInstance

        MANYLINUX_VERSION: str = package_env_config.get("MANYLINUX_VERSION", "")
        if len(MANYLINUX_VERSION) == 0:
            # Native builds without dockercross need a separate dist dir to avoid conflicts with manylinux
            # dist_dir = IPP_SOURCE_DIR / f"{platform}_dist"
            pass
        if os.environ.get("CROSS_TRIPLE", None) is None:
            print(
                f"ERROR: MANYLINUX_VERSION={MANYLINUX_VERSION} but not building in dockcross."
            )
            sys.exit(1)

        builder_cls = LinuxBuildPythonInstance
    else:
        raise ValueError(f"Unknown platform {platform}")

    # Pass helper function callables and dist dir to avoid circular imports
    builder = builder_cls(
        py_env=py_env,
        wheel_names=wheel_names,
        package_env_config=package_env_config,
        cleanup=cleanup,
        build_itk_tarball_cache=build_itk_tarball_cache,
        cmake_options=cmake_options,
        windows_extra_lib_paths=windows_extra_lib_paths,
        dist_dir=dist_dir,
        module_source_dir=module_source_dir,
        module_dependancies_root_dir=module_dependancies_root_dir,
        itk_module_deps=itk_module_deps,
    )
    builder.run()
