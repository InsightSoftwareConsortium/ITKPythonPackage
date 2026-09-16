"""Build tools must resolve inside the target pixi environment."""

import subprocess
from pathlib import Path

import pytest
from wheel_builder_utils import (
    abort_if_wrong_pixi_environment,
    which_required_in_pixi_env,
)


def test_resolves_inside_target_env_not_launching_path(monkeypatch):
    monkeypatch.setenv("PIXI_ENVIRONMENT_NAME", "default")
    seen = {}

    def fake_run(cmd, cwd=None, env=None, check=False):
        seen["cmd"] = [str(part) for part in cmd]
        return subprocess.CompletedProcess(
            cmd, 0, "/envs/windows-py311/bin/doxygen\n", ""
        )

    monkeypatch.setattr("wheel_builder_utils.run_commandLine_subprocess", fake_run)
    monkeypatch.setattr("wheel_builder_utils.shutil.which", lambda _: "/stray/doxygen")

    resolved = which_required_in_pixi_env("doxygen", Path("/bin/pixi"), "windows-py311")

    assert resolved == Path("/envs/windows-py311/bin/doxygen")
    assert seen["cmd"][:4] == [str(Path("/bin/pixi")), "run", "-e", "windows-py311"]


def test_uses_current_env_when_already_inside_it(monkeypatch):
    monkeypatch.setenv("PIXI_ENVIRONMENT_NAME", "windows-py311")
    monkeypatch.setattr(
        "wheel_builder_utils._which", lambda _: Path("/envs/windows-py311/bin/cmake")
    )

    def explode(*_args, **_kwargs):  # nesting pixi run would overflow cmd.exe
        raise AssertionError("must not nest a second pixi run")

    monkeypatch.setattr("wheel_builder_utils.run_commandLine_subprocess", explode)

    assert which_required_in_pixi_env(
        "cmake", Path("/bin/pixi"), "windows-py311"
    ) == Path("/envs/windows-py311/bin/cmake")


def test_missing_tool_in_target_env_raises(monkeypatch):
    monkeypatch.setenv("PIXI_ENVIRONMENT_NAME", "default")
    monkeypatch.setattr(
        "wheel_builder_utils.run_commandLine_subprocess",
        lambda *a, **k: subprocess.CompletedProcess(a[0] if a else [], 0, "\n", ""),
    )
    monkeypatch.setattr("wheel_builder_utils.shutil.which", lambda _: "/stray/doxygen")

    with pytest.raises(RuntimeError, match="doxygen"):
        which_required_in_pixi_env("doxygen", Path("/bin/pixi"), "windows-py311")


def test_wrong_environment_aborts_with_the_env_name(monkeypatch, capsys):
    monkeypatch.setenv("PIXI_ENVIRONMENT_NAME", "default")
    with pytest.raises(SystemExit) as excinfo:
        abort_if_wrong_pixi_environment("windows-py311")
    message = str(excinfo.value)
    assert "windows-py311" in message
    assert "default" in message
    assert "pixi run -e windows-py311" in message


def test_no_pixi_environment_also_aborts(monkeypatch):
    monkeypatch.delenv("PIXI_ENVIRONMENT_NAME", raising=False)
    with pytest.raises(SystemExit):
        abort_if_wrong_pixi_environment("linux-py311")


def test_correct_environment_is_silent(monkeypatch):
    monkeypatch.setenv("PIXI_ENVIRONMENT_NAME", "linux-py311")
    assert abort_if_wrong_pixi_environment("linux-py311") is None


def test_hostsystem_opts_out_of_the_environment_guard(monkeypatch):
    monkeypatch.setenv("PIXI_ENVIRONMENT_NAME", "hostsystem")
    assert abort_if_wrong_pixi_environment("macosx-py311") is None


def test_hostsystem_resolves_tools_from_host_path(monkeypatch):
    monkeypatch.setenv("PIXI_ENVIRONMENT_NAME", "hostsystem")
    monkeypatch.setattr(
        "wheel_builder_utils._which", lambda _: Path("/usr/local/bin/doxygen")
    )

    def explode(*_args, **_kwargs):
        raise AssertionError("hostsystem must not probe a pixi environment")

    monkeypatch.setattr("wheel_builder_utils.run_commandLine_subprocess", explode)

    assert which_required_in_pixi_env(
        "doxygen", Path("/bin/pixi"), "macosx-py311"
    ) == Path("/usr/local/bin/doxygen")


def test_wrong_environment_message_mentions_hostsystem(monkeypatch):
    monkeypatch.setenv("PIXI_ENVIRONMENT_NAME", "default")
    with pytest.raises(SystemExit) as excinfo:
        abort_if_wrong_pixi_environment("macosx-py311")
    assert "hostsystem" in str(excinfo.value)
