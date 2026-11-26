import os
import re
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
from build_wheels import in_manylinux_container, remotemodulebuildandtestaction
from hypothesis import given
from hypothesis import strategies as st
from target_platform import (
    _MACOSX_DEPLOYMENT_TARGET,
    OS,
    Arch,
    ContainerImage,
    TargetPlatform,
    manylinux_version_from_platform_env,
)

NICKNAMES = {"x64", "arm64", "amd64", "x86"}

# (os_name, arch, manylinux) -> (pixi_suffix, linux_triple,
#                                cmake_osx_arch, wheel_plat_tag)
EXPECTED = {
    (OS.LINUX, Arch.X86_64, "_2_28"): (
        "x64",
        "x86_64-linux-gnu",
        None,
        "manylinux_2_28_x86_64",
    ),
    (OS.LINUX, Arch.AARCH64, "_2_28"): (
        "aarch64",
        "aarch64-linux-gnu",
        None,
        "manylinux_2_28_aarch64",
    ),
    (OS.LINUX, Arch.X86_64, "_2_34"): (
        "x64",
        "x86_64-linux-gnu",
        None,
        "manylinux_2_34_x86_64",
    ),
    (OS.DARWIN, Arch.AARCH64, ""): (
        "arm64",
        None,
        "arm64",
        "macosx_14_0_arm64",
    ),
    (OS.WINDOWS, Arch.X86_64, ""): (
        "x64",
        None,
        None,
        "win_amd64",
    ),
}


@pytest.mark.parametrize("key", sorted(EXPECTED, key=repr))
def test_translations(key: tuple[OS, Arch, str]) -> None:
    os_name, arch, manylinux = key
    pixi, triple, osx, tag = EXPECTED[key]
    plat = TargetPlatform(os_name=os_name, arch=arch, manylinux_version=manylinux)
    assert plat.pixi_suffix == pixi
    assert plat.wheel_plat_tag == tag
    if triple is not None:
        assert plat.linux_triple == triple
    if osx is not None:
        assert plat.cmake_osx_arch == osx


def test_unknown_manylinux_version_raises() -> None:
    with pytest.raises(ValueError, match="Unknown manylinux version"):
        TargetPlatform(OS.LINUX, Arch.X86_64, "_2_99")


def test_unsupported_os_arch_combination_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported combination"):
        TargetPlatform(OS.DARWIN, Arch.X86_64)


def test_manylinux_on_non_linux_raises() -> None:
    with pytest.raises(ValueError, match="only meaningful on linux"):
        TargetPlatform(OS.DARWIN, Arch.AARCH64, "_2_28")


def test_x86_64_uses_dockcross_with_hyphen() -> None:
    image = TargetPlatform(OS.LINUX, Arch.X86_64, "_2_28").container_image
    assert image == ContainerImage(
        name="manylinux_2_28-x64:20260203-3dfb3ff",
        registry="docker.io/dockcross",
    )
    assert image.reference == (
        "docker.io/dockcross/manylinux_2_28-x64:20260203-3dfb3ff"
    )


def test_aarch64_uses_pypa_with_underscore() -> None:
    image = TargetPlatform(OS.LINUX, Arch.AARCH64, "_2_28").container_image
    assert image == ContainerImage(
        name="manylinux_2_28_aarch64:2025.08.12-1",
        registry="quay.io/pypa",
    )
    assert image.reference == ("quay.io/pypa/manylinux_2_28_aarch64:2025.08.12-1")


def _fake_uname(sysname: str, machine: str) -> SimpleNamespace:
    return SimpleNamespace(sysname=sysname, machine=machine)


def _patch_posix_uname(
    monkeypatch: pytest.MonkeyPatch, sysname: str, machine: str
) -> None:
    """Present a POSIX ``os.uname`` to the code under test.

    ``raising=False`` because Windows has no ``os.uname`` to replace;
    monkeypatch removes the attribute again on teardown. Without it these
    tests error with ``AttributeError`` on Windows before reaching any
    assertion.
    """
    monkeypatch.setattr(
        os, "uname", lambda: _fake_uname(sysname, machine), raising=False
    )
    monkeypatch.setattr(os, "name", "posix")


def test_detect_resolves_linux_sysname(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_posix_uname(monkeypatch, "Linux", "x86_64")
    plat = TargetPlatform.detect({})
    assert plat.os_name is OS.LINUX


def test_detect_resolves_darwin_sysname(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_posix_uname(monkeypatch, "Darwin", "arm64")
    plat = TargetPlatform.detect({})
    assert plat.os_name is OS.DARWIN


def test_detect_resolves_windows_via_os_name_nt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(os, "uname", raising=False)
    monkeypatch.setattr(os, "name", "nt")
    plat = TargetPlatform.detect({"PROCESSOR_ARCHITECTURE": "AMD64"})
    assert plat.os_name is OS.WINDOWS


def test_detect_unsupported_sysname_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_posix_uname(monkeypatch, "PlayStation", "x86_64")
    with pytest.raises(ValueError, match="Unsupported operating system"):
        TargetPlatform.detect({})


def test_detect_target_arch_env_overrides_host_machine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_posix_uname(monkeypatch, "Linux", "aarch64")
    plat = TargetPlatform.detect({"TARGET_ARCH": "x86_64"})
    assert plat.arch is Arch.X86_64


def test_detect_falls_back_to_uname_machine_without_target_arch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_posix_uname(monkeypatch, "Linux", "aarch64")
    plat = TargetPlatform.detect({})
    assert plat.arch is Arch.AARCH64


@given(machine=st.text(max_size=20))
def test_detect_never_yields_a_nickname(machine: str) -> None:
    """detect() returns a canonical Arch or raises; never a nickname."""
    env = {"TARGET_ARCH": machine}
    try:
        plat = TargetPlatform.detect(env)
    except ValueError:
        return
    assert isinstance(plat.arch, Arch)
    assert plat.arch.value not in NICKNAMES
    assert plat.arch.value == plat.arch.value.lower()


def test_detect_manylinux_override_ignores_ambient_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_posix_uname(monkeypatch, "Linux", "aarch64")
    env = {"MANYLINUX_VERSION": "_2_34"}
    plat = TargetPlatform.detect(env, manylinux_version="")
    assert plat.manylinux_version == ""


def test_detect_default_reads_ambient_manylinux_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_posix_uname(monkeypatch, "Linux", "x86_64")
    env = {"MANYLINUX_VERSION": "_2_28"}
    plat = TargetPlatform.detect(env)
    assert plat.manylinux_version == "_2_28"


def test_detect_manylinux_override_still_validates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_posix_uname(monkeypatch, "Linux", "x86_64")
    with pytest.raises(ValueError, match="Unknown manylinux version"):
        TargetPlatform.detect({}, manylinux_version="_2_99")


def test_macosx_deployment_target_matches_wheel_tag_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MACOSX_DEPLOYMENT_TARGET", raising=False)
    build_default = remotemodulebuildandtestaction()["MACOSX_DEPLOYMENT_TARGET"]
    assert build_default.replace(".", "_") == _MACOSX_DEPLOYMENT_TARGET


def test_macos_wheel_plat_tag_is_installable_on_arm64() -> None:
    tag = TargetPlatform(OS.DARWIN, Arch.AARCH64, "").wheel_plat_tag
    match = re.fullmatch(r"macosx_(\d+)_0_arm64", tag)
    assert match is not None
    assert int(match.group(1)) >= 11


def test_pixi_macos_system_requirement_matches_the_deployment_target() -> None:
    """pixi.toml is the third copy of the macOS version; bind it too.

    The ``macos`` virtual package on the workspace platform that
    ``[feature.macosx-build]`` uses must agree with
    ``target_platform._MACOSX_DEPLOYMENT_TARGET``, or the cached ITK build
    and the wheel tag disagree.
    """
    pixi_toml = Path(__file__).resolve().parent.parent / "pixi.toml"
    config = tomllib.loads(pixi_toml.read_text())
    (platform_name,) = config["feature"]["macosx-build"]["platforms"]
    (platform_entry,) = [
        entry
        for entry in config["workspace"]["platforms"]
        if isinstance(entry, dict) and entry.get("name") == platform_name
    ]
    assert platform_entry["macos"].replace(".", "_") == _MACOSX_DEPLOYMENT_TARGET


@pytest.mark.parametrize(
    ("platform_env", "expected"),
    [
        ("manylinux228-py311", "_2_28"),
        ("manylinux_2_28-py311", "_2_28"),
        ("manylinux234-py311", "_2_34"),
        ("/repo/.pixi/envs/manylinux228-py311", "_2_28"),
        ("linux-py311", ""),
        ("macosx-py311", ""),
        ("windows-py311", ""),
        ("manylinux-py311", ""),
    ],
)
def test_manylinux_version_is_implied_by_the_platform_env(
    platform_env: str, expected: str
) -> None:
    assert manylinux_version_from_platform_env(platform_env) == expected


@pytest.mark.parametrize(
    ("env", "inside"),
    [
        ({}, False),
        ({"CROSS_TRIPLE": "x86_64-linux-gnu"}, True),
        ({"AUDITWHEEL_PLAT": "manylinux_2_28_aarch64"}, True),
        ({"CROSS_TRIPLE": "", "AUDITWHEEL_PLAT": ""}, False),
    ],
)
def test_both_manylinux_images_count_as_the_container(
    env: dict[str, str], inside: bool
) -> None:
    """The aarch64 build uses a pypa image, which has no CROSS_TRIPLE."""
    assert in_manylinux_container(env) is inside
