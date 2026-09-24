import pytest
from cmake_argument_builder import CMakeArgumentBuilder
from linux_build_python_instance import LinuxBuildPythonInstance
from macos_build_python_instance import MacOSBuildPythonInstance
from target_platform import Arch, TargetPlatform
from windows_build_python_instance import WindowsBuildPythonInstance


def _make_builder(cls, tmp_path, platform_env, target, package_env_config):
    """Build an instance wired up enough to exercise its hooks.

    ``__new__`` bypasses ``__init__`` deliberately: the constructor
    resolves CMake and pixi paths that are irrelevant to these hooks and
    unavailable in the dev environment.
    """
    builder = cls.__new__(cls)
    builder.build_dir_root = tmp_path
    builder.platform_env = platform_env
    builder.target = target
    builder.package_env_config = dict(package_env_config)
    builder.venv_info_dict = {"venv_bin_path": str(tmp_path / "bin")}
    builder.cmake_compiler_configurations = CMakeArgumentBuilder()
    builder.cmake_itk_source_build_configurations = CMakeArgumentBuilder()
    return builder


@pytest.fixture
def macos_builder(tmp_path):
    """A macOS builder wired up enough to exercise its hooks."""
    return _make_builder(
        MacOSBuildPythonInstance,
        tmp_path,
        "macosx-py311",
        TargetPlatform("darwin", Arch.AARCH64),
        {"ARCH": "arm64"},
    )


@pytest.fixture
def linux_builder(tmp_path):
    """A manylinux x86_64 builder."""
    return _make_builder(
        LinuxBuildPythonInstance,
        tmp_path,
        "manylinux228-py311",
        TargetPlatform("linux", Arch.X86_64, "_2_28"),
        {"ARCH": "x64"},
    )


@pytest.fixture
def linux_aarch64_builder(tmp_path):
    """A manylinux aarch64 builder, covering the cross-build triple."""
    return _make_builder(
        LinuxBuildPythonInstance,
        tmp_path,
        "manylinux228-py311",
        TargetPlatform("linux", Arch.AARCH64, "_2_28"),
        {"ARCH": "aarch64"},
    )


@pytest.fixture
def windows_builder(tmp_path):
    """A Windows x86_64 builder."""
    return _make_builder(
        WindowsBuildPythonInstance,
        tmp_path,
        "windows-py311",
        TargetPlatform("windows", Arch.X86_64),
        {"ARCH": "x64"},
    )
