"""Build-environment plumbing shared by every platform builder.

These are the pieces of the build that talk to the surrounding machine
rather than to a particular platform: running a command inside a pixi
environment and resolving interpreter paths in a Unix virtualenv. They are module-level functions so
they can be exercised without constructing a builder.
"""

import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wheel_builder_utils import HOST_SYSTEM_ENVIRONMENT_NAME, run_command


@dataclass(frozen=True)
class PythonEnvironment:
    """The Python installation the wheels are built against.

    Raises
    ------
    FileNotFoundError
        If the include directory or a named library does not exist.
    """

    root_dir: Path
    include_dir: Path
    library: Path | None
    bin_path: Path
    base_dir: Path
    executable: Path | None = None
    sabi_library: Path | None = None

    def __post_init__(self) -> None:
        if not self.include_dir.is_dir():
            msg = f"Python include directory not found: {self.include_dir}"
            raise FileNotFoundError(msg)
        for library in (self.library, self.sabi_library):
            if library is not None and not library.is_file():
                msg = f"Python library not found: {library}"
                raise FileNotFoundError(msg)


def echo_check_call(
    cmd: Sequence[str | Path],
    pixi_env_name: str = "",
    pixi_executable: str | Path | None = None,
    run_dir: Path | None = None,
    use_pixi_env: bool = True,
    env=None,
    **kwargs: Any,
) -> int:
    """Print the command, then run it and return its exit status.

    Parameters
    ----------
    cmd :
        Command to execute.
    pixi_env_name :
        Pixi environment to run inside; empty disables the preamble.
    pixi_executable :
        Path to the pixi executable, required only when a preamble is built.
    run_dir :
        Working directory, also the root of the ``.pixi`` home.
    **kwargs :
        Additional keyword arguments forwarded to the subprocess runner.

    Returns
    -------
    int
        The command's return code. Note that a non-zero status is
        *returned*, not raised, unless ``check=True`` is forwarded.
    """

    pixi_run_preamble: list[str] = []
    pixi_env: dict[str, str] = os.environ.copy()
    if env is not None:
        pixi_env.update(env)
    if run_dir is not None:
        pixi_env.update(
            {
                "PIXI_HOME": str(Path(run_dir) / ".pixi"),
            }
        )

    # A nested pixi run would overflow the cmd.exe line limit on Windows.
    active_env = os.environ.get("PIXI_ENVIRONMENT_NAME")
    already_in_pixi_env = active_env == pixi_env_name
    host_system = active_env == HOST_SYSTEM_ENVIRONMENT_NAME
    if pixi_env_name and use_pixi_env and not (already_in_pixi_env or host_system):
        pixi_run_preamble = [
            str(pixi_executable),
            "run",
            "-e",
            pixi_env_name,
            "--",
        ]

    cmd_strs = pixi_run_preamble + [str(c) for c in cmd]
    display_cmd = " ".join(cmd_strs)
    print(f">>Start Running: cd {run_dir} && {display_cmd}")
    print("^" * 60)
    print(cmd_strs)
    print("^" * 60)
    print(kwargs)
    print("^" * 60)
    process_completion_info: subprocess.CompletedProcess[str] = run_command(
        cmd_strs, env=pixi_env, cwd=run_dir, **kwargs
    )
    cmd_return_status: int = process_completion_info.returncode
    print("^" * 60)
    print(f"<<Finished Running: cmd_return_status={cmd_return_status}")
    print(" ====== stdout =====")
    print(process_completion_info.stdout)
    print(" ====== stderr =====")
    print(process_completion_info.stderr)
    print(" ===================")
    return cmd_return_status


def find_unix_python_paths(venv_dir: Path) -> PythonEnvironment:
    """Resolve Python interpreter and virtualenv paths on Unix.

    Parameters
    ----------
    venv_dir : Path
        Root of the Python virtual environment.

    Raises
    ------
    FileNotFoundError
        If the Python executable does not exist under *venv_dir*.
    RuntimeError
        If the interpreter cannot report its include directory.
    """
    python_executable = venv_dir / "bin" / "python"
    if not python_executable.exists():
        msg = f"Python executable not found: {python_executable}"
        raise FileNotFoundError(msg)

    try:
        python_include_dir = subprocess.check_output(
            [
                str(python_executable),
                "-c",
                "import sysconfig; print(sysconfig.get_paths()['include'])",
            ],
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as e:
        msg = f"Failed to compute Python include dir from {python_executable}: {e}"
        raise RuntimeError(msg) from e
    if not python_include_dir:
        msg = f"{python_executable} reported no Python include dir"
        raise RuntimeError(msg)

    # CMake infers the library from the interpreter, so none is named.
    return PythonEnvironment(
        root_dir=venv_dir,
        include_dir=Path(python_include_dir),
        library=None,
        bin_path=venv_dir / "bin",
        base_dir=venv_dir,
        executable=python_executable,
    )
