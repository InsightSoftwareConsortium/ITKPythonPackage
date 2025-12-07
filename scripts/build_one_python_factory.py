from __future__ import annotations

from pathlib import Path

from build_python_instance_base import (
    IPP_SOURCE_DIR,
    IPP_SUPERBUILD_BINARY_DIR,
    ITK_SOURCE_DIR,
    SCRIPT_DIR,
    package_env_config,
)


def build_one_python_instance(
    py_env,
    wheel_names,
    platform_name: str,
    platform_architechture: str,
    cleanup: bool,
    cmake_options: list[str],
    windows_extra_lib_paths: list[str],
    module_source_dir: Path | None = None,
    module_dependancies_root_dir: Path | None = None,
    itk_module_deps: str | None = None,
):
    """
    Backwards-compatible wrapper that now delegates to the new OOP builders.
    """
    platform = platform_name.lower()
    if platform == "windows":
        from windows_build_python_instance import WindowsBuildPythonInstance

        builder_cls = WindowsBuildPythonInstance
    elif platform in ("darwin", "mac", "macos", "osx"):
        from macos_build_python_instance import MacOSBuildPythonInstance

        builder_cls = MacOSBuildPythonInstance
    elif platform == "linux":
        from linux_build_python_instance import LinuxBuildPythonInstance

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
        module_source_dir=module_source_dir,
        module_dependancies_root_dir=module_dependancies_root_dir,
        itk_module_deps=itk_module_deps,
    )
    builder.run()
