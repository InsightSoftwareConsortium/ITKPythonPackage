from pathlib import Path

import build_environment
import wheel_packaging
from build_environment import PythonEnvironment
from build_python_instance_base import BuildPythonInstanceBase
from wheel_builder_utils import get_default_platform_build


class PosixBuildPythonInstance(BuildPythonInstanceBase):
    """Behavior shared by the Linux and macOS builders."""

    def build_tarball(self) -> None:
        """Create a zstd-compressed tarball of the ITK build tree."""
        wheel_packaging.create_posix_tarball(
            build_dir_root=self.build_dir_root,
            arch=self.package_env_config["ARCH"],
            ipp_source_dir=self.package_env_config["IPP_SOURCE_DIR"],
            platform_name=get_default_platform_build().split("-")[0],
            run=self.echo_check_call,
        )

    def venv_paths(self) -> PythonEnvironment:
        """Return the pixi-managed Python environment.

        Shared by Linux and macOS; Windows uses its own path conventions.
        """
        return build_environment.find_unix_python_paths(
            Path(self.package_env_config["PYTHON_EXECUTABLE"]).parent.parent
        )
