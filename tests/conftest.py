from pathlib import Path
from typing import TypeVar

import build_python_instance_base
import pytest
from build_config import BuildConfig
from build_environment import PythonEnvironment
from build_python_instance_base import BuildPythonInstanceBase
from cmake_argument_builder import CMakeArgumentBuilder
from linux_build_python_instance import LinuxBuildPythonInstance
from macos_build_python_instance import MacOSBuildPythonInstance
from target_platform import OS, Arch, TargetPlatform
from windows_build_python_instance import WindowsBuildPythonInstance

BuilderT = TypeVar("BuilderT", bound=BuildPythonInstanceBase)


def make_config(root: Path, target: TargetPlatform) -> BuildConfig:
    """A complete configuration for *target*, rooted at *root*."""
    return BuildConfig(
        itk_source_dir=root / "ITK",
        build_dir_root=root,
        os_name=target.os_name,
        arch=target.arch,
        itk_git_tag="main",
        itk_package_version="6.0.0",
        macosx_deployment_target="14.0" if target.os_name is OS.DARWIN else None,
        itk_module_preq="",
        itk_module_no_cleanup="1",
        use_ccache=False,
        dead_strip=False,
        pixi_executable=Path("pixi"),
        cmake_executable=Path("cmake"),
        ninja_executable=Path("ninja"),
        doxygen_executable=Path("doxygen"),
        git_executable=Path("git"),
        python_executable=Path("python"),
        oci_exe="docker",
        manylinux_version=target.manylinux_version or None,
    )


def _make_builder(
    cls: type[BuilderT],
    tmp_path: Path,
    platform_env: str,
    target: TargetPlatform,
) -> BuilderT:
    """Build an instance wired up enough to exercise its hooks.

    ``__new__`` bypasses ``__init__`` deliberately: the constructor
    resolves CMake and pixi paths that are irrelevant to these hooks and
    unavailable in the dev environment.
    """
    builder = cls.__new__(cls)
    builder.build_dir_root = tmp_path
    builder.platform_env = platform_env
    builder.target = target
    builder.config = make_config(tmp_path, target)
    builder.ipp_dir = Path(build_python_instance_base.__file__).parent.parent
    (tmp_path / "include").mkdir(exist_ok=True)
    builder.python_env = PythonEnvironment(
        root_dir=tmp_path,
        include_dir=tmp_path / "include",
        library=None,
        bin_path=tmp_path / "bin",
        base_dir=tmp_path,
    )
    builder.cmake_compiler_configurations = CMakeArgumentBuilder()
    builder.cmake_itk_source_build_configurations = CMakeArgumentBuilder()
    return builder


@pytest.fixture
def macos_builder(tmp_path: Path) -> MacOSBuildPythonInstance:
    """A macOS builder wired up enough to exercise its hooks."""
    return _make_builder(
        MacOSBuildPythonInstance,
        tmp_path,
        "macosx-py311",
        TargetPlatform(OS.DARWIN, Arch.AARCH64),
    )


@pytest.fixture
def linux_builder(tmp_path: Path) -> LinuxBuildPythonInstance:
    """A manylinux x86_64 builder."""
    return _make_builder(
        LinuxBuildPythonInstance,
        tmp_path,
        "manylinux228-py311",
        TargetPlatform(OS.LINUX, Arch.X86_64, "_2_28"),
    )


@pytest.fixture
def linux_aarch64_builder(tmp_path: Path) -> LinuxBuildPythonInstance:
    """A manylinux aarch64 builder, covering the cross-build triple."""
    return _make_builder(
        LinuxBuildPythonInstance,
        tmp_path,
        "manylinux228-py311",
        TargetPlatform(OS.LINUX, Arch.AARCH64, "_2_28"),
    )


@pytest.fixture
def windows_builder(tmp_path: Path) -> WindowsBuildPythonInstance:
    """A Windows x86_64 builder."""
    return _make_builder(
        WindowsBuildPythonInstance,
        tmp_path,
        "windows-py311",
        TargetPlatform(OS.WINDOWS, Arch.X86_64),
    )
