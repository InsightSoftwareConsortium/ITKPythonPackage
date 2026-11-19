import pytest
from dead_strip import (
    LINKER_FLAGS,
    PYTHON_MODULE_EXPORTS,
    SECTION_FLAGS,
    dead_strip_cmake_definitions,
)

VERSION_SCRIPT = f"-Wl,--version-script={PYTHON_MODULE_EXPORTS.as_posix()}"


def test_linux_sets_sections_gold_and_every_target_kind():
    defs = dead_strip_cmake_definitions("linux", {})
    assert defs["CMAKE_C_FLAGS:STRING"] == SECTION_FLAGS
    assert defs["CMAKE_CXX_FLAGS:STRING"] == SECTION_FLAGS
    for kind in ("SHARED", "EXE"):
        assert defs[f"CMAKE_{kind}_LINKER_FLAGS:STRING"] == LINKER_FLAGS
    assert defs["CMAKE_LINK_DEPENDS_USE_LINKER:BOOL"] == "OFF"


def test_python_modules_export_only_pyinit():
    defs = dead_strip_cmake_definitions("linux", {})
    assert (
        defs["CMAKE_MODULE_LINKER_FLAGS:STRING"] == f"{LINKER_FLAGS} {VERSION_SCRIPT}"
    )
    assert VERSION_SCRIPT not in defs["CMAKE_SHARED_LINKER_FLAGS:STRING"]
    text = PYTHON_MODULE_EXPORTS.read_text()
    assert "global: PyInit_*;" in text
    assert "local: *;" in text


def test_icf_is_the_safe_variant():
    """--icf=all segfaulted SimpleITK on the first exception crossing the wrapper."""
    assert "--icf=safe" in LINKER_FLAGS
    assert "--icf=all" not in LINKER_FLAGS


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
