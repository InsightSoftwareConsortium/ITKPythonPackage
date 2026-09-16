import re
import tomllib
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from target_platform import (
    _MACOSX_DEPLOYMENT_TARGET,
    Arch,
    ContainerImage,
    TargetPlatform,
)  # noqa: F401  (import check)

NICKNAMES = {"x64", "arm64", "amd64", "x86"}

# (os_name, arch, manylinux) -> (pixi_suffix, linux_triple,
#                                cmake_osx_arch, wheel_plat_tag)
EXPECTED = {
    ("linux", Arch.X86_64, "_2_28"): (
        "x64",
        "x86_64-linux-gnu",
        None,
        "manylinux_2_28_x86_64",
    ),
    ("linux", Arch.AARCH64, "_2_28"): (
        "aarch64",
        "aarch64-linux-gnu",
        None,
        "manylinux_2_28_aarch64",
    ),
    ("linux", Arch.X86_64, "_2_34"): (
        "x64",
        "x86_64-linux-gnu",
        None,
        "manylinux_2_34_x86_64",
    ),
    ("darwin", Arch.AARCH64, ""): (
        "arm64",
        None,
        "arm64",
        "macosx_14_0_arm64",
    ),
    ("windows", Arch.X86_64, ""): (
        "x64",
        None,
        None,
        "win_amd64",
    ),
}


@pytest.mark.parametrize("key", sorted(EXPECTED, key=repr))
def test_translations(key):
    os_name, arch, manylinux = key
    pixi, triple, osx, tag = EXPECTED[key]
    plat = TargetPlatform(os_name=os_name, arch=arch, manylinux_version=manylinux)
    assert plat.pixi_suffix == pixi
    assert plat.wheel_plat_tag == tag
    assert plat.build_dir_suffix == pixi
    if triple is not None:
        assert plat.linux_triple == triple
    if osx is not None:
        assert plat.cmake_osx_arch == osx


def test_unknown_manylinux_version_raises():
    with pytest.raises(ValueError, match="Unknown manylinux version"):
        TargetPlatform("linux", Arch.X86_64, "_2_99")


def test_unsupported_os_arch_combination_raises():
    with pytest.raises(ValueError, match="Unsupported combination"):
        TargetPlatform("darwin", Arch.I686)


def test_manylinux_on_non_linux_raises():
    with pytest.raises(ValueError, match="only meaningful on linux"):
        TargetPlatform("darwin", Arch.AARCH64, "_2_28")


def test_x86_64_uses_dockcross_with_hyphen():
    image = TargetPlatform("linux", Arch.X86_64, "_2_28").container_image
    assert image == ContainerImage(
        name="manylinux_2_28-x64:20250913-6ea98ba",
        registry="docker.io/dockcross",
    )
    assert image.reference == (
        "docker.io/dockcross/manylinux_2_28-x64:20250913-6ea98ba"
    )


def test_aarch64_uses_pypa_with_underscore():
    image = TargetPlatform("linux", Arch.AARCH64, "_2_28").container_image
    assert image == ContainerImage(
        name="manylinux_2_28_aarch64:2025.08.12-1",
        registry="quay.io/pypa",
    )
    assert image.reference == ("quay.io/pypa/manylinux_2_28_aarch64:2025.08.12-1")


@given(machine=st.text(max_size=20))
def test_detect_never_yields_a_nickname(machine):
    """detect() returns a canonical Arch or raises; never a nickname."""
    env = {"TARGET_ARCH": machine}
    try:
        plat = TargetPlatform.detect(env)
    except ValueError:
        return
    assert isinstance(plat.arch, Arch)
    assert plat.arch.value not in NICKNAMES
    assert plat.arch.value == plat.arch.value.lower()


def test_macos_wheel_plat_tag_is_installable_on_arm64():
    tag = TargetPlatform("darwin", Arch.AARCH64, "").wheel_plat_tag
    match = re.fullmatch(r"macosx_(\d+)_0_arm64", tag)
    assert match is not None
    assert int(match.group(1)) >= 11


def test_pixi_macos_system_requirement_matches_the_deployment_target():
    """pixi.toml is the third copy of the macOS version; bind it too.

    ``system-requirements = { macos = "14.0" }`` under
    ``[feature.macosx-build]`` must agree with
    ``target_platform._MACOSX_DEPLOYMENT_TARGET``, or the cached ITK build
    and the wheel tag disagree.
    """
    pixi_toml = Path(__file__).resolve().parent.parent / "pixi.toml"
    config = tomllib.loads(pixi_toml.read_text())
    macos_requirement = config["feature"]["macosx-build"]["system-requirements"][
        "macos"
    ]
    assert macos_requirement.replace(".", "_") == _MACOSX_DEPLOYMENT_TARGET
