import argparse
from pathlib import Path

import pytest
from build_config import BuildConfig, BuildConfigError
from target_platform import OS, Arch, TargetPlatform


def _args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "itk_source_dir": Path("/bdr/ITK"),
        "build_dir_root": Path("/bdr"),
        "itk_git_tag": "v6.0b02",
        "itk_package_version": "6.0.0b2",
        "macosx_deployment_target": "14.0",
        "itk_module_deps": "",
        "use_ccache": False,
        "manylinux_version": "",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _build(
    target: TargetPlatform,
    env: dict[str, str],
    args: argparse.Namespace,
    python_executable: str = "/env/bin/python",
) -> BuildConfig:
    return BuildConfig.from_args_and_env(
        args,
        env,
        target=target,
        pixi_executable=Path("/px/pixi"),
        cmake_executable=Path("/env/bin/cmake"),
        ninja_executable=Path("/env/bin/ninja"),
        doxygen_executable=Path("/env/bin/doxygen"),
        git_executable=Path("/env/bin/git"),
        python_executable=python_executable,
        oci_exe="docker",
    )


def _config(
    target: TargetPlatform,
    env: dict[str, str] | None = None,
    **overrides: object,
) -> BuildConfig:
    return _build(target, env or {}, _args(**overrides))


COMMON_TAIL = [
    ("ITK_MODULE_PREQ", ""),
    ("ITK_MODULE_NO_CLEANUP", "1"),
    ("USE_CCACHE", "OFF"),
    ("PIXI_EXECUTABLE", "/px/pixi"),
    ("CMAKE_EXECUTABLE", "/env/bin/cmake"),
    ("NINJA_EXECUTABLE", "/env/bin/ninja"),
    ("DOXYGEN_EXECUTABLE", "/env/bin/doxygen"),
    ("GIT_EXECUTABLE", "/env/bin/git"),
    ("PYTHON_EXECUTABLE", "/env/bin/python"),
    ("OCI_EXE", "docker"),
]


def _head(os_name: str, arch: str) -> list[tuple[str, str]]:
    return [
        ("ITK_SOURCE_DIR", "/bdr/ITK"),
        ("IPP_SUPERBUILD_BINARY_DIR", "/bdr/build/ITK-support-bld"),
        ("OS_NAME", os_name),
        ("ARCH", arch),
        ("BUILD_DIR_ROOT", "/bdr"),
        ("ITK_GIT_TAG", "v6.0b02"),
        ("ITK_PACKAGE_VERSION", "6.0.0b2"),
    ]


def test_manylinux_environment_lists_every_key_in_order() -> None:
    config = _config(TargetPlatform(OS.LINUX, Arch.X86_64), manylinux_version="_2_28")
    assert list(config.to_environment().items()) == [
        *_head("linux", "x64"),
        *COMMON_TAIL,
        ("MANYLINUX_VERSION", "_2_28"),
        ("MANYLINUX_IMAGE_NAME", "manylinux_2_28-x64:20260203-3dfb3ff"),
        ("CONTAINER_SOURCE", "docker.io/dockcross/manylinux_2_28-x64:20260203-3dfb3ff"),
        ("TARGET_ARCH", "x86_64"),
    ]
    assert config.target == TargetPlatform(OS.LINUX, Arch.X86_64, "_2_28")


def test_native_linux_environment_has_no_container_keys() -> None:
    config = _config(TargetPlatform(OS.LINUX, Arch.AARCH64))
    assert list(config.to_environment().items()) == [
        *_head("linux", "aarch64"),
        *COMMON_TAIL,
    ]
    assert config.target.manylinux_version == ""


def test_macos_environment_carries_the_deployment_target() -> None:
    config = _config(TargetPlatform(OS.DARWIN, Arch.AARCH64))
    assert list(config.to_environment().items()) == [
        *_head("darwin", "arm64"),
        ("MACOSX_DEPLOYMENT_TARGET", "14.0"),
        *COMMON_TAIL,
    ]


def test_macos_ignores_an_ambient_manylinux_version() -> None:
    config = _config(TargetPlatform(OS.DARWIN, Arch.AARCH64), manylinux_version="_2_28")
    assert config.target.manylinux_version == ""
    assert "MANYLINUX_VERSION" not in config.to_environment()


def test_windows_has_no_deployment_target() -> None:
    config = _config(
        TargetPlatform(OS.WINDOWS, Arch.X86_64), macosx_deployment_target="14.0"
    )
    assert config.macosx_deployment_target is None
    assert list(config.to_environment().items()) == [
        *_head("windows", "x64"),
        *COMMON_TAIL,
    ]


def test_fields_are_typed() -> None:
    config = _config(
        TargetPlatform(OS.LINUX, Arch.X86_64),
        itk_source_dir="/src/ITK",
        build_dir_root="/b",
    )
    assert config.itk_source_dir == Path("/src/ITK")
    assert config.build_dir_root == Path("/b")
    assert config.ipp_superbuild_binary_dir == Path("/b/build/ITK-support-bld")
    assert config.python_executable == Path("/env/bin/python")


@pytest.mark.parametrize(
    ("flag", "env", "expected"),
    [
        (False, {"USE_CCACHE": "1"}, "ON"),
        (False, {}, "OFF"),
        (True, {}, "ON"),
    ],
)
def test_ccache_is_on_with_the_flag_or_the_environment(
    flag: bool, env: dict[str, str], expected: str
) -> None:
    config = _config(TargetPlatform(OS.LINUX, Arch.X86_64), env, use_ccache=flag)
    assert config.to_environment()["USE_CCACHE"] == expected


def test_module_no_cleanup_comes_from_the_environment() -> None:
    config = _config(
        TargetPlatform(OS.LINUX, Arch.X86_64), {"ITK_MODULE_NO_CLEANUP": "0"}
    )
    assert config.itk_module_no_cleanup is False
    assert config.to_environment()["ITK_MODULE_NO_CLEANUP"] == "0"


def test_module_no_cleanup_must_be_a_flag() -> None:
    with pytest.raises(BuildConfigError, match="ITK_MODULE_NO_CLEANUP"):
        _config(TargetPlatform(OS.LINUX, Arch.X86_64), {"ITK_MODULE_NO_CLEANUP": "x"})


@pytest.mark.parametrize(
    ("target", "overrides", "field"),
    [
        (
            TargetPlatform(OS.DARWIN, Arch.AARCH64),
            {"macosx_deployment_target": "fourteen"},
            "macosx_deployment_target",
        ),
        (
            TargetPlatform(OS.LINUX, Arch.AARCH64),
            {"manylinux_version": "_2_34"},
            "manylinux_version",
        ),
        (
            TargetPlatform(OS.LINUX, Arch.X86_64),
            {"itk_git_tag": ""},
            "itk_git_tag",
        ),
        (
            TargetPlatform(OS.LINUX, Arch.X86_64),
            {"itk_source_dir": None},
            "itk_source_dir",
        ),
    ],
)
def test_bad_values_are_rejected_by_name(
    target: TargetPlatform, overrides: dict[str, object], field: str
) -> None:
    value = next(iter(overrides.values()))
    with pytest.raises(BuildConfigError, match=rf"^{field}={value!r}: ") as raised:
        _build(target, {}, _args(**overrides))
    assert raised.value.field == field


def test_an_empty_python_executable_is_rejected() -> None:
    with pytest.raises(BuildConfigError, match=r"^python_executable='': "):
        _build(TargetPlatform(OS.LINUX, Arch.X86_64), {}, _args(), "")


def test_an_empty_deployment_target_means_none_is_set() -> None:
    config = _config(
        TargetPlatform(OS.DARWIN, Arch.AARCH64), macosx_deployment_target=""
    )
    assert config.to_environment()["MACOSX_DEPLOYMENT_TARGET"] == ""


def test_config_is_frozen() -> None:
    config = _config(TargetPlatform(OS.LINUX, Arch.X86_64))
    with pytest.raises(AttributeError):
        config.itk_git_tag = "other"  # type: ignore[misc]
