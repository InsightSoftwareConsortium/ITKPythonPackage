"""The compiler cache each platform builds through."""

import os
from pathlib import Path

import pytest
from compiler_cache import (
    DEFAULT_MAX_SIZE,
    ccache_size_bytes,
    compiler_cache_base_dirs,
    compiler_cache_definitions,
    compiler_cache_environment,
    compiler_cache_max_size,
    compiler_cache_session,
    compiler_cache_size_setting,
    compiler_cache_tool,
    use_compiler_cache,
)
from target_platform import OS


@pytest.mark.parametrize(
    ("os_name", "tool"),
    [(OS.WINDOWS, "sccache"), (OS.DARWIN, "ccache"), (OS.LINUX, "ccache")],
)
def test_each_platform_uses_its_cache(os_name: OS, tool: str) -> None:
    assert compiler_cache_tool(os_name) == tool


def test_both_languages_compile_through_the_launcher(tmp_path: Path) -> None:
    launcher = tmp_path / "ccache"
    definitions = compiler_cache_definitions("ccache", launcher)
    assert definitions["CMAKE_C_COMPILER_LAUNCHER:FILEPATH"] == str(launcher)
    assert definitions["CMAKE_CXX_COMPILER_LAUNCHER:FILEPATH"] == str(launcher)


@pytest.mark.parametrize(("tool", "wraps"), [("ccache", "ON"), ("sccache", "OFF")])
def test_only_ccache_also_runs_the_wrapping_generators(
    tmp_path: Path, tool: str, wraps: str
) -> None:
    """ITK puts CastXML and SWIG behind the launcher when ITK_USE_CCACHE is on."""
    definitions = compiler_cache_definitions(tool, tmp_path / tool)
    assert definitions["ITK_USE_CCACHE:BOOL"] == wraps


@pytest.mark.parametrize(
    ("tool", "variable"),
    [("ccache", "CCACHE_MAXSIZE"), ("sccache", "SCCACHE_CACHE_SIZE")],
)
def test_the_cache_is_sized_for_an_itk_build(tool: str, variable: str) -> None:
    assert compiler_cache_environment(tool, {})[variable] == DEFAULT_MAX_SIZE


@pytest.mark.parametrize(
    ("tool", "variable"),
    [("ccache", "CCACHE_MAXSIZE"), ("sccache", "SCCACHE_CACHE_SIZE")],
)
def test_a_size_the_caller_chose_is_kept(tool: str, variable: str) -> None:
    assert variable not in compiler_cache_environment(tool, {variable: "8G"})


def test_the_sccache_server_never_idles_out_during_a_build() -> None:
    """A server restarted after an idle stretch reports only its own compiles."""
    assert compiler_cache_environment("sccache", {})["SCCACHE_IDLE_TIMEOUT"] == "0"


def test_an_idle_timeout_the_caller_chose_is_kept() -> None:
    env = {"SCCACHE_IDLE_TIMEOUT": "3600"}
    assert "SCCACHE_IDLE_TIMEOUT" not in compiler_cache_environment("sccache", env)


def test_ccache_hashes_paths_below_the_common_parent(tmp_path: Path) -> None:
    """A cache filled from one checkout and build root hits from another."""
    roots = [tmp_path / "ITKPythonPackage", tmp_path / "ITKPythonPackage-build"]
    env = compiler_cache_environment("ccache", {}, roots)
    assert env["CCACHE_BASEDIR"] == str(tmp_path)


def test_sccache_lists_every_root_longest_first(tmp_path: Path) -> None:
    roots = [tmp_path, tmp_path / "IPP", tmp_path / "BDR-build", tmp_path / "IPP"]
    env = compiler_cache_environment("sccache", {}, roots)
    assert env["SCCACHE_BASEDIRS"] == os.pathsep.join(
        [str(tmp_path / "BDR-build"), str(tmp_path / "IPP"), str(tmp_path)]
    )


@pytest.mark.parametrize("tool", ["ccache", "sccache"])
def test_a_base_dir_the_caller_chose_is_kept(tool: str, tmp_path: Path) -> None:
    env = {"CCACHE_BASEDIR": "/x", "SCCACHE_BASEDIRS": "/x"}
    added = compiler_cache_environment(tool, env, [tmp_path])
    assert not {"CCACHE_BASEDIR", "SCCACHE_BASEDIRS"} & added.keys()


def test_no_base_dir_without_roots() -> None:
    assert compiler_cache_base_dirs("ccache", []) is None
    assert compiler_cache_base_dirs("sccache", []) is None


def test_ccache_never_takes_a_filesystem_root_as_base_dir(tmp_path: Path) -> None:
    """Every absolute path would be rewritten, toolchain headers included."""
    anchor = Path(tmp_path.anchor)
    assert compiler_cache_base_dirs("ccache", [anchor / "a", anchor / "b"]) is None


def test_ccache_gets_no_sccache_settings() -> None:
    assert compiler_cache_environment("ccache", {}) == {
        "CCACHE_MAXSIZE": DEFAULT_MAX_SIZE
    }


@pytest.mark.parametrize("flag", [True, False])
def test_an_explicit_flag_wins_over_the_environment(flag: bool) -> None:
    assert use_compiler_cache(flag, {"USE_CCACHE": "0" if flag else "1"}) is flag


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, False),
        ({"USE_CCACHE": "1"}, True),
        ({"USE_CCACHE": "on"}, True),
        ({"USE_COMPILER_CACHE": "YES"}, True),
        ({"USE_COMPILER_CACHE": "0", "USE_CCACHE": "1"}, False),
    ],
)
def test_without_a_flag_the_environment_decides(
    env: dict[str, str], expected: bool
) -> None:
    assert use_compiler_cache(None, env) is expected


def test_ccache_reports_on_this_build_alone(tmp_path: Path) -> None:
    before, after = compiler_cache_session("ccache", tmp_path / "ccache", "30G")
    assert before[-1] == [str(tmp_path / "ccache"), "--zero-stats"]
    assert after == [[str(tmp_path / "ccache"), "--show-stats", "--verbose"]]


def test_the_sccache_server_is_restarted_and_stopped(tmp_path: Path) -> None:
    exe = str(tmp_path / "sccache")
    before, after = compiler_cache_session("sccache", exe, "30G")
    assert before[:2] == [[exe, "--stop-server"], [exe, "--start-server"]]
    assert [exe, "--zero-stats"] in before
    assert after[-1] == [exe, "--stop-server"]


def test_ccache_saves_its_size_limit_before_the_build(tmp_path: Path) -> None:
    exe = str(tmp_path / "ccache")
    before, _ = compiler_cache_session("ccache", exe, "42G")
    assert before.index([exe, "--max-size", "42G"]) < before.index(
        [exe, "--zero-stats"]
    )


@pytest.mark.parametrize(
    ("tool", "variable"),
    [("ccache", "CCACHE_MAXSIZE"), ("sccache", "SCCACHE_CACHE_SIZE")],
)
def test_the_effective_size_prefers_the_callers(tool: str, variable: str) -> None:
    assert compiler_cache_max_size(tool, {variable: "8G"}) == "8G"
    assert compiler_cache_max_size(tool, {}) == DEFAULT_MAX_SIZE


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ("30G", 30e9),
        ("75.0 GB", 75e9),
        ("5.0 GiB", 5 * 1024**3),
        ("30", 30 * 1024**3),
        ("512 MB", 512e6),
        ("lots", None),
    ],
)
def test_ccache_sizes_are_read_in_bytes(size: str, expected: float | None) -> None:
    assert ccache_size_bytes(size) == expected


def _fake_ccache(tmp_path: Path, printed: str) -> Path:
    exe = tmp_path / "ccache"
    exe.write_text(f"#!/bin/sh\necho '{printed}'\n")
    exe.chmod(0o755)
    return exe


posix_only = pytest.mark.skipif(
    not Path("/bin/sh").exists(), reason="the fake ccache is a shell script"
)


@posix_only
def test_a_larger_configured_ccache_limit_is_kept(tmp_path: Path) -> None:
    exe = _fake_ccache(tmp_path, "75.0 GB")
    assert compiler_cache_size_setting("ccache", exe, {}) == {
        "CCACHE_MAXSIZE": "75.0 GB"
    }


@posix_only
def test_a_smaller_configured_limit_gives_way_to_the_default(tmp_path: Path) -> None:
    exe = _fake_ccache(tmp_path, "5.0 GiB")
    assert compiler_cache_size_setting("ccache", exe, {}) == {}


def test_a_size_the_caller_chose_is_not_queried(tmp_path: Path) -> None:
    env = {"CCACHE_MAXSIZE": "8G"}
    assert compiler_cache_size_setting("ccache", tmp_path / "absent", env) == {}


def test_sccache_has_no_configured_limit_to_keep(tmp_path: Path) -> None:
    assert compiler_cache_size_setting("sccache", tmp_path / "absent", {}) == {}
