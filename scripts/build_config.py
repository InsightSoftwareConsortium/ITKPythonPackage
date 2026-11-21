"""The validated configuration of one wheel build."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from target_platform import TargetPlatform


def _on_off(value: bool) -> str:
    return "ON" if value else "OFF"


@dataclass(frozen=True)
class BuildConfig:
    """Everything a builder reads about the build, typed and validated."""

    itk_source_dir: Path
    build_dir_root: Path
    target: TargetPlatform
    itk_git_tag: str
    itk_package_version: str
    # None where there is no deployment target (every OS but macOS).
    macosx_deployment_target: str | None
    itk_module_preq: str
    itk_module_no_cleanup: bool
    use_ccache: bool
    pixi_executable: Path
    cmake_executable: Path
    ninja_executable: Path
    doxygen_executable: Path
    git_executable: Path
    python_executable: Path
    oci_exe: str

    @property
    def pixi_suffix(self) -> str:
        return self.target.pixi_suffix

    @property
    def ipp_superbuild_binary_dir(self) -> Path:
        return self.build_dir_root / "build" / "ITK-support-bld"

    def to_environment(self) -> dict[str, str]:
        """The settings as the environment variables the build tools receive."""
        env = {
            "ITK_SOURCE_DIR": str(self.itk_source_dir),
            "IPP_SUPERBUILD_BINARY_DIR": str(self.ipp_superbuild_binary_dir),
            "OS_NAME": self.target.os_name.value,
            "ARCH": self.pixi_suffix,
            "BUILD_DIR_ROOT": str(self.build_dir_root),
            "ITK_GIT_TAG": self.itk_git_tag,
            "ITK_PACKAGE_VERSION": self.itk_package_version,
        }
        if self.macosx_deployment_target is not None:
            env["MACOSX_DEPLOYMENT_TARGET"] = self.macosx_deployment_target
        env.update(
            {
                "ITK_MODULE_PREQ": self.itk_module_preq,
                "ITK_MODULE_NO_CLEANUP": "1" if self.itk_module_no_cleanup else "0",
                "USE_CCACHE": _on_off(self.use_ccache),
                "PIXI_EXECUTABLE": str(self.pixi_executable),
                "CMAKE_EXECUTABLE": str(self.cmake_executable),
                "NINJA_EXECUTABLE": str(self.ninja_executable),
                "DOXYGEN_EXECUTABLE": str(self.doxygen_executable),
                "GIT_EXECUTABLE": str(self.git_executable),
                "PYTHON_EXECUTABLE": str(self.python_executable),
                "OCI_EXE": self.oci_exe,
            }
        )
        if self.target.manylinux_version:
            image = self.target.container_image
            env.update(
                {
                    "MANYLINUX_VERSION": self.target.manylinux_version,
                    "MANYLINUX_IMAGE_NAME": image.name,
                    "CONTAINER_SOURCE": image.reference,
                    "TARGET_ARCH": self.target.arch.value,
                }
            )
        return env
