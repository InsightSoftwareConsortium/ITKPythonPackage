"""The bash that runs the shell script tests."""

import os
import shutil
from pathlib import Path


def find_bash() -> str:
    """Return the path of bash, or an empty string when there is none.

    On Windows, System32\\bash.exe starts WSL, which fails without an
    installed distribution, and process creation finds it before PATH;
    use the bash that comes with Git for Windows instead.
    """
    if os.name != "nt":
        return shutil.which("bash") or ""
    git = shutil.which("git")
    if git is None:
        return ""
    # git.exe is in cmd/, bin/, or mingw64/bin/ of the Git installation.
    for root in Path(git).resolve().parents[1:3]:
        bash = root / "bin" / "bash.exe"
        if bash.is_file():
            return str(bash)
    return ""


BASH = find_bash()
