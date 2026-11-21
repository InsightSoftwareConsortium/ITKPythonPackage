import argparse
from collections.abc import Sequence

import pytest
from build_wheels import parse_args_with_cmake_defines
from cmake_argument_builder import definitions_from_cmake_options


def _parser(default: Sequence[str] = ()) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--platform-env")
    p.add_argument("--use-ccache", action="store_true")
    p.add_argument("cmake_options", nargs="*", default=list(default))
    return p


def test_defines_between_options_reach_cmake_options() -> None:
    args = parse_args_with_cmake_defines(
        _parser(),
        [
            "--platform-env",
            "linux-py311",
            "-DCMAKE_CXX_FLAGS:STRING=-pipe",
            "--use-ccache",
            "-DBUILD_TESTING:BOOL=OFF",
        ],
    )
    assert args.platform_env == "linux-py311"
    assert args.use_ccache
    assert args.cmake_options == [
        "-DCMAKE_CXX_FLAGS:STRING=-pipe",
        "-DBUILD_TESTING:BOOL=OFF",
    ]


def test_defines_follow_environment_defaults() -> None:
    args = parse_args_with_cmake_defines(
        _parser(["-DA:BOOL=ON"]), ["-DCMAKE_C_FLAGS:STRING=-O2 -g"]
    )
    assert args.cmake_options == ["-DA:BOOL=ON", "-DCMAKE_C_FLAGS:STRING=-O2 -g"]


def test_double_dash_form_still_works() -> None:
    args = parse_args_with_cmake_defines(_parser(), ["--", "-DX:STRING=-pipe"])
    assert args.cmake_options == ["-DX:STRING=-pipe"]


def test_defines_keep_command_line_order_with_spaces() -> None:
    args = parse_args_with_cmake_defines(
        _parser(["-DA:BOOL=ON"]),
        ["-DB:STRING=-O2 -g", "--use-ccache", "-DC:STRING=-pipe"],
    )
    assert args.cmake_options == [
        "-DA:BOOL=ON",
        "-DB:STRING=-O2 -g",
        "-DC:STRING=-pipe",
    ]


def test_unknown_non_define_options_are_rejected() -> None:
    with pytest.raises(SystemExit):
        parse_args_with_cmake_defines(_parser(), ["--no-such-flag", "-DX=1"])


def test_definitions_keep_their_values_verbatim() -> None:
    defs = definitions_from_cmake_options(
        ["-DA:BOOL=ON", "-DCMAKE_C_FLAGS:STRING=-O2 -g", "-DEMPTY:STRING="]
    )
    assert dict(defs.items()) == {
        "A:BOOL": "ON",
        "CMAKE_C_FLAGS:STRING": "-O2 -g",
        "EMPTY:STRING": "",
    }


@pytest.mark.parametrize("option", ["-Wno-dev", "-DNO_VALUE", "-D=ON", "BUILD=ON"])
def test_options_that_are_not_definitions_are_refused(option: str) -> None:
    """They used to be dropped without a word."""
    with pytest.raises(ValueError, match="not a -D<KEY>=<VALUE> definition"):
        definitions_from_cmake_options(["-DA:BOOL=ON", option])
