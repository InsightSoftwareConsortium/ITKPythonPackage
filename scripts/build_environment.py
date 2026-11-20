"""Build-environment plumbing shared by every platform builder.

These are the pieces of the build that talk to the surrounding machine
rather than to a particular platform: running a command inside a pixi
environment, resolving interpreter paths in a Unix virtualenv, and
naming the pixi environment itself. They are module-level functions so
they can be exercised without constructing a builder.
"""

import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from wheel_builder_utils import run_commandLine_subprocess


def get_pixi_environment_name(platform_env: str) -> str:
    """Return the pixi environment name for a platform environment.

    The pixi environment name is the same as the platform_env and is
    related to the environment setups defined in pixi.toml in the root
    of this git directory that contains these scripts.
    """
    return platform_env


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

    # When this process is already running inside the requested environment,
    # a further ``pixi run`` re-prepends that environment's directories to an
    # already-activated PATH. On Windows each activation adds ~2.4 kB, and the
    # second one overflows the cmd.exe 8191-character line limit, failing with
    # "The input line is too long." Running in-process is equivalent here.
    already_in_pixi_env = os.environ.get("PIXI_ENVIRONMENT_NAME") == pixi_env_name
    if pixi_env_name and use_pixi_env and not already_in_pixi_env:
        pixi_run_preamble = [
            str(pixi_executable),
            "run",
            "-e",
            pixi_env_name,
            "--",
        ]

    # convert all items to strings (i.e. Path() to str)
    cmd_strs = pixi_run_preamble + [str(c) for c in cmd]
    # Prepare a friendly command-line string for display
    try:
        display_cmd = " ".join(cmd_strs)
    except Exception as e:
        display_cmd = f"{cmd_strs!s}\nERROR: {e}"
        sys.exit(1)
    print(f">>Start Running: cd {run_dir} && {display_cmd}")
    print("^" * 60)
    print(cmd_strs)
    print("^" * 60)
    print(kwargs)
    print("^" * 60)
    process_completion_info: subprocess.CompletedProcess[str] = (
        run_commandLine_subprocess(cmd_strs, env=pixi_env, cwd=run_dir, **kwargs)
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


def find_unix_exectable_paths(
    venv_dir: Path,
) -> tuple[str, str, str, str, str]:
    """Resolve Python interpreter and virtualenv paths on Unix.

    Parameters
    ----------
    venv_dir : Path
        Root of the Python virtual environment.

    Returns
    -------
    tuple[str, str, str, str, str]
        ``(python_executable, python_include_dir, python_library,
        venv_bin_path, venv_base_dir)``.

    Raises
    ------
    FileNotFoundError
        If the Python executable does not exist under *venv_dir*.
    """
    python_executable = venv_dir / "bin" / "python"
    if not python_executable.exists():
        msg = f"Python executable not found: {python_executable}"
        raise FileNotFoundError(msg)

    # Compute Python include dir using sysconfig for the given interpreter
    try:
        python_include_dir = (
            subprocess.check_output(
                [
                    str(python_executable),
                    "-c",
                    "import sysconfig; print(sysconfig.get_paths()['include'])",
                ],
                text=True,
            ).strip()
            or ""
        )
    except Exception as e:
        print(f"Failed to compute Python include dir: {e}\n defaulting to empty")
        python_include_dir = ""

    # modern CMake with Python3 can infer the library from executable; leave empty
    python_library = ""

    # Update PATH
    venv_bin_path = venv_dir / "bin"
    return (
        str(python_executable),
        str(python_include_dir),
        str(python_library),
        str(venv_bin_path),
        str(venv_dir),
    )
