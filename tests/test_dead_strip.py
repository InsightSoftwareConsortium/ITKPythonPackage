import pytest
from dead_strip import (
    LINKER_FLAGS,
    PYTHON_MODULE_EXPORTS,
    SECTION_FLAGS,
    dead_strip_cmake_definitions,
)

VERSION_SCRIPT = f"-Wl,--version-script={PYTHON_MODULE_EXPORTS.as_posix()}"


def test_linux_sets_sections_and_gc_for_every_target_kind():
    defs = dead_strip_cmake_definitions("linux", {})
    assert defs["CMAKE_C_FLAGS:STRING"] == SECTION_FLAGS
    assert defs["CMAKE_CXX_FLAGS:STRING"] == SECTION_FLAGS
    for kind in ("SHARED", "EXE"):
        assert defs[f"CMAKE_{kind}_LINKER_FLAGS:STRING"] == LINKER_FLAGS


def test_python_modules_export_only_pyinit():
    defs = dead_strip_cmake_definitions("linux", {})
    assert (
        defs["CMAKE_MODULE_LINKER_FLAGS:STRING"] == f"{LINKER_FLAGS} {VERSION_SCRIPT}"
    )
    assert VERSION_SCRIPT not in defs["CMAKE_SHARED_LINKER_FLAGS:STRING"]
    text = PYTHON_MODULE_EXPORTS.read_text()
    assert "global: PyInit_*;" in text
    assert "local: *;" in text


def test_default_linker_is_used():
    """gold is deprecated since binutils 2.44 and its --icf saved nothing."""
    flags = " ".join(dead_strip_cmake_definitions("linux", {}).values())
    assert "-fuse-ld" not in flags
    assert "--icf" not in flags


@pytest.mark.parametrize("os_name", ["darwin", "windows"])
def test_other_platforms_are_unchanged(os_name):
    assert dead_strip_cmake_definitions(os_name, {"LDFLAGS": "-Wl,-x"}) == {}


def test_environment_flags_are_kept():
    defs = dead_strip_cmake_definitions(
        "linux", {"CFLAGS": "-O2", "CXXFLAGS": "-g0", "LDFLAGS": "-Wl,-z,now"}
    )
    assert defs["CMAKE_C_FLAGS:STRING"] == f"-O2 {SECTION_FLAGS}"
    assert defs["CMAKE_CXX_FLAGS:STRING"] == f"-g0 {SECTION_FLAGS}"
    assert defs["CMAKE_SHARED_LINKER_FLAGS:STRING"] == f"-Wl,-z,now {LINKER_FLAGS}"
