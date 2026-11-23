from pathlib import Path

import pytest
from cmake_argument_builder import CMakeArgumentBuilder
from msvc_path_trim import msvc_trim_definitions, msvc_trim_prefixes
from windows_build_python_instance import WindowsBuildPythonInstance

ROOTS = ["C:\\BDR", "C:\\BDR\\ITK-source", "D:/R312/IPP/"]
TRIMS = "-d1trimfile:C:/BDR/ITK-source/ -d1trimfile:D:/R312/IPP/ -d1trimfile:C:/BDR/"


def test_prefixes_are_windows_absolute_and_longest_first() -> None:
    assert msvc_trim_prefixes(ROOTS) == [
        "C:/BDR/ITK-source/",
        "D:/R312/IPP/",
        "C:/BDR/",
    ]


def test_trims_hold_no_backslash_for_cmake_to_read_as_an_escape() -> None:
    """DCMTK writes CMAKE_CXX_FLAGS unquoted into DCMTKConfig.cmake."""
    for value in msvc_trim_definitions({}, {}, ROOTS).values():
        assert "\\" not in value


def test_a_relative_root_is_made_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (prefix,) = msvc_trim_prefixes(["build"])
    assert prefix.endswith("build/")
    assert prefix != "build/"


def test_a_root_with_a_space_is_skipped() -> None:
    assert msvc_trim_definitions({}, {}, ["C:\\Program Files\\x"]) == {}


def test_trims_extend_cmakes_msvc_defaults() -> None:
    assert msvc_trim_definitions({}, {}, ROOTS) == {
        "CMAKE_C_FLAGS:STRING": f"/DWIN32 /D_WINDOWS {TRIMS}",
        "CMAKE_CXX_FLAGS:STRING": f"/DWIN32 /D_WINDOWS /EHsc {TRIMS}",
    }


def test_environment_flags_come_first_as_cmake_orders_them() -> None:
    defs = msvc_trim_definitions({"CXXFLAGS": "/W3"}, {}, ["C:\\BDR"])
    expected = "/W3 /DWIN32 /D_WINDOWS /EHsc -d1trimfile:C:/BDR/"
    assert defs["CMAKE_CXX_FLAGS:STRING"] == expected


def test_a_user_definition_replaces_the_defaults() -> None:
    user = CMakeArgumentBuilder({"CMAKE_CXX_FLAGS": "/O1"})
    defs = msvc_trim_definitions({}, user, ["C:\\BDR"])
    assert defs["CMAKE_CXX_FLAGS:STRING"] == "/O1 -d1trimfile:C:/BDR/"


def test_a_value_that_already_trims_is_left_alone() -> None:
    defs = msvc_trim_definitions({"CFLAGS": "-d1trimfile:E:\\x\\"}, {}, ["C:\\BDR"])
    assert "CMAKE_C_FLAGS:STRING" not in defs
    assert "CMAKE_CXX_FLAGS:STRING" in defs


def test_the_windows_builder_adds_the_trim(
    tmp_path: Path, windows_builder: WindowsBuildPythonInstance
) -> None:
    defs = windows_builder.compiler_flag_definitions(CMakeArgumentBuilder(), [tmp_path])
    (prefix,) = msvc_trim_prefixes([tmp_path])
    assert defs["CMAKE_CXX_FLAGS:STRING"].endswith(f"-d1trimfile:{prefix}")
