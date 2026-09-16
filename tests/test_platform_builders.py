import os
import zipfile
from pathlib import Path
from unittest.mock import patch

from cmake_argument_builder import CMakeArgumentBuilder
from target_platform import Arch, TargetPlatform, host_arch


def test_build_dir_suffix_matches_pixi_suffix_on_all_platforms():
    """The ITK-<env>-<pixi>_<arch> expression has exactly one source."""
    for os_name, arch in (
        ("linux", Arch.X86_64),
        ("linux", Arch.AARCH64),
        ("darwin", Arch.AARCH64),
        ("windows", Arch.X86_64),
    ):
        plat = TargetPlatform(os_name, arch)
        assert plat.build_dir_suffix == plat.pixi_suffix


def _make_wheel(path: Path, members: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def test_fixup_wheel_skips_wheel_with_no_binaries(tmp_path, macos_builder):
    """The itk metapackage has no .so/.dylib, so delocate must not run."""
    wheel = _make_wheel(
        tmp_path / "itk-6.0.0-py3-none-any.whl", {"itk/__init__.py": ""}
    )
    # fixup_wheel calls remove_apple_double_files first, which itself
    # calls echo_check_call — patch it out so the assertion below is
    # about delocate and nothing else.
    with patch.object(macos_builder, "remove_apple_double_files"):
        with patch.object(macos_builder, "echo_check_call") as called:
            macos_builder.fixup_wheel(str(wheel))
    flat = " ".join(str(a) for c in called.call_args_list for a in c.args[0])
    assert "delocate-wheel" not in flat


def test_fixup_wheel_runs_delocate_when_binaries_present(tmp_path, macos_builder):
    wheel = _make_wheel(
        tmp_path / "itk_core-6.0.0-cp311-abi3-macosx_11_0_arm64.whl",
        {"itk/_ITKCommonPython.so": "\x7fELF"},
    )
    with patch.object(macos_builder, "echo_check_call") as called:
        macos_builder.fixup_wheel(str(wheel))
    assert called.call_count >= 1
    flat = " ".join(str(a) for c in called.call_args_list for a in c.args[0])
    assert "delocate-wheel" in flat
    assert "--require-archs" in flat


def test_posix_build_tarball_delegates(macos_builder):
    """build_tarball is a base hook now; the Middle Man override is gone."""
    with patch.object(macos_builder, "create_posix_tarball") as created:
        macos_builder.build_tarball()
    created.assert_called_once()


def test_prepare_build_env_uses_existing_downloaded_binaries(macos_builder):
    """Pin the downloaded-cache probe, whose platform_env appears twice.

    The spelling is preserved verbatim from the verified macOS builder.
    """
    build_root = macos_builder.build_dir_root / "build"
    doubled = build_root / "ITK-macosx-py311-macosx-py311_arm64"
    doubled.mkdir(parents=True)
    macos_builder.cmake_itk_source_build_configurations = CMakeArgumentBuilder()
    with (
        patch.object(macos_builder, "venv_paths"),
        patch.object(macos_builder, "update_venv_itk_build_configurations"),
        patch.object(macos_builder, "_configure_toolchain"),
    ):
        macos_builder.prepare_build_env()
    assert (
        macos_builder.cmake_itk_source_build_configurations.get("ITK_BINARY_DIR:PATH")
        == doubled.as_posix()
    )


def test_configure_toolchain_routes_arch_through_the_target(macos_builder):
    """macOS reads CMAKE_OSX_ARCHITECTURES from the type, not from ARCH."""
    macos_builder.cmake_compiler_configurations = CMakeArgumentBuilder()
    macos_builder.package_env_config = {"ARCH": "ignored-by-design"}
    macos_builder._configure_toolchain()
    assert (
        macos_builder.cmake_compiler_configurations.get(
            "CMAKE_OSX_ARCHITECTURES:STRING"
        )
        == "arm64"
    )
    assert macos_builder.package_env_config["TBB_DIR"] == "NOT_FOUND"


def test_host_arch_is_independent_of_target():
    """QEMU reads the host; a cross-build sets only the target."""
    target = TargetPlatform.detect({"TARGET_ARCH": "aarch64"})
    assert target.arch is Arch.AARCH64
    assert host_arch({}) in set(Arch)
