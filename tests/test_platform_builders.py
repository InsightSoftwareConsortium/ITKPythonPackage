import os
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cmake_argument_builder import CMakeArgumentBuilder
from target_platform import Arch, TargetPlatform, host_arch


def test_build_dir_suffix_is_the_documented_token_per_platform():
    """Spell out the ``_{arch}`` token of ``ITK-<env>-<pixi>_<arch>``.

    Literal expectations, so a change to the mapping fails here. Comparing
    ``build_dir_suffix`` against ``pixi_suffix`` would not: the former is
    defined as ``return self.pixi_suffix``.
    """
    expected = {
        ("linux", Arch.X86_64): "x64",
        ("linux", Arch.AARCH64): "aarch64",
        ("linux", Arch.I686): "x86",
        ("darwin", Arch.AARCH64): "arm64",
        ("darwin", Arch.X86_64): "x86_64",
        ("windows", Arch.X86_64): "x64",
    }
    for (os_name, arch), token in expected.items():
        assert TargetPlatform(os_name, arch).build_dir_suffix == token


@pytest.mark.parametrize(
    ("builder_fixture", "expected_suffix"),
    [
        ("linux_builder", "x64"),
        ("linux_aarch64_builder", "aarch64"),
        ("macos_builder", "arm64"),
        ("windows_builder", "x64"),
    ],
)
def test_prepare_build_env_sets_itk_binary_dir_on_every_platform(
    request, builder_fixture, expected_suffix
):
    """The ITK binary directory has exactly one construction site.

    This drives the real template method, including each subclass's real
    ``_configure_toolchain``. A subclass that reintroduced its own path
    construction, or that supplied the wrong architecture token, fails here.
    """
    builder = request.getfixturevalue(builder_fixture)
    with (
        patch.object(builder, "venv_paths"),
        patch.object(builder, "update_venv_itk_build_configurations"),
    ):
        builder.prepare_build_env()

    expected = (
        builder.build_dir_root
        / "build"
        / f"ITK-{builder.platform_env}-{builder.platform_env}_{expected_suffix}"
    ).as_posix()
    assert (
        builder.cmake_itk_source_build_configurations.get("ITK_BINARY_DIR:PATH")
        == expected
    )


def test_linux_configure_toolchain_takes_the_triple_from_the_target(
    linux_builder, linux_aarch64_builder
):
    """The four-branch ARCH cascade is gone; the type supplies the triple."""
    for builder, triple in (
        (linux_builder, "x86_64-linux-gnu"),
        (linux_aarch64_builder, "aarch64-linux-gnu"),
    ):
        builder._configure_toolchain()
        assert (
            builder.cmake_compiler_configurations.get(
                "CMAKE_CXX_COMPILER_TARGET:STRING"
            )
            == triple
        )
        assert builder.package_env_config["USE_TBB"] == "ON"
        # One key, one type: TBB_DIR is a str on Linux as well as Windows.
        assert isinstance(builder.package_env_config["TBB_DIR"], str)


def test_windows_configure_toolchain_sets_tbb_dir_as_str(windows_builder):
    windows_builder._configure_toolchain()
    assert windows_builder.package_env_config["USE_TBB"] == "ON"
    tbb_dir = windows_builder.package_env_config["TBB_DIR"]
    assert isinstance(tbb_dir, str)
    assert tbb_dir.endswith("TBB")


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


def _make_build_env(tmp_path: Path) -> Path:
    """A minimal ``<prefix>/{bin,lib}`` layout for PYTHON_EXECUTABLE."""
    env_root = tmp_path / "env"
    (env_root / "bin").mkdir(parents=True, exist_ok=True)
    (env_root / "lib").mkdir(parents=True, exist_ok=True)
    (env_root / "bin" / "python").touch()
    return env_root


def _prepare_linux_fixup(linux_builder, tmp_path, module_source_dir=None):
    linux_builder.package_env_config.update(
        {
            "MANYLINUX_VERSION": "_2_28",
            "PYTHON_EXECUTABLE": str(_make_build_env(tmp_path) / "bin" / "python"),
            "IPP_SUPERBUILD_BINARY_DIR": tmp_path / "superbuild",
        }
    )
    linux_builder.module_source_dir = module_source_dir
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(exist_ok=True)
    wheel = _make_wheel(
        dist_dir / "itk_core-6.0.0-cp311-abi3-linux_x86_64.whl",
        {"itk/_ITKCommonPython.so": "\x7fELF"},
    )
    repaired_name = "itk_core-6.0.0-cp311-abi3-manylinux_2_28_x86_64.whl"
    return wheel, dist_dir / repaired_name


def test_fixup_wheel_raises_and_keeps_original_when_repair_fails(
    tmp_path, linux_builder
):
    """A failed auditwheel repair must not delete the input wheel."""
    wheel, repaired = _prepare_linux_fixup(linux_builder, tmp_path)
    with patch.object(linux_builder, "echo_check_call", return_value=1):
        with pytest.raises(RuntimeError):
            linux_builder.fixup_wheel(str(wheel))
    assert wheel.exists()
    assert not repaired.exists()


def test_fixup_wheel_raises_when_repair_reports_success_but_output_missing(
    tmp_path, linux_builder
):
    """echo_check_call reporting 0 is not enough without the output wheel."""
    wheel, repaired = _prepare_linux_fixup(linux_builder, tmp_path)
    with patch.object(linux_builder, "echo_check_call", return_value=0):
        with pytest.raises(RuntimeError):
            linux_builder.fixup_wheel(str(wheel))
    assert wheel.exists()


def test_fixup_wheel_removes_original_only_after_verified_repair(
    tmp_path, linux_builder
):
    wheel, repaired = _prepare_linux_fixup(linux_builder, tmp_path)

    def fake_repair(cmd, env=None):
        repaired.touch()
        return 0

    with patch.object(linux_builder, "echo_check_call", side_effect=fake_repair):
        linux_builder.fixup_wheel(str(wheel))
    assert not wheel.exists()
    assert repaired.exists()


def _capture_repair_env(builder, wheel, repaired) -> dict:
    captured_env = {}

    def fake_repair(cmd, env=None):
        captured_env.update(env)
        repaired.touch()
        return 0

    with patch.object(builder, "echo_check_call", side_effect=fake_repair):
        builder.fixup_wheel(str(wheel))
    return captured_env


def test_fixup_wheel_ld_library_path_starts_with_the_build_env_lib_dir(
    tmp_path, linux_builder, monkeypatch
):
    """The environment's own lib dir must precede the system dirs.

    It is derived from PYTHON_EXECUTABLE, so it is present whether or not
    CONDA_PREFIX happens to be exported.
    """
    monkeypatch.delenv("CONDA_PREFIX", raising=False)
    wheel, repaired = _prepare_linux_fixup(linux_builder, tmp_path)
    ld_library_path = _capture_repair_env(linux_builder, wheel, repaired)[
        "LD_LIBRARY_PATH"
    ]
    env_lib = str((_make_build_env(tmp_path) / "lib").resolve())
    # Compare positions in the joined string rather than indices in a
    # ":"-split list: tmp_path carries a drive letter off a POSIX box, and
    # its colon would split one entry into two.
    assert ld_library_path.index(env_lib) < ld_library_path.index("/usr/lib64")


def test_fixup_wheel_ld_library_path_has_no_empty_entries(tmp_path, linux_builder):
    """An empty entry means the working directory to the dynamic loader."""
    wheel, repaired = _prepare_linux_fixup(linux_builder, tmp_path)
    entries = _capture_repair_env(linux_builder, wheel, repaired)[
        "LD_LIBRARY_PATH"
    ].split(":")
    assert "" not in entries


def test_fixup_wheel_fails_loudly_when_the_build_env_lib_dir_is_absent(
    tmp_path, linux_builder
):
    """Silently omitting the env lib dir is what reintroduced defect C."""
    wheel, repaired = _prepare_linux_fixup(linux_builder, tmp_path)
    linux_builder.package_env_config["PYTHON_EXECUTABLE"] = str(
        tmp_path / "no-such-env" / "bin" / "python"
    )
    with patch.object(linux_builder, "echo_check_call", return_value=0):
        with pytest.raises(RuntimeError, match="library directory"):
            linux_builder.fixup_wheel(str(wheel))


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
    macos_builder.package_env_config = {"ARCH": "ignored-by-design"}
    macos_builder._configure_toolchain()
    assert (
        macos_builder.cmake_compiler_configurations.get(
            "CMAKE_OSX_ARCHITECTURES:STRING"
        )
        == "arm64"
    )
    assert macos_builder.package_env_config["TBB_DIR"] == "NOT_FOUND"


def test_configure_toolchain_sets_python_host_platform_from_the_same_values(
    macos_builder, monkeypatch
):
    """_PYTHON_HOST_PLATFORM must be derived, not a second hardcoded fact.

    The version is a sentinel no production default could equal, so a
    literal (e.g. "macosx-14.0-arm64") cannot coincidentally satisfy this.
    Fails if the version or the architecture is hardcoded, or if the two
    settings are allowed to drift apart.
    """
    monkeypatch.delenv("_PYTHON_HOST_PLATFORM", raising=False)
    monkeypatch.delenv("MACOSX_DEPLOYMENT_TARGET", raising=False)
    macos_builder.package_env_config["MACOSX_DEPLOYMENT_TARGET"] = "99.5"
    macos_builder._configure_toolchain()
    assert (
        os.environ["_PYTHON_HOST_PLATFORM"]
        == f"macosx-99.5-{macos_builder.target.cmake_osx_arch}"
    )


def test_configure_toolchain_leaves_python_host_platform_unset_without_a_target(
    macos_builder, monkeypatch
):
    """No macosx_target means no malformed 'macosx--<arch>' value."""
    monkeypatch.delenv("_PYTHON_HOST_PLATFORM", raising=False)
    macos_builder.package_env_config.pop("MACOSX_DEPLOYMENT_TARGET", None)
    macos_builder._configure_toolchain()
    assert "_PYTHON_HOST_PLATFORM" not in os.environ


def test_host_arch_is_independent_of_target(monkeypatch):
    """QEMU reads the host; a cross-build sets only the target.

    The host is pinned to Linux/x86_64 so the assertion does not depend on
    where the suite runs. Off a POSIX box ``detect`` would otherwise pair
    the real OS with the requested aarch64 target and raise on the
    unsupported windows/aarch64 combination before reaching the assert.
    """
    monkeypatch.setattr(
        os,
        "uname",
        lambda: SimpleNamespace(sysname="Linux", machine="x86_64"),
        raising=False,
    )
    monkeypatch.setattr(os, "name", "posix")
    target = TargetPlatform.detect({"TARGET_ARCH": "aarch64"})
    assert target.arch is Arch.AARCH64
    assert host_arch({}) in set(Arch)


def _checking_echo(failing_tool: str):
    """A stand-in with build_environment.echo_check_call's semantics.

    It returns a non-zero status for *failing_tool* and raises only when
    the caller forwarded ``check=True`` — so a call site that omits the
    flag sees the failure silently, exactly as production would.
    """

    def _echo(cmd, *args, check: bool = False, **kwargs) -> int:
        rendered = " ".join(str(c) for c in cmd)
        if failing_tool in rendered:
            if check:
                raise RuntimeError(f"command failed: {rendered}")
            return 1
        return 0

    return _echo


def _wire_itk_cplusplus(builder, tmp_path):
    builder.cleanup = False
    builder.build_node_cpu_count = 2
    builder.build_load_limit = 2
    builder.cmake_cmdline_definitions = CMakeArgumentBuilder()
    builder.cmake_itk_source_build_configurations.set(
        "ITK_BINARY_DIR:PATH", str(tmp_path / "itk-bld")
    )
    builder.package_env_config.update(
        {
            "CMAKE_EXECUTABLE": "cmake",
            "NINJA_EXECUTABLE": "ninja",
            "ITK_SOURCE_DIR": str(tmp_path / "ITK"),
        }
    )


@pytest.mark.parametrize("failing_tool", ["cmake", "ninja"])
def test_itk_cplusplus_build_raises_when_a_step_fails(
    tmp_path, linux_builder, failing_tool
):
    """A failed configure or ninja must not be recorded as a done step."""
    _wire_itk_cplusplus(linux_builder, tmp_path)
    with patch.object(
        linux_builder, "echo_check_call", side_effect=_checking_echo(failing_tool)
    ):
        with pytest.raises(RuntimeError):
            linux_builder.build_wrapped_itk_cplusplus()


def test_superbuild_support_components_raise_when_cmake_fails(tmp_path, linux_builder):
    """The superbuild configure/build pair must stop the run on failure."""
    linux_builder.cmake_cmdline_definitions = CMakeArgumentBuilder()
    linux_builder.package_env_config.update(
        {
            "CMAKE_EXECUTABLE": "cmake",
            "USE_TBB": "ON",
            "ITK_SOURCE_DIR": str(tmp_path / "ITK"),
            "ITK_GIT_TAG": "main",
            "IPP_SOURCE_DIR": tmp_path / "ipp",
            "IPP_SUPERBUILD_BINARY_DIR": tmp_path / "superbuild",
        }
    )
    with patch.object(
        linux_builder, "echo_check_call", side_effect=_checking_echo("cmake")
    ):
        with pytest.raises(RuntimeError):
            linux_builder.build_superbuild_support_components()


def test_superbuild_support_components_raise_when_the_build_fails(
    tmp_path, linux_builder
):
    """The configure can pass and the build still fail (a oneTBB download
    that never completes). That was recorded as a done step and surfaced
    later as a missing TBBConfig.cmake in step 02."""
    linux_builder.cmake_cmdline_definitions = CMakeArgumentBuilder()
    linux_builder.package_env_config.update(
        {
            "CMAKE_EXECUTABLE": "cmake",
            "USE_TBB": "ON",
            "ITK_SOURCE_DIR": str(tmp_path / "ITK"),
            "ITK_GIT_TAG": "main",
            "IPP_SOURCE_DIR": tmp_path / "ipp",
            "IPP_SUPERBUILD_BINARY_DIR": tmp_path / "superbuild",
        }
    )
    with patch.object(
        linux_builder, "echo_check_call", side_effect=_checking_echo("--build")
    ):
        with pytest.raises(RuntimeError):
            linux_builder.build_superbuild_support_components()


def _prepare_metawheel(linux_builder, tmp_path) -> Path:
    linux_builder.package_env_config.update(
        {
            "MANYLINUX_VERSION": "_2_28",
            "PYTHON_EXECUTABLE": str(_make_build_env(tmp_path) / "bin" / "python"),
        }
    )
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(exist_ok=True)
    metawhl = _make_wheel(
        dist_dir / "itk-6.0.0-cp311-abi3-linux_x86_64.whl",
        {"itk-6.0.0.dist-info/WHEEL": "Tag: cp311-abi3-linux_x86_64"},
    )
    return metawhl


def test_metawheel_is_kept_when_repack_produces_nothing(tmp_path, linux_builder):
    """The original meta-wheel must survive a repack that yields no wheel."""
    metawhl = _prepare_metawheel(linux_builder, tmp_path)

    def fake_unpack(cmd, *args, check: bool = False, **kwargs) -> int:
        rendered = [str(c) for c in cmd]
        if "unpack" in rendered:
            unpacked = tmp_path / "metawheel" / "itk-6.0.0" / "itk.dist-info"
            unpacked.mkdir(parents=True, exist_ok=True)
            (unpacked / "WHEEL").write_text("Tag: cp311-abi3-linux_x86_64\n")
        # "pack" reports success but writes nothing.
        return 0

    with patch.object(linux_builder, "echo_check_call", side_effect=fake_unpack):
        with pytest.raises(RuntimeError, match="no wheel"):
            linux_builder.post_build_fixup()
    assert metawhl.exists()


def test_metawheel_repack_failure_raises_and_keeps_the_original(
    tmp_path, linux_builder
):
    """`wheel pack` returning non-zero must stop the fixup, not be ignored."""
    metawhl = _prepare_metawheel(linux_builder, tmp_path)

    def fake(cmd, *args, check: bool = False, **kwargs) -> int:
        rendered = [str(c) for c in cmd]
        if "unpack" in rendered:
            unpacked = tmp_path / "metawheel" / "itk-6.0.0" / "itk.dist-info"
            unpacked.mkdir(parents=True, exist_ok=True)
            (unpacked / "WHEEL").write_text("Tag: cp311-abi3-linux_x86_64\n")
            return 0
        if check:
            raise RuntimeError("wheel pack failed")
        return 1

    with patch.object(linux_builder, "echo_check_call", side_effect=fake):
        with pytest.raises(RuntimeError):
            linux_builder.post_build_fixup()
    assert metawhl.exists()


def test_windows_fixup_wheel_raises_when_delvewheel_fails(tmp_path, windows_builder):
    """A failed delvewheel repair must not be reported as a success."""
    dist_dir = windows_builder.build_dir_root / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    wheel = dist_dir / "itk_core-6.0.0-cp311-abi3-win_amd64.whl"
    wheel.touch()
    with patch.object(windows_builder, "echo_check_call", return_value=1):
        with pytest.raises(RuntimeError, match="delvewheel"):
            windows_builder.fixup_wheel(str(wheel), lib_paths="C:/tbb/bin")


def test_windows_lib_paths_are_split_on_semicolons(windows_builder):
    """--lib-paths arrives as one semicolon-delimited string, not characters."""
    windows_builder.windows_extra_lib_paths = ["C:/tbb/bin;C:/extra/bin;"]
    captured = {}

    def fake_fixup_wheels(lib_paths):
        captured["lib_paths"] = lib_paths

    with patch.object(windows_builder, "fixup_wheels", side_effect=fake_fixup_wheels):
        windows_builder.post_build_fixup()

    entries = captured["lib_paths"].split(";")
    assert "C:/tbb/bin" in entries
    assert "C:/extra/bin" in entries
    assert not any(len(e) == 1 for e in entries)
