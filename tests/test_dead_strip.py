import pytest
from cmake_argument_builder import CMakeArgumentBuilder
from dead_strip import (
    DARWIN_MODULE_FLAGS,
    LINKER_FLAGS,
    PYTHON_MODULE_EXPORTS,
    SECTION_FLAGS,
    dead_strip_cmake_definitions,
    user_flag_key,
)
from target_platform import OS

VERSION_SCRIPT = f"-Wl,--version-script={PYTHON_MODULE_EXPORTS.as_posix()}"


def test_linux_sets_sections_and_gc_for_every_target_kind():
    defs = dead_strip_cmake_definitions(OS.LINUX, {})
    assert defs["CMAKE_C_FLAGS:STRING"] == SECTION_FLAGS
    assert defs["CMAKE_CXX_FLAGS:STRING"] == SECTION_FLAGS
    for kind in ("SHARED", "EXE"):
        assert defs[f"CMAKE_{kind}_LINKER_FLAGS:STRING"] == LINKER_FLAGS


def test_python_modules_export_only_pyinit():
    defs = dead_strip_cmake_definitions(OS.LINUX, {})
    assert (
        defs["CMAKE_MODULE_LINKER_FLAGS:STRING"] == f"{LINKER_FLAGS} {VERSION_SCRIPT}"
    )
    assert VERSION_SCRIPT not in defs["CMAKE_SHARED_LINKER_FLAGS:STRING"]
    text = PYTHON_MODULE_EXPORTS.read_text()
    assert "global: PyInit_*;" in text
    assert "local: *;" in text


def test_default_linker_is_used():
    """gold is deprecated since binutils 2.44 and its --icf saved nothing."""
    flags = " ".join(dead_strip_cmake_definitions(OS.LINUX, {}).values())
    assert "-fuse-ld" not in flags
    assert "--icf" not in flags


def test_windows_is_unchanged():
    assert dead_strip_cmake_definitions(OS.WINDOWS, {"LDFLAGS": "-Wl,-x"}) == {}


def test_darwin_strips_and_limits_exports_of_python_modules_only():
    defs = dead_strip_cmake_definitions(OS.DARWIN, {})
    assert defs == {"CMAKE_MODULE_LINKER_FLAGS:STRING": DARWIN_MODULE_FLAGS}
    assert "-Wl,-dead_strip " in DARWIN_MODULE_FLAGS
    assert "-Wl,-exported_symbol,_PyInit_*" in DARWIN_MODULE_FLAGS


def test_darwin_keeps_environment_and_user_linker_flags():
    env = {"LDFLAGS": "-Wl,-dead_strip_dylibs"}
    defs = dead_strip_cmake_definitions(OS.DARWIN, env)
    assert defs["CMAKE_MODULE_LINKER_FLAGS:STRING"] == (
        f"-Wl,-dead_strip_dylibs {DARWIN_MODULE_FLAGS}"
    )
    user = {"CMAKE_MODULE_LINKER_FLAGS": "-Wl,-headerpad_max_install_names"}
    defs = dead_strip_cmake_definitions(OS.DARWIN, env, user)
    assert defs["CMAKE_MODULE_LINKER_FLAGS:STRING"] == (
        f"-Wl,-headerpad_max_install_names {DARWIN_MODULE_FLAGS}"
    )


def test_environment_flags_are_kept():
    defs = dead_strip_cmake_definitions(
        OS.LINUX, {"CFLAGS": "-O2", "CXXFLAGS": "-g0", "LDFLAGS": "-Wl,-z,now"}
    )
    assert defs["CMAKE_C_FLAGS:STRING"] == f"-O2 {SECTION_FLAGS}"
    assert defs["CMAKE_CXX_FLAGS:STRING"] == f"-g0 {SECTION_FLAGS}"
    assert defs["CMAKE_SHARED_LINKER_FLAGS:STRING"] == f"-Wl,-z,now {LINKER_FLAGS}"


@pytest.mark.parametrize("key", ["CMAKE_CXX_FLAGS:STRING", "CMAKE_CXX_FLAGS"])
def test_user_flags_replace_environment_and_are_merged(key):
    user = {key: "-march=native"}
    defs = dead_strip_cmake_definitions(OS.LINUX, {"CXXFLAGS": "-g0"}, user)
    assert defs["CMAKE_CXX_FLAGS:STRING"] == f"-march=native {SECTION_FLAGS}"
    assert user_flag_key(user, "CMAKE_CXX_FLAGS") == key


def test_user_module_linker_flags_keep_the_version_script():
    user = CMakeArgumentBuilder({"CMAKE_MODULE_LINKER_FLAGS:STRING": "-Wl,-z,now"})
    defs = dead_strip_cmake_definitions(OS.LINUX, {}, user)
    assert defs["CMAKE_MODULE_LINKER_FLAGS:STRING"].startswith("-Wl,-z,now ")
    assert VERSION_SCRIPT in defs["CMAKE_MODULE_LINKER_FLAGS:STRING"]


def test_user_flag_key_absent():
    assert user_flag_key({}, "CMAKE_C_FLAGS") is None
