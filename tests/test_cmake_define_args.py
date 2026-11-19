import argparse

import pytest
from build_wheels import parse_args_with_cmake_defines


def _parser(default=()):
    p = argparse.ArgumentParser()
    p.add_argument("--platform-env")
    p.add_argument("--use-ccache", action="store_true")
    p.add_argument("cmake_options", nargs="*", default=list(default))
    return p


def test_defines_between_options_reach_cmake_options():
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


def test_defines_follow_environment_defaults():
    args = parse_args_with_cmake_defines(
        _parser(["-DA:BOOL=ON"]), ["-DCMAKE_C_FLAGS:STRING=-O2 -g"]
    )
    assert args.cmake_options == ["-DA:BOOL=ON", "-DCMAKE_C_FLAGS:STRING=-O2 -g"]


def test_double_dash_form_still_works():
    args = parse_args_with_cmake_defines(_parser(), ["--", "-DX:STRING=-pipe"])
    assert args.cmake_options == ["-DX:STRING=-pipe"]


def test_defines_keep_command_line_order_with_spaces():
    args = parse_args_with_cmake_defines(
        _parser(["-DA:BOOL=ON"]),
        ["-DB:STRING=-O2 -g", "--use-ccache", "-DC:STRING=-pipe"],
    )
    assert args.cmake_options == [
        "-DA:BOOL=ON",
        "-DB:STRING=-O2 -g",
        "-DC:STRING=-pipe",
    ]


def test_unknown_non_define_options_are_rejected():
    with pytest.raises(SystemExit):
        parse_args_with_cmake_defines(_parser(), ["--no-such-flag", "-DX=1"])
