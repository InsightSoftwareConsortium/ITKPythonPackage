"""The compiler cache each platform builds through."""

import pytest
from compiler_cache import (
    DEFAULT_MAX_SIZE,
    compiler_cache_definitions,
    compiler_cache_environment,
    compiler_cache_tool,
    use_compiler_cache,
)


@pytest.mark.parametrize(
    ("os_name", "tool"),
    [("windows", "sccache"), ("darwin", "ccache"), ("linux", "ccache")],
)
def test_each_platform_uses_its_cache(os_name, tool):
    assert compiler_cache_tool(os_name) == tool


def test_both_languages_compile_through_the_launcher(tmp_path):
    launcher = tmp_path / "ccache"
    definitions = compiler_cache_definitions("ccache", launcher)
    assert definitions["CMAKE_C_COMPILER_LAUNCHER:FILEPATH"] == str(launcher)
    assert definitions["CMAKE_CXX_COMPILER_LAUNCHER:FILEPATH"] == str(launcher)


@pytest.mark.parametrize(("tool", "wraps"), [("ccache", "ON"), ("sccache", "OFF")])
def test_only_ccache_also_runs_the_wrapping_generators(tmp_path, tool, wraps):
    """ITK puts CastXML and SWIG behind the launcher when ITK_USE_CCACHE is on."""
    definitions = compiler_cache_definitions(tool, tmp_path / tool)
    assert definitions["ITK_USE_CCACHE:BOOL"] == wraps


@pytest.mark.parametrize(
    ("tool", "variable"),
    [("ccache", "CCACHE_MAXSIZE"), ("sccache", "SCCACHE_CACHE_SIZE")],
)
def test_the_cache_is_sized_for_an_itk_build(tool, variable):
    assert compiler_cache_environment(tool, {}) == {variable: DEFAULT_MAX_SIZE}


@pytest.mark.parametrize(
    ("tool", "variable"),
    [("ccache", "CCACHE_MAXSIZE"), ("sccache", "SCCACHE_CACHE_SIZE")],
)
def test_a_size_the_caller_chose_is_kept(tool, variable):
    assert compiler_cache_environment(tool, {variable: "8G"}) == {}


@pytest.mark.parametrize("flag", [True, False])
def test_an_explicit_flag_wins_over_the_environment(flag):
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
def test_without_a_flag_the_environment_decides(env, expected):
    assert use_compiler_cache(None, env) is expected
