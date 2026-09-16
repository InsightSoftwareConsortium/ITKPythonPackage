import shutil
import sys

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
    """``check=True`` reaches run_commandLine_subprocess, which raises."""
    with pytest.raises(RuntimeError):
        build_environment.echo_check_call(
            [sys.executable, "-c", "import sys; sys.exit(3)"],
            use_pixi_env=False,
            check=True,
        )


def test_get_pixi_environment_name_is_the_platform_env():
    assert build_environment.get_pixi_environment_name("macosx-py311") == "macosx-py311"


def test_find_unix_exectable_paths_raises_when_interpreter_absent(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_environment.find_unix_exectable_paths(tmp_path)


def test_find_unix_exectable_paths_resolves_a_venv_layout(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # A real venv symlinks its interpreter, but creating a symlink needs
    # SeCreateSymbolicLinkPrivilege off a POSIX box (Developer Mode or an
    # elevated shell), so an unprivileged run raises WinError 1314. Copy the
    # interpreter instead: find_unix_exectable_paths() runs it to read
    # sysconfig, so the stand-in has to be executable, and a copied
    # interpreter still is even without the .exe suffix.
    try:
        (bin_dir / "python").symlink_to(sys.executable)
    except (OSError, NotImplementedError):
        shutil.copy2(sys.executable, bin_dir / "python")

    exe, include_dir, library, venv_bin, venv_base = (
        build_environment.find_unix_exectable_paths(tmp_path)
    )

    assert exe == str(bin_dir / "python")
    assert venv_bin == str(bin_dir)
    assert venv_base == str(tmp_path)
    # CMake infers the library from the interpreter, so it stays empty.
    assert library == ""
    assert include_dir
