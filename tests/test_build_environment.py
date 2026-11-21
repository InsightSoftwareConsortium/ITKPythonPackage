import shutil
import subprocess
import sys
from pathlib import Path

import build_environment
import pytest


def test_echo_check_call_returns_zero_on_success():
    rc = build_environment.echo_check_call(
        [sys.executable, "-c", "pass"], use_pixi_env=False
    )
    assert rc == 0


def test_echo_check_call_returns_nonzero_rather_than_raising():
    """It returns the exit status; it does not raise on its own.

    Callers that must stop the build therefore have to forward
    ``check=True`` or inspect the returned status themselves.
    """
    rc = build_environment.echo_check_call(
        [sys.executable, "-c", "import sys; sys.exit(3)"], use_pixi_env=False
    )
    assert rc == 3


def test_echo_check_call_raises_when_check_is_forwarded():
    """``check=True`` reaches run_command, which raises."""
    with pytest.raises(RuntimeError):
        build_environment.echo_check_call(
            [sys.executable, "-c", "import sys; sys.exit(3)"],
            use_pixi_env=False,
            check=True,
        )


@pytest.mark.parametrize(
    ("active", "wrapped"),
    [("hostsystem", False), ("macosx-py311", False), ("default", True)],
)
def test_pixi_run_preamble_only_outside_the_target_and_hostsystem(
    monkeypatch, active, wrapped
):
    """hostsystem runs tools from PATH, as AGENTS.md documents."""
    monkeypatch.setenv("PIXI_ENVIRONMENT_NAME", active)
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(build_environment, "run_command", fake_run)
    build_environment.echo_check_call(
        ["cmake", "--version"], pixi_env_name="macosx-py311", pixi_executable="pixi"
    )
    assert (seen["cmd"][:2] == ["pixi", "run"]) is wrapped
    assert seen["cmd"][-2:] == ["cmake", "--version"]


def test_find_unix_python_paths_raises_when_interpreter_absent(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_environment.find_unix_python_paths(tmp_path)


def test_find_unix_python_paths_resolves_a_venv_layout(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # A real venv symlinks its interpreter, but creating a symlink needs
    # SeCreateSymbolicLinkPrivilege off a POSIX box (Developer Mode or an
    # elevated shell), so an unprivileged run raises WinError 1314. Copy the
    # interpreter instead: find_unix_python_paths() runs it to read
    # sysconfig, so the stand-in has to be executable, and a copied
    # interpreter still is even without the .exe suffix.
    try:
        (bin_dir / "python").symlink_to(sys.executable)
    except (OSError, NotImplementedError):
        shutil.copy2(sys.executable, bin_dir / "python")

    env = build_environment.find_unix_python_paths(tmp_path)

    assert env.executable == bin_dir / "python"
    assert env.bin_path == bin_dir
    assert env.base_dir == tmp_path
    assert env.root_dir == tmp_path
    # CMake infers the library from the interpreter, so none is named.
    assert env.library is None
    assert env.sabi_library is None
    assert env.include_dir.is_dir()


def _environment(
    tmp_path: Path, **overrides: Path | None
) -> build_environment.PythonEnvironment:
    (tmp_path / "include").mkdir(exist_ok=True)
    fields: dict[str, Path | None] = {
        "root_dir": tmp_path,
        "include_dir": tmp_path / "include",
        "library": None,
        "bin_path": tmp_path / "bin",
        "base_dir": tmp_path,
    }
    fields.update(overrides)
    return build_environment.PythonEnvironment(**fields)  # type: ignore[arg-type]


def test_python_environment_accepts_existing_paths(tmp_path):
    library = tmp_path / "python311.lib"
    sabi = tmp_path / "python3.lib"
    library.touch()
    sabi.touch()
    env = _environment(tmp_path, library=library, sabi_library=sabi)
    assert env.library == library
    assert env.sabi_library == sabi


def test_python_environment_requires_the_include_dir(tmp_path):
    with pytest.raises(FileNotFoundError, match="include directory"):
        _environment(tmp_path, include_dir=tmp_path / "missing")


@pytest.mark.parametrize("field", ["library", "sabi_library"])
def test_python_environment_requires_named_libraries(tmp_path, field):
    with pytest.raises(FileNotFoundError, match="library not found"):
        _environment(tmp_path, **{field: tmp_path / "python3.lib"})


def test_python_environment_is_frozen(tmp_path):
    env = _environment(tmp_path)
    with pytest.raises(AttributeError):
        env.root_dir = tmp_path / "other"  # type: ignore[misc]
