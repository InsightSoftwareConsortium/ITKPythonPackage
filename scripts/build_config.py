"""The validated configuration of one wheel build."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from compiler_cache import use_compiler_cache
from target_platform import OS, Arch, TargetPlatform

if TYPE_CHECKING:
    import argparse
    from collections.abc import Mapping

_DEPLOYMENT_TARGET = re.compile(r"\d+(\.\d+){0,2}")


class BuildConfigError(ValueError):
    """A build setting is missing or has a value the build cannot use."""

    def __init__(self, field: str, value: object, reason: str) -> None:
        super().__init__(f"{field}={value!r}: {reason}")
        self.field = field
        self.value = value


def _text(field: str, value: object, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise BuildConfigError(field, value, "expected a string")
    if not allow_empty and not value:
        raise BuildConfigError(field, value, "must not be empty")
    return value


def _path(field: str, value: object) -> Path:
    if isinstance(value, Path):
        return value
    if isinstance(value, os.PathLike | str) and str(value):
        return Path(value)
    raise BuildConfigError(field, value, "expected a non-empty path")


def _flag(field: str, value: object) -> bool:
    if not isinstance(value, bool):
        raise BuildConfigError(field, value, "expected True or False")
    return value


def _optional_flag(field: str, value: object) -> bool | None:
    return None if value is None else _flag(field, value)


def _manylinux_version(target: TargetPlatform, value: object) -> str:
    field = "manylinux_version"
    if target.os_name is not OS.LINUX:
        return ""
    version = _text(field, value or "")
    try:
        TargetPlatform(target.os_name, target.arch, version)
    except ValueError as e:
        raise BuildConfigError(field, version, str(e)) from e
    return version


def _deployment_target(target: TargetPlatform, value: object) -> str | None:
    field = "macosx_deployment_target"
    if target.os_name is not OS.DARWIN:
        return None
    version = _text(field, value)
    if version and not _DEPLOYMENT_TARGET.fullmatch(version):
        raise BuildConfigError(field, version, "expected a macOS version such as 14.0")
    return version


def _on_off(value: bool) -> str:
    return "ON" if value else "OFF"


@dataclass(frozen=True)
class BuildConfig:
    """Everything a builder reads about the build, typed and validated."""

    itk_source_dir: Path
    build_dir_root: Path
    os_name: OS
    arch: Arch
    itk_git_tag: str
    itk_package_version: str
    # None where there is no deployment target (every OS but macOS).
    macosx_deployment_target: str | None
    itk_module_preq: str
    itk_module_no_cleanup: str
    use_ccache: bool
    dead_strip: bool
    pixi_executable: Path
    cmake_executable: Path
    ninja_executable: Path
    doxygen_executable: Path
    git_executable: Path
    python_executable: Path
    oci_exe: str
    manylinux_version: str | None = None

    @classmethod
    def from_args_and_env(
        cls,
        args: argparse.Namespace,
        env: Mapping[str, str],
        *,
        target: TargetPlatform,
        pixi_executable: Path,
        cmake_executable: Path,
        ninja_executable: Path,
        doxygen_executable: Path,
        git_executable: Path,
        python_executable: str,
        oci_exe: str,
    ) -> BuildConfig:
        """Validate and convert the parsed arguments, environment, and tools.

        Raises
        ------
        BuildConfigError
            Naming the first setting whose value the build cannot use.
        """
        manylinux_version = _manylinux_version(target, args.manylinux_version)
        macosx_deployment_target = _deployment_target(
            target, args.macosx_deployment_target
        )
        return cls(
            itk_source_dir=_path("itk_source_dir", args.itk_source_dir),
            build_dir_root=_path("build_dir_root", args.build_dir_root),
            os_name=target.os_name,
            arch=target.arch,
            itk_git_tag=_text("itk_git_tag", args.itk_git_tag, allow_empty=False),
            itk_package_version=_text(
                "itk_package_version", args.itk_package_version, allow_empty=False
            ),
            macosx_deployment_target=macosx_deployment_target,
            itk_module_preq=_text("itk_module_preq", args.itk_module_deps),
            itk_module_no_cleanup=env.get("ITK_MODULE_NO_CLEANUP", "1"),
            use_ccache=use_compiler_cache(
                _optional_flag("use_ccache", args.use_ccache), env
            ),
            dead_strip=_flag("dead_strip", args.dead_strip),
            pixi_executable=_path("pixi_executable", pixi_executable),
            cmake_executable=_path("cmake_executable", cmake_executable),
            ninja_executable=_path("ninja_executable", ninja_executable),
            doxygen_executable=_path("doxygen_executable", doxygen_executable),
            git_executable=_path("git_executable", git_executable),
            python_executable=_path("python_executable", python_executable),
            oci_exe=_text("oci_exe", oci_exe, allow_empty=False),
            manylinux_version=manylinux_version or None,
        )

    @property
    def target(self) -> TargetPlatform:
        return TargetPlatform(self.os_name, self.arch, self.manylinux_version or "")

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
            "OS_NAME": self.os_name.value,
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
                "ITK_MODULE_NO_CLEANUP": self.itk_module_no_cleanup,
                "USE_CCACHE": _on_off(self.use_ccache),
                "DEAD_STRIP": _on_off(self.dead_strip),
                "PIXI_EXECUTABLE": str(self.pixi_executable),
                "CMAKE_EXECUTABLE": str(self.cmake_executable),
                "NINJA_EXECUTABLE": str(self.ninja_executable),
                "DOXYGEN_EXECUTABLE": str(self.doxygen_executable),
                "GIT_EXECUTABLE": str(self.git_executable),
                "PYTHON_EXECUTABLE": str(self.python_executable),
                "OCI_EXE": self.oci_exe,
            }
        )
        if self.manylinux_version:
            image = self.target.container_image
            env.update(
                {
                    "MANYLINUX_VERSION": self.manylinux_version,
                    "MANYLINUX_IMAGE_NAME": image.name,
                    "CONTAINER_SOURCE": image.reference,
                    "TARGET_ARCH": self.arch.value,
                }
            )
        return env
