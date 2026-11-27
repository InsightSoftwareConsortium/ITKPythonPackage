"""Argument parsing of the Linux module script, which also runs on macOS."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.bash import BASH

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
SCRIPT = SCRIPTS / "dockcross-manylinux-download-cache-and-build-module-wheels.sh"
MAC_SCRIPT = SCRIPTS / "macpython-download-cache-and-build-module-wheels.sh"

pytestmark = pytest.mark.skipif(not BASH, reason="needs bash")


def _run(
    tmp_path: Path,
    *args: str,
    script: Path = SCRIPT,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the script up to its first check, with a ``getopt`` that always fails."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    getopt = fake_bin / "getopt"
    getopt.write_text("#!/bin/sh\nexit 99\n")
    getopt.chmod(0o755)
    env = {
        "PATH": f"{fake_bin}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "MODULE_DEPS_DIR": str(tmp_path / "deps"),
        **(extra_env or {}),
    }
    return subprocess.run(
        [BASH, str(script), *args],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_options_after_the_python_version_are_parsed(tmp_path: Path) -> None:
    """The CI action passes ``cp311 --cmake_options ...``; parsing must not need GNU getopt."""
    result = _run(tmp_path, "cp311", "--cmake_options", "-DBUILD_TESTING=OFF")
    assert "Unexpected option" not in result.stdout
    assert "set ITK_PACKAGE_VERSION" in result.stdout
    assert result.returncode == 1


@pytest.mark.parametrize(
    "args",
    [
        ("-c", "-DA=1", "cp311"),
        ("--cmake_options=-DA=1", "cp311"),
        ("-cmake_options", "-DA=1"),
        ("--exclude_libs", "libfoo.so", "cp311"),
    ],
)
def test_short_long_and_single_dash_forms_are_accepted(
    tmp_path: Path, args: tuple[str, ...]
) -> None:
    result = _run(tmp_path, *args)
    assert "Unexpected option" not in result.stdout
    assert result.returncode == 1


@pytest.mark.parametrize("args", [("--bogus",), ("cp311", "--cmake_options"), ("-h",)])
def test_bad_options_and_help_show_usage(tmp_path: Path, args: tuple[str, ...]) -> None:
    result = _run(tmp_path, *args)
    assert "Usage:" in result.stdout
    assert result.returncode == 2


@pytest.mark.parametrize("script", [SCRIPT, MAC_SCRIPT], ids=["linux", "macos"])
def test_several_unquoted_cmake_options_are_accepted(
    tmp_path: Path, script: Path
) -> None:
    """The CI action passes ``--cmake_options -DA=1 -DB=2`` without quotes."""
    result = _run(tmp_path, "--cmake_options", "-DA=1", "-DB=2", "cp311", script=script)
    assert "Unexpected option" not in result.stdout
    assert result.returncode == 1


def test_a_macos_option_without_its_value_shows_usage(tmp_path: Path) -> None:
    result = _run(tmp_path, "--cmake_options", script=MAC_SCRIPT)
    assert "needs a value" in result.stdout
    assert result.returncode == 2


def test_a_manylinux_version_without_caches_stops_before_downloading(
    tmp_path: Path,
) -> None:
    result = _run(
        tmp_path,
        "cp311",
        extra_env={"ITK_PACKAGE_VERSION": "v6.0b03", "MANYLINUX_VERSION": "2014"},
    )
    assert "manylinux_2_28 only" in result.stdout
    assert "Fetching" not in result.stdout
    assert result.returncode == 1


@pytest.mark.skipif(
    sys.platform == "win32", reason="Git bash does not find the fake curl on PATH"
)
def test_a_failed_download_stops_the_build(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    curl = fake_bin / "curl"
    curl.write_text("#!/bin/sh\nexit 22\n")
    curl.chmod(0o755)
    result = _run(
        tmp_path,
        "cp311",
        extra_env={"ITK_PACKAGE_VERSION": "v6.0b03", "MANYLINUX_VERSION": "_2_28"},
    )
    assert "Fetching" in result.stdout
    assert "Running:" not in result.stdout
    assert result.returncode == 1
