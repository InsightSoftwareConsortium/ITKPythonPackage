import os
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import wheel_packaging
from build_python_instance_base import BuildPythonInstanceBase
from cmake_argument_builder import CMakeArgumentBuilder
from linux_build_python_instance import LinuxBuildPythonInstance
from macos_build_python_instance import MacOSBuildPythonInstance
from target_platform import OS, Arch, TargetPlatform, host_arch
from windows_build_python_instance import WindowsBuildPythonInstance


def test_pixi_suffix_is_the_documented_build_dir_token_per_platform() -> None:
    """Spell out the ``_{arch}`` token of ``ITK-<env>-<pixi>_<arch>``.

    Literal expectations, so a change to the mapping fails here.
    """
    expected = {
        (OS.LINUX, Arch.X86_64): "x64",
        (OS.LINUX, Arch.AARCH64): "aarch64",
        (OS.DARWIN, Arch.AARCH64): "arm64",
        (OS.WINDOWS, Arch.X86_64): "x64",
    }
    for (os_name, arch), token in expected.items():
        assert TargetPlatform(os_name, arch).pixi_suffix == token


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
    request: pytest.FixtureRequest, builder_fixture: str, expected_suffix: str
) -> None:
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
    linux_builder: LinuxBuildPythonInstance,
    linux_aarch64_builder: LinuxBuildPythonInstance,
) -> None:
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
        builder._configure_tbb()
        env = builder.subprocess_environment()
        assert env["USE_TBB"] == "ON"
        assert env["TBB_DIR"].endswith("TBB")


def test_windows_configure_tbb_sets_tbb_dir_as_str(
    windows_builder: WindowsBuildPythonInstance,
) -> None:
    windows_builder._configure_tbb()
    env = windows_builder.subprocess_environment()
    assert env["USE_TBB"] == "ON"
    assert env["TBB_DIR"].endswith("TBB")


def _make_wheel(path: Path, members: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def test_fixup_wheel_skips_wheel_with_no_binaries(
    tmp_path: Path, macos_builder: MacOSBuildPythonInstance
) -> None:
    """The itk metapackage has no .so/.dylib, so delocate must not run."""
    wheel = _make_wheel(
        tmp_path / "itk-6.0.0-py3-none-any.whl", {"itk/__init__.py": ""}
    )
    # fixup_wheel calls remove_apple_double_files first, which itself
    # calls echo_check_call; patch it out so the assertion below is
    # about delocate and nothing else.
    with (
        patch.object(macos_builder, "remove_apple_double_files"),
        patch.object(macos_builder, "echo_check_call") as called,
    ):
        macos_builder.fixup_wheel(str(wheel))
    flat = " ".join(str(a) for c in called.call_args_list for a in c.args[0])
    assert "delocate-wheel" not in flat


def test_fixup_wheel_runs_delocate_when_binaries_present(
    tmp_path: Path, macos_builder: MacOSBuildPythonInstance
) -> None:
    wheel = _make_wheel(
        tmp_path / "itk_core-6.0.0-cp311-abi3-macosx_11_0_arm64.whl",
        {"itk/_ITKCommonPython.so": "\x7fELF"},
    )
    macos_builder.python_env.bin_path.mkdir(parents=True, exist_ok=True)
    (macos_builder.python_env.bin_path / "delocate-wheel").touch()
    with patch.object(macos_builder, "echo_check_call") as called:
        macos_builder.fixup_wheel(str(wheel))
    assert called.call_count >= 1
    flat = " ".join(str(a) for c in called.call_args_list for a in c.args[0])
    assert "delocate-wheel" in flat
    assert "--require-archs" in flat


def test_macos_gives_the_ipo_check_the_toolchain_archiver(
    tmp_path: Path,
    macos_builder: MacOSBuildPythonInstance,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CMake's own lookup misses conda's prefixed ``ar``; pass it by path."""
    tools = tmp_path / "toolchain"
    tools.mkdir()
    for name in ("arm64-apple-darwin20.0.0-ar", "arm64-apple-darwin20.0.0-ranlib"):
        (tools / name).touch(mode=0o755)
    monkeypatch.setenv("PATH", str(tools))
    monkeypatch.setenv("AR", "arm64-apple-darwin20.0.0-ar")
    monkeypatch.setenv("RANLIB", "arm64-apple-darwin20.0.0-ranlib")
    macos_builder._configure_lto_archiver()
    defs = dict(macos_builder.cmake_compiler_configurations.items())
    for lang in ("C", "CXX"):
        assert defs[f"CMAKE_{lang}_COMPILER_AR:FILEPATH"] == str(
            tools / "arm64-apple-darwin20.0.0-ar"
        )
        assert defs[f"CMAKE_{lang}_COMPILER_RANLIB:FILEPATH"] == str(
            tools / "arm64-apple-darwin20.0.0-ranlib"
        )


def test_macos_leaves_the_archiver_to_cmake_without_a_toolchain_ar(
    macos_builder: MacOSBuildPythonInstance, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AR", raising=False)
    monkeypatch.delenv("RANLIB", raising=False)
    macos_builder._configure_lto_archiver()
    assert not dict(macos_builder.cmake_compiler_configurations.items())


def _make_build_env(tmp_path: Path) -> Path:
    """A minimal ``<prefix>/{bin,lib}`` layout for PYTHON_EXECUTABLE."""
    env_root = tmp_path / "env"
    (env_root / "bin").mkdir(parents=True, exist_ok=True)
    (env_root / "lib").mkdir(parents=True, exist_ok=True)
    (env_root / "bin" / "python").touch()
    return env_root


def _prepare_linux_fixup(
    linux_builder: LinuxBuildPythonInstance,
    tmp_path: Path,
    module_source_dir: Path | None = None,
) -> tuple[Path, Path]:
    linux_builder.config = replace(
        linux_builder.config,
        python_executable=_make_build_env(tmp_path) / "bin" / "python",
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
    tmp_path: Path, linux_builder: LinuxBuildPythonInstance
) -> None:
    """A failed auditwheel repair must not delete the input wheel."""
    wheel, repaired = _prepare_linux_fixup(linux_builder, tmp_path)
    with (
        patch.object(linux_builder, "echo_check_call", return_value=1),
        pytest.raises(RuntimeError),
    ):
        linux_builder.fixup_wheel(str(wheel))
    assert wheel.exists()
    assert not repaired.exists()


def test_fixup_wheel_raises_when_repair_reports_success_but_output_missing(
    tmp_path: Path, linux_builder: LinuxBuildPythonInstance
) -> None:
    """echo_check_call reporting 0 is not enough without the output wheel."""
    wheel, _repaired = _prepare_linux_fixup(linux_builder, tmp_path)
    with (
        patch.object(linux_builder, "echo_check_call", return_value=0),
        pytest.raises(RuntimeError),
    ):
        linux_builder.fixup_wheel(str(wheel))
    assert wheel.exists()


def test_fixup_wheel_removes_original_only_after_verified_repair(
    tmp_path: Path, linux_builder: LinuxBuildPythonInstance
) -> None:
    wheel, repaired = _prepare_linux_fixup(linux_builder, tmp_path)
    _capture_repair_env(linux_builder, wheel, repaired)
    assert not wheel.exists()
    assert repaired.exists()


def _capture_repair_env(
    builder: LinuxBuildPythonInstance, wheel: Path, repaired: Path
) -> dict[str, str]:
    captured_env: dict[str, str] = {}

    def fake_repair(cmd: Sequence[str | Path], env: Mapping[str, str]) -> int:
        captured_env.update(env)
        repaired.touch()
        return 0

    with patch.object(builder, "echo_check_call", side_effect=fake_repair):
        builder.fixup_wheel(str(wheel))
    return captured_env


def test_fixup_wheel_ld_library_path_starts_with_the_build_env_lib_dir(
    tmp_path: Path,
    linux_builder: LinuxBuildPythonInstance,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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


def test_fixup_wheel_ld_library_path_has_no_empty_entries(
    tmp_path: Path, linux_builder: LinuxBuildPythonInstance
) -> None:
    """An empty entry means the working directory to the dynamic loader."""
    wheel, repaired = _prepare_linux_fixup(linux_builder, tmp_path)
    entries = _capture_repair_env(linux_builder, wheel, repaired)[
        "LD_LIBRARY_PATH"
    ].split(":")
    assert "" not in entries


def test_fixup_wheel_fails_loudly_when_the_build_env_lib_dir_is_absent(
    tmp_path: Path, linux_builder: LinuxBuildPythonInstance
) -> None:
    """Silently omitting the env lib dir is what reintroduced defect C."""
    wheel, _repaired = _prepare_linux_fixup(linux_builder, tmp_path)
    linux_builder.config = replace(
        linux_builder.config,
        python_executable=tmp_path / "no-such-env" / "bin" / "python",
    )
    with (
        patch.object(linux_builder, "echo_check_call", return_value=0),
        pytest.raises(RuntimeError, match="library directory"),
    ):
        linux_builder.fixup_wheel(str(wheel))


def test_posix_build_tarball_delegates(macos_builder: MacOSBuildPythonInstance) -> None:
    """The POSIX build_tarball delegates to wheel_packaging.create_posix_tarball."""
    macos_builder.ipp_dir = Path("/ipp")
    with patch.object(wheel_packaging, "create_posix_tarball") as created:
        macos_builder.build_tarball()
    created.assert_called_once()
    kwargs = created.call_args.kwargs
    assert kwargs["build_dir_root"] == macos_builder.build_dir_root
    assert kwargs["arch"] == "arm64"
    assert kwargs["ipp_source_dir"] == Path("/ipp")


def test_prepare_build_env_names_the_build_by_platform_env(
    macos_builder: MacOSBuildPythonInstance,
) -> None:
    """The build directory repeats platform_env, which names the pixi environment."""
    macos_builder.platform_env = "pixi-env"
    with (
        patch.object(macos_builder, "venv_paths"),
        patch.object(macos_builder, "update_venv_itk_build_configurations"),
        patch.object(macos_builder, "_configure_toolchain"),
    ):
        macos_builder.prepare_build_env()
    expected = macos_builder.build_dir_root / "build" / "ITK-pixi-env-pixi-env_arm64"
    assert macos_builder.cmake_itk_source_build_configurations.get(
        "ITK_BINARY_DIR:PATH"
    ) == (expected.as_posix())


def test_configure_toolchain_routes_arch_through_the_target(
    macos_builder: MacOSBuildPythonInstance,
) -> None:
    """macOS reads CMAKE_OSX_ARCHITECTURES from the type, not from ARCH."""
    macos_builder.config = replace(
        macos_builder.config, target=TargetPlatform(OS.LINUX, Arch.X86_64)
    )
    macos_builder._configure_toolchain()
    assert (
        macos_builder.cmake_compiler_configurations.get(
            "CMAKE_OSX_ARCHITECTURES:STRING"
        )
        == "arm64"
    )


def test_configure_toolchain_sets_python_host_platform_from_the_same_values(
    macos_builder: MacOSBuildPythonInstance, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_PYTHON_HOST_PLATFORM must be derived, not a second hardcoded fact.

    The version is a sentinel no production default could equal, so a
    literal (e.g. "macosx-14.0-arm64") cannot coincidentally satisfy this.
    Fails if the version or the architecture is hardcoded, or if the two
    settings are allowed to drift apart.
    """
    monkeypatch.delenv("_PYTHON_HOST_PLATFORM", raising=False)
    monkeypatch.delenv("MACOSX_DEPLOYMENT_TARGET", raising=False)
    macos_builder.config = replace(
        macos_builder.config, macosx_deployment_target="99.5"
    )
    macos_builder._configure_toolchain()
    assert (
        os.environ["_PYTHON_HOST_PLATFORM"]
        == f"macosx-99.5-{macos_builder.target.cmake_osx_arch}"
    )


def test_configure_toolchain_leaves_python_host_platform_unset_without_a_target(
    macos_builder: MacOSBuildPythonInstance, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No macosx_target means no malformed 'macosx--<arch>' value."""
    monkeypatch.delenv("_PYTHON_HOST_PLATFORM", raising=False)
    macos_builder.config = replace(macos_builder.config, macosx_deployment_target=None)
    macos_builder._configure_toolchain()
    assert "_PYTHON_HOST_PLATFORM" not in os.environ


def test_host_arch_is_independent_of_target(monkeypatch: pytest.MonkeyPatch) -> None:
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


def _checking_echo(failing_tool: str) -> Callable[..., int]:
    """A stand-in with build_environment.echo_check_call's semantics.

    It returns a non-zero status for *failing_tool* and raises only when
    the caller forwarded ``check=True``, so a call site that omits the
    flag sees the failure silently, exactly as production would.
    """

    def _echo(
        cmd: Sequence[str | Path], *args: object, check: bool = False, **kwargs: object
    ) -> int:
        rendered = " ".join(str(c) for c in cmd)
        if failing_tool in rendered:
            if check:
                msg = f"command failed: {rendered}"
                raise RuntimeError(msg)
            return 1
        return 0

    return _echo


def _wire_itk_cplusplus(builder: BuildPythonInstanceBase, tmp_path: Path) -> None:
    builder.cleanup = False
    builder.build_node_cpu_count = 2
    builder.build_load_limit = 2
    builder.cmake_cmdline_definitions = CMakeArgumentBuilder()
    builder.cmake_itk_source_build_configurations.set(
        "ITK_BINARY_DIR:PATH", str(tmp_path / "itk-bld")
    )
    builder.config = replace(builder.config, itk_source_dir=tmp_path / "ITK")


@pytest.mark.parametrize("failing_tool", ["cmake", "ninja"])
def test_itk_cplusplus_build_raises_when_a_step_fails(
    tmp_path: Path, linux_builder: LinuxBuildPythonInstance, failing_tool: str
) -> None:
    """A failed configure or ninja must not be recorded as a done step."""
    _wire_itk_cplusplus(linux_builder, tmp_path)
    with (
        patch.object(
            linux_builder, "echo_check_call", side_effect=_checking_echo(failing_tool)
        ),
        pytest.raises(RuntimeError),
    ):
        linux_builder.build_wrapped_itk_cplusplus()


def test_superbuild_support_components_raise_when_cmake_fails(
    tmp_path: Path, linux_builder: LinuxBuildPythonInstance
) -> None:
    """The superbuild configure/build pair must stop the run on failure."""
    linux_builder.cmake_cmdline_definitions = CMakeArgumentBuilder()
    linux_builder.config = replace(
        linux_builder.config, itk_source_dir=tmp_path / "ITK"
    )
    linux_builder.tbb_dir = tmp_path / "tbb"
    linux_builder.ipp_dir = tmp_path / "ipp"
    with (
        patch.object(
            linux_builder, "echo_check_call", side_effect=_checking_echo("cmake")
        ),
        pytest.raises(RuntimeError),
    ):
        linux_builder.build_superbuild_support_components()


def test_superbuild_support_components_raise_when_the_build_fails(
    tmp_path: Path, linux_builder: LinuxBuildPythonInstance
) -> None:
    """The configure can pass and the build still fail (a oneTBB download
    that never completes). That was recorded as a done step and surfaced
    later as a missing TBBConfig.cmake in step 02."""
    linux_builder.cmake_cmdline_definitions = CMakeArgumentBuilder()
    linux_builder.config = replace(
        linux_builder.config, itk_source_dir=tmp_path / "ITK"
    )
    linux_builder.tbb_dir = tmp_path / "tbb"
    linux_builder.ipp_dir = tmp_path / "ipp"
    with (
        patch.object(
            linux_builder, "echo_check_call", side_effect=_checking_echo("--build")
        ),
        pytest.raises(RuntimeError),
    ):
        linux_builder.build_superbuild_support_components()


def _prepare_metawheel(linux_builder: LinuxBuildPythonInstance, tmp_path: Path) -> Path:
    linux_builder.config = replace(
        linux_builder.config,
        python_executable=_make_build_env(tmp_path) / "bin" / "python",
    )
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(exist_ok=True)
    return _make_wheel(
        dist_dir / "itk-6.0.0-cp311-abi3-linux_x86_64.whl",
        {"itk-6.0.0.dist-info/WHEEL": "Tag: cp311-abi3-linux_x86_64"},
    )


def test_metawheel_is_kept_when_repack_produces_nothing(
    tmp_path: Path, linux_builder: LinuxBuildPythonInstance
) -> None:
    """The original meta-wheel must survive a repack that yields no wheel."""
    metawhl = _prepare_metawheel(linux_builder, tmp_path)

    def fake_unpack(
        cmd: Sequence[str | Path], *args: object, check: bool = False, **kwargs: object
    ) -> int:
        rendered = [str(c) for c in cmd]
        if "unpack" in rendered:
            unpacked = tmp_path / "metawheel" / "itk-6.0.0" / "itk.dist-info"
            unpacked.mkdir(parents=True, exist_ok=True)
            (unpacked / "WHEEL").write_text("Tag: cp311-abi3-linux_x86_64\n")
        # "pack" reports success but writes nothing.
        return 0

    with (
        patch.object(linux_builder, "echo_check_call", side_effect=fake_unpack),
        pytest.raises(RuntimeError, match="no wheel"),
    ):
        linux_builder.post_build_fixup()
    assert metawhl.exists()


def test_metawheel_repack_failure_raises_and_keeps_the_original(
    tmp_path: Path, linux_builder: LinuxBuildPythonInstance
) -> None:
    """`wheel pack` returning non-zero must stop the fixup, not be ignored."""
    metawhl = _prepare_metawheel(linux_builder, tmp_path)

    def fake(
        cmd: Sequence[str | Path], *args: object, check: bool = False, **kwargs: object
    ) -> int:
        rendered = [str(c) for c in cmd]
        if "unpack" in rendered:
            unpacked = tmp_path / "metawheel" / "itk-6.0.0" / "itk.dist-info"
            unpacked.mkdir(parents=True, exist_ok=True)
            (unpacked / "WHEEL").write_text("Tag: cp311-abi3-linux_x86_64\n")
            return 0
        if check:
            msg = "wheel pack failed"
            raise RuntimeError(msg)
        return 1

    with (
        patch.object(linux_builder, "echo_check_call", side_effect=fake),
        pytest.raises(RuntimeError),
    ):
        linux_builder.post_build_fixup()
    assert metawhl.exists()


def test_windows_fixup_wheel_raises_when_delvewheel_fails(
    tmp_path: Path, windows_builder: WindowsBuildPythonInstance
) -> None:
    """A failed delvewheel repair must not be reported as a success."""
    dist_dir = windows_builder.build_dir_root / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    wheel = dist_dir / "itk_core-6.0.0-cp311-abi3-win_amd64.whl"
    wheel.touch()
    with (
        patch.object(windows_builder, "echo_check_call", return_value=1),
        pytest.raises(RuntimeError, match="delvewheel"),
    ):
        windows_builder.fixup_wheel(str(wheel), lib_paths="C:/tbb/bin")


def test_windows_lib_paths_are_split_on_semicolons(
    windows_builder: WindowsBuildPythonInstance,
) -> None:
    """--lib-paths arrives as one semicolon-delimited string, not characters."""
    windows_builder.windows_extra_lib_paths = ["C:/tbb/bin;C:/extra/bin;"]
    captured: dict[str, str] = {}

    def fake_fixup_wheels(lib_paths: str) -> None:
        captured["lib_paths"] = lib_paths

    with patch.object(windows_builder, "fixup_wheels", side_effect=fake_fixup_wheels):
        windows_builder.post_build_fixup()

    entries = captured["lib_paths"].split(";")
    assert "C:/tbb/bin" in entries
    assert "C:/extra/bin" in entries
    assert not any(len(e) == 1 for e in entries)


def test_ingested_remote_modules_are_enabled_and_can_be_overridden(
    linux_builder: LinuxBuildPythonInstance,
) -> None:
    from build_python_instance_base import ITK_INGESTED_REMOTE_MODULES

    linux_builder.enable_ingested_remote_modules()
    defs = CMakeArgumentBuilder()
    defs.update(linux_builder.cmake_itk_source_build_configurations.items())
    args = defs.cmake_command_line_arguments()
    for module in ITK_INGESTED_REMOTE_MODULES:
        assert f"-DModule_{module}:BOOL='ON'" in args

    defs.update({"Module_Montage:BOOL": "OFF"})
    args = defs.cmake_command_line_arguments()
    assert "-DModule_Montage:BOOL='OFF'" in args
    assert "-DModule_Montage:BOOL='ON'" not in args


def test_check_wheel_sizes_rejects_a_wheel_over_the_pypi_limit(
    tmp_path: Path, linux_builder: LinuxBuildPythonInstance
) -> None:
    from build_python_instance_base import PYPI_MAX_WHEEL_BYTES

    small = tmp_path / "itk_core-6.0.0-cp311-abi3-manylinux_2_28_x86_64.whl"
    small.write_bytes(b"0")
    linux_builder.check_wheel_sizes(tmp_path)

    big = tmp_path / "itk_filtering-6.0.0-cp311-abi3-manylinux_2_28_x86_64.whl"
    with Path(big).open("wb") as f:
        f.truncate(PYPI_MAX_WHEEL_BYTES + 1)
    with pytest.raises(RuntimeError, match="itk_filtering"):
        linux_builder.check_wheel_sizes(tmp_path)


def test_repair_output_dir_picks_the_module_or_main_dist(
    tmp_path: Path, linux_builder: LinuxBuildPythonInstance
) -> None:
    linux_builder.module_source_dir = tmp_path / "module"
    assert linux_builder._repair_output_dir(False) == tmp_path / "dist"
    assert linux_builder._repair_output_dir(True) == tmp_path / "module" / "dist"


def test_require_repaired_raises_on_status_or_missing_output(
    tmp_path: Path, windows_builder: WindowsBuildPythonInstance
) -> None:
    source = tmp_path / "itk_core-6.0.0-cp311-abi3-win_amd64.whl"
    expected = tmp_path / "dist" / source.name
    with pytest.raises(
        RuntimeError,
        match=r"^delvewheel repair failed for itk_core-6\.0\.0-cp311-abi3-win_amd64"
        r"\.whl \(exit status 0, expected output shown-here\)$",
    ):
        windows_builder._require_repaired(
            "delvewheel", source, 0, expected, "shown-here"
        )
    expected.parent.mkdir()
    expected.touch()
    with pytest.raises(RuntimeError, match="exit status 2"):
        windows_builder._require_repaired("delvewheel", source, 2, expected, "x")
    windows_builder._require_repaired("delvewheel", source, 0, expected, "x")


@pytest.mark.parametrize(
    ("builder_fixture", "use_tbb", "tbb_dir_parts"),
    [
        ("linux_builder", "ON", ("build", "oneTBB-prefix", "lib", "cmake", "TBB")),
        ("windows_builder", "ON", ("build", "oneTBB-prefix", "lib", "cmake", "TBB")),
        ("macos_builder", "OFF", None),
    ],
)
def test_configure_tbb_per_platform(
    request: pytest.FixtureRequest,
    builder_fixture: str,
    use_tbb: str,
    tbb_dir_parts: tuple[str, ...] | None,
) -> None:
    builder = request.getfixturevalue(builder_fixture)
    builder._configure_tbb()
    assert builder._tbb_prefix == builder.build_dir_root / "build" / "oneTBB-prefix"
    env = builder.subprocess_environment()
    assert env["USE_TBB"] == use_tbb
    expected = (
        str(builder.build_dir_root.joinpath(*tbb_dir_parts))
        if tbb_dir_parts
        else "NOT_FOUND"
    )
    assert env["TBB_DIR"] == expected


@pytest.mark.parametrize(
    ("builder_fixture", "expected_tag"),
    [
        ("linux_builder", "cp311-abi3-manylinux_2_28_x86_64"),
        ("linux_aarch64_builder", "cp311-abi3-manylinux_2_28_aarch64"),
    ],
)
def test_metawheel_tag_comes_from_the_target(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    builder_fixture: str,
    expected_tag: str,
) -> None:
    builder = request.getfixturevalue(builder_fixture)
    _prepare_metawheel(builder, tmp_path)
    wheel_file = tmp_path / "metawheel" / "itk-6.0.0" / "itk.dist-info" / "WHEEL"

    def fake(
        cmd: Sequence[str | Path], *args: object, check: bool = False, **kwargs: object
    ) -> int:
        rendered = [str(c) for c in cmd]
        if "unpack" in rendered:
            wheel_file.parent.mkdir(parents=True, exist_ok=True)
            wheel_file.write_text("Wheel-Version: 1.0\nTag: cp311-abi3-linux_x86_64\n")
        else:
            assert wheel_file.read_text().splitlines()[-1] == f"Tag: {expected_tag}"
            dest = Path(rendered[rendered.index("--dest") + 1])
            (dest / f"itk-6.0.0-{expected_tag}.whl").touch()
        return 0

    with patch.object(builder, "echo_check_call", side_effect=fake):
        builder.post_build_fixup()
    assert (tmp_path / "dist" / f"itk-6.0.0-{expected_tag}.whl").exists()


def test_only_a_manylinux_target_is_repaired(
    linux_builder: LinuxBuildPythonInstance,
) -> None:
    assert linux_builder.builds_manylinux()
    linux_builder.target = TargetPlatform(OS.LINUX, Arch.X86_64)
    assert not linux_builder.builds_manylinux()
    with patch.object(linux_builder, "echo_check_call") as called:
        linux_builder.fixup_wheel("itk_core-6.0.0-cp311-abi3-linux_x86_64.whl")
    called.assert_not_called()


@pytest.mark.parametrize(
    ("builder_fixture", "expected"),
    [
        ("windows_builder", ["--config-setting=cmake.args=-GNinja"]),
        ("linux_builder", []),
        ("macos_builder", []),
    ],
)
def test_only_windows_chooses_the_generator(
    request: pytest.FixtureRequest, builder_fixture: str, expected: list[str]
) -> None:
    builder = request.getfixturevalue(builder_fixture)
    assert builder.python_build_generator_args() == expected


def test_python_build_wheel_command_orders_settings_before_the_generator(
    windows_builder: WindowsBuildPythonInstance,
) -> None:
    cmd = windows_builder.python_build_wheel_command(Path("out"), "--config-setting=x")
    assert cmd[:3] == ["python", "-m", "build"]
    assert cmd[cmd.index("--outdir") + 1] == "out"
    assert cmd[-3:] == [
        "--config-setting=cmake.build-type=Release",
        "--config-setting=x",
        "--config-setting=cmake.args=-GNinja",
    ]


def test_module_wheels_are_repaired_into_the_module_dist(
    linux_builder: LinuxBuildPythonInstance, windows_builder: WindowsBuildPythonInstance
) -> None:
    for builder in (linux_builder, windows_builder):
        with patch.object(builder, "fixup_wheel") as fixed:
            builder.fixup_module_wheel("mod.whl")
        fixed.assert_called_once_with("mod.whl", remote_module_wheel=True)


def test_macos_repairs_module_wheels_in_place(
    macos_builder: MacOSBuildPythonInstance,
) -> None:
    with patch.object(macos_builder, "fixup_wheel") as fixed:
        macos_builder.fixup_module_wheel("mod.whl")
    fixed.assert_called_once_with("mod.whl")


def test_only_the_windows_builder_takes_extra_lib_paths() -> None:
    import inspect

    from windows_build_python_instance import WindowsBuildPythonInstance

    base = inspect.signature(BuildPythonInstanceBase.__init__).parameters
    windows = inspect.signature(WindowsBuildPythonInstance.__init__).parameters
    assert "windows_extra_lib_paths" not in base
    assert "windows_extra_lib_paths" in windows


def test_fixup_wheel_fails_when_delocate_is_missing(
    tmp_path: Path, macos_builder: MacOSBuildPythonInstance
) -> None:
    """A wheel with binaries must not ship unrepaired because delocate is absent."""
    wheel = _make_wheel(
        tmp_path / "itk_core-6.0.0-cp311-abi3-macosx_14_0_arm64.whl",
        {"itk/_ITKCommonPython.so": "\x7fELF"},
    )
    with (
        patch.object(macos_builder, "echo_check_call") as called,
        pytest.raises(RuntimeError, match="delocate-wheel not found"),
    ):
        macos_builder.fixup_wheel(str(wheel))
    flat = " ".join(str(a) for c in called.call_args_list for a in c.args[0])
    assert "delocate" not in flat
