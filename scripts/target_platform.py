"""Single source of truth for target platform and architecture.

Every architecture spelling the build needs is a property here. Adding
a new architecture means adding one enum member and filling in each
property, so a missing translation is a construction error rather than
a silently-skipped branch.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


class Arch(Enum):
    """Canonical machine name. Never a per-OS nickname."""

    X86_64 = "x86_64"
    AARCH64 = "aarch64"
    I686 = "i686"


_MACHINE_ALIASES: dict[str, Arch] = {
    "x86_64": Arch.X86_64,
    "amd64": Arch.X86_64,
    "x64": Arch.X86_64,
    "aarch64": Arch.AARCH64,
    "arm64": Arch.AARCH64,
    "i686": Arch.I686,
    "i386": Arch.I686,
}

_OS_NAMES = ("linux", "darwin", "windows")

# (arch, manylinux_version) -> container image tag
_MANYLINUX_IMAGE_TAGS: dict[tuple[Arch, str], str] = {
    # manylinux_2_28 is what ships; the _2_34 entry is deliberate headroom
    # for evaluating a higher glibc floor and is not a shipping target.
    (Arch.X86_64, "_2_34"): "latest",
    (Arch.X86_64, "_2_28"): "20250913-6ea98ba",
    (Arch.AARCH64, "_2_28"): "2025.08.12-1",
}

_PIXI_SUFFIX: dict[tuple[str, Arch], str] = {
    ("linux", Arch.X86_64): "x64",
    ("linux", Arch.AARCH64): "aarch64",
    ("linux", Arch.I686): "x86",
    ("darwin", Arch.AARCH64): "arm64",
    ("darwin", Arch.X86_64): "x86_64",
    ("windows", Arch.X86_64): "x64",
}

_MACOSX_DEPLOYMENT_TARGET = "14_0"


def manylinux_version_from_platform_env(platform_env: str) -> str:
    """Manylinux version implied by a platform environment name.

    ``'manylinux228-py311'`` and ``'manylinux_2_28-py311'`` give ``'_2_28'``;
    any other environment gives ``''``.
    """
    prefix = Path(platform_env).name.split("-")[0]
    if not prefix.startswith("manylinux"):
        return ""
    digits = prefix[len("manylinux") :].replace("_", "")
    if len(digits) < 2 or not digits.isdigit():
        return ""
    return f"_{digits[0]}_{digits[1:]}"


@dataclass(frozen=True)
class ContainerImage:
    """A manylinux build image and the registry that serves it."""

    name: str
    registry: str

    @property
    def reference(self) -> str:
        return f"{self.registry}/{self.name}"


@dataclass(frozen=True)
class TargetPlatform:
    """The platform being built *for*, with every spelling it needs."""

    os_name: str
    arch: Arch
    manylinux_version: str = ""

    def __post_init__(self) -> None:
        if self.os_name not in _OS_NAMES:
            msg = f"Unknown os_name {self.os_name!r}; expected one of {_OS_NAMES}"
            raise ValueError(msg)
        if not isinstance(self.arch, Arch):
            msg = f"arch must be an Arch, got {self.arch!r}"
            raise TypeError(msg)
        if (self.os_name, self.arch) not in _PIXI_SUFFIX:
            msg = f"Unsupported combination {self.os_name}/{self.arch.value}"
            raise ValueError(msg)
        if self.manylinux_version:
            if self.os_name != "linux":
                msg = "manylinux_version is only meaningful on linux"
                raise ValueError(msg)
            if (self.arch, self.manylinux_version) not in _MANYLINUX_IMAGE_TAGS:
                msg_0 = (
                    f"Unknown manylinux version "
                    f"{self.manylinux_version!r} for {self.arch.value}"
                )
                raise ValueError(msg_0)

    @property
    def pixi_suffix(self) -> str:
        """Naming convention used by pixi environments and build dirs."""
        return _PIXI_SUFFIX[(self.os_name, self.arch)]

    @property
    def build_dir_suffix(self) -> str:
        """Trailing token of ``ITK-<env>-<pixi>_<arch>`` build dirs."""
        return self.pixi_suffix

    @property
    def linux_triple(self) -> str:
        if self.os_name != "linux":
            msg = "linux_triple is only defined on linux"
            raise ValueError(msg)
        return f"{self.arch.value}-linux-gnu"

    @property
    def cmake_osx_arch(self) -> str:
        if self.os_name != "darwin":
            msg = "cmake_osx_arch is only defined on darwin"
            raise ValueError(msg)
        return "arm64" if self.arch is Arch.AARCH64 else self.arch.value

    @property
    def wheel_plat_tag(self) -> str:
        if self.os_name == "linux":
            return f"manylinux{self.manylinux_version}_{self.arch.value}"
        if self.os_name == "darwin":
            return f"macosx_{_MACOSX_DEPLOYMENT_TARGET}_{self.cmake_osx_arch}"
        return "win_amd64"

    @property
    def container_image(self) -> ContainerImage:
        if self.os_name != "linux" or not self.manylinux_version:
            msg = "container_image requires a manylinux linux target"
            raise ValueError(msg)
        tag = _MANYLINUX_IMAGE_TAGS[(self.arch, self.manylinux_version)]
        if self.arch is Arch.X86_64:
            # dockcross spells the arch with a hyphen and calls it x64.
            return ContainerImage(
                name=f"manylinux{self.manylinux_version}-x64:{tag}",
                registry="docker.io/dockcross",
            )
        return ContainerImage(
            name=f"manylinux{self.manylinux_version}_{self.arch.value}:{tag}",
            registry="quay.io/pypa",
        )

    @classmethod
    def detect(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        manylinux_version: str | None = None,
    ) -> TargetPlatform:
        """Resolve the *target* platform from uname and the environment.

        Parameters
        ----------
        manylinux_version : str, optional
            Overrides the ambient ``MANYLINUX_VERSION`` environment
            variable; ``""`` means "ignore ambient manylinux state".
        """
        env = os.environ if env is None else env
        uname = os.uname() if hasattr(os, "uname") else None
        sysname = uname.sysname.lower() if uname else ""
        if sysname.startswith("linux"):
            os_name = "linux"
        elif sysname.startswith("darwin"):
            os_name = "darwin"
        elif os.name == "nt":
            os_name = "windows"
        else:
            msg = f"Unsupported operating system {sysname!r}"
            raise ValueError(msg)

        # PROCESSOR_ARCHITECTURE describes the process environment, not the
        # package config mapping callers pass in as ``env``; fall back to the
        # real environment so Windows, which has no os.uname, still resolves.
        ambient_machine = env.get("PROCESSOR_ARCHITECTURE") or os.environ.get(
            "PROCESSOR_ARCHITECTURE", ""
        )
        machine = env.get("TARGET_ARCH") or (
            uname.machine if uname else ambient_machine
        )
        arch = _MACHINE_ALIASES.get(machine.lower())
        if arch is None:
            msg = f"Unknown machine {machine!r}"
            raise ValueError(msg)

        return cls(
            os_name=os_name,
            arch=arch,
            manylinux_version=(
                env.get("MANYLINUX_VERSION", "")
                if manylinux_version is None
                else manylinux_version
            ),
        )


def host_arch(env: Mapping[str, str] | None = None) -> Arch:
    """Architecture of the machine running the build.

    Deliberately distinct from the target: the QEMU-emulation decision
    is host-versus-target, and collapsing the two breaks cross-builds.
    """
    env = os.environ if env is None else env
    uname = os.uname() if hasattr(os, "uname") else None
    ambient_machine = env.get("PROCESSOR_ARCHITECTURE") or os.environ.get(
        "PROCESSOR_ARCHITECTURE", ""
    )
    machine = uname.machine if uname else ambient_machine
    arch = _MACHINE_ALIASES.get(machine.lower())
    if arch is None:
        msg = f"Unknown host machine {machine!r}"
        raise ValueError(msg)
    return arch
