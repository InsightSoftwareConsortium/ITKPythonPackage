import pytest
from cmake_argument_builder import CMakeArgumentBuilder
from compiler_flags import environment_flag_definitions
from linux_build_python_instance import LinuxBuildPythonInstance


def test_every_flag_variable_follows_the_environment() -> None:
    env = {"CFLAGS": "-O2", "CXXFLAGS": "-O3", "LDFLAGS": "-Wl,-z,now"}
    assert environment_flag_definitions(env, {}) == {
        "CMAKE_C_FLAGS:STRING": "-O2",
        "CMAKE_CXX_FLAGS:STRING": "-O3",
        "CMAKE_SHARED_LINKER_FLAGS:STRING": "-Wl,-z,now",
        "CMAKE_MODULE_LINKER_FLAGS:STRING": "-Wl,-z,now",
        "CMAKE_EXE_LINKER_FLAGS:STRING": "-Wl,-z,now",
    }


def test_an_unset_variable_is_passed_empty_so_a_reused_tree_drops_it() -> None:
    assert environment_flag_definitions({}, {})["CMAKE_C_FLAGS:STRING"] == ""


def test_a_user_definition_wins() -> None:
    user = CMakeArgumentBuilder({"CMAKE_CXX_FLAGS:STRING": "-O1"})
    defs = environment_flag_definitions({"CXXFLAGS": "-O3"}, user)
    assert defs["CMAKE_CXX_FLAGS:STRING"] == "-O1"


def test_posix_builders_pass_the_environment_flags(
    linux_builder: LinuxBuildPythonInstance, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CXXFLAGS", "-march=x86-64-v2")
    defs = linux_builder.compiler_flag_definitions(CMakeArgumentBuilder(), [])
    assert defs["CMAKE_CXX_FLAGS:STRING"] == "-march=x86-64-v2"
