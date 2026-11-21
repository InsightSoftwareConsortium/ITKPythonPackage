from build_python_instance_base import BuildPythonInstanceBase


class PosixBuildPythonInstance(BuildPythonInstanceBase):
    """Behavior shared by the Linux and macOS builders."""

    def build_tarball(self) -> None:
        """Create a zstd-compressed tarball of the ITK build tree."""
        self.create_posix_tarball()
