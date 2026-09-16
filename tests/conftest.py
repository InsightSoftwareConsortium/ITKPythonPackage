import pytest
from macos_build_python_instance import MacOSBuildPythonInstance
from target_platform import Arch, TargetPlatform


@pytest.fixture
def macos_builder(tmp_path):
    """A macOS builder wired up enough to exercise its hooks."""
    builder = MacOSBuildPythonInstance.__new__(MacOSBuildPythonInstance)
    builder.build_dir_root = tmp_path
    builder.platform_env = "macosx-py311"
    builder.target = TargetPlatform("darwin", Arch.AARCH64)
    builder.package_env_config = {"ARCH": "arm64"}
    builder.venv_info_dict = {"venv_bin_path": str(tmp_path / "bin")}
    return builder
