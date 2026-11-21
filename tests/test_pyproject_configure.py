"""Template substitution and the command line of pyproject_configure."""

import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pyproject_configure
import pytest


def test_a_backslash_in_a_value_is_escaped_exactly_once(tmp_path: Path) -> None:
    template = tmp_path / "pyproject.toml.in"
    template.write_text('first = "@FIRST@"\nsecond = "@SECOND@"\nthird = "@THIRD@"\n')
    output = tmp_path / "pyproject.toml"
    pyproject_configure.configure(
        template, {"FIRST": r"C:\BDR", "SECOND": "x", "THIRD": "y"}, output
    )
    assert tomllib.loads(output.read_text())["first"] == r"C:\BDR"


def test_the_command_line_reads_the_env_file_it_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / "build.env"
    env_file.write_text("ITK_PACKAGE_VERSION=6.0.0\n")
    seen: dict[str, object] = {}

    def fake_configure(
        _script_dir: str | Path,
        config: Mapping[str, Any],
        output_dir: str | Path,
        wheel_name: str,
    ) -> None:
        seen.update(config=config, output_dir=output_dir, wheel_name=wheel_name)

    monkeypatch.setattr(
        pyproject_configure, "configure_one_pyproject_file", fake_configure
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "pyproject_configure.py",
            "--env-file",
            str(env_file),
            "--output-dir",
            str(tmp_path),
            "itk-core",
        ],
    )
    pyproject_configure.main()
    assert seen == {
        "config": {"ITK_PACKAGE_VERSION": "6.0.0"},
        "output_dir": str(tmp_path),
        "wheel_name": "itk-core",
    }
