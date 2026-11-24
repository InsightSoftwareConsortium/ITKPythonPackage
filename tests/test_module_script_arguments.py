"""Argument parsing of the Linux module script, which also runs on macOS."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "dockcross-manylinux-download-cache-and-build-module-wheels.sh"
)

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the script up to its first check, with a ``getopt`` that always fails."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    getopt = fake_bin / "getopt"
    getopt.write_text("#!/bin/sh\nexit 99\n")
    getopt.chmod(0o755)
    env = {
        "PATH": f"{fake_bin}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "MODULE_DEPS_DIR": str(tmp_path / "deps"),
    }
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
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
