from build_python_instance_base import BuildPythonInstanceBase


class PosixBuildPythonInstance(BuildPythonInstanceBase):
    """Behavior shared by the Linux and macOS builders."""

    def build_tarball(self):
        """Create a zstd-compressed tarball of the ITK build tree."""
        self.create_posix_tarball()

    def discover_python_venvs(
        self, platform_os_name: str, platform_architecture: str
    ) -> list[str]:
        """Return environment names found under the project venvs dir."""
        venvs_dir = self.build_dir_root / "venvs"
        if not venvs_dir.exists():
            return []
        return sorted(p.name for p in venvs_dir.iterdir() if p.is_dir())
