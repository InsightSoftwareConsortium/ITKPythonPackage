"""Template substitution and the command line of pyproject_configure."""

import sys
import tomllib

import pyproject_configure


def test_a_backslash_in_a_value_is_escaped_exactly_once(tmp_path):
    template = tmp_path / "pyproject.toml.in"
    template.write_text('first = "@FIRST@"\nsecond = "@SECOND@"\nthird = "@THIRD@"\n')
    output = tmp_path / "pyproject.toml"
    pyproject_configure.configure(
        template, {"FIRST": r"C:\BDR", "SECOND": "x", "THIRD": "y"}, output
    )
    assert tomllib.loads(output.read_text())["first"] == r"C:\BDR"


def test_the_command_line_reads_the_env_file_it_is_given(tmp_path, monkeypatch):
    env_file = tmp_path / "build.env"
    env_file.write_text("ITK_PACKAGE_VERSION=6.0.0\n")
    seen = {}

    def fake_configure(_script_dir, config, output_dir, wheel_name):
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
