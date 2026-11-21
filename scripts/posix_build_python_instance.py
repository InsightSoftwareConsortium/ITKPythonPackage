from pathlib import Path

import build_environment
import wheel_packaging
from build_python_instance_base import BuildPythonInstanceBase


class PosixBuildPythonInstance(BuildPythonInstanceBase):
    """Behavior shared by the Linux and macOS builders."""

    def build_tarball(self) -> None:
        """Create a zstd-compressed tarball of the ITK build tree."""
        self.create_posix_tarball()

    def create_posix_tarball(self) -> None:
        """Create a compressed tarball of the ITK Python build tree."""
        wheel_packaging.create_posix_tarball(self)

    def find_unix_exectable_paths(
        self,
        venv_dir: Path,
    ) -> tuple[str, str, str, str, str]:
        """Delegate to the module-level implementation."""
        return build_environment.find_unix_exectable_paths(venv_dir)

    def venv_paths(self) -> None:
        """Populate ``venv_info_dict`` from the pixi-managed Python interpreter.

        Shared by Linux and macOS; Windows uses its own path conventions.
        """
        primary_python_base_dir = Path(
            self.package_env_config["PYTHON_EXECUTABLE"]
        ).parent.parent
        (
            python_executable,
            python_include_dir,
            python_library,
            venv_bin_path,
            venv_base_dir,
        ) = self.find_unix_exectable_paths(primary_python_base_dir)
        self.venv_info_dict = {
            "python_executable": python_executable,
            "python_include_dir": python_include_dir,
            "python_library": python_library,
            "venv_bin_path": venv_bin_path,
            "venv_base_dir": venv_base_dir,
            "python_root_dir": primary_python_base_dir,
        }
