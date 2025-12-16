"""This module provides convenient function facilitating scripting.

These functions have been copied from scikit-build project.
See https://github.com/scikit-build/scikit-build
"""

from __future__ import annotations

import os
import shutil
import sys

from pathlib import Path
from os import environ as os_environ, chdir as os_chdir, environ
from contextlib import contextmanager
from functools import wraps


def mkdir_p(path):
    """Ensure directory ``path`` exists. If needed, parent directories are created.

    Uses pathlib with parents=True and exist_ok=True.
    """
    Path(path).mkdir(parents=True, exist_ok=True)


@contextmanager
def push_env(**kwargs):
    """This context manager allow to set/unset environment variables."""
    saved_env = dict(os_environ)
    for var, value in kwargs.items():
        if value is not None:
            os_environ[var] = value
        elif var in os_environ:
            del os_environ[var]
    yield
    os_environ.clear()
    for saved_var, saved_value in saved_env.items():
        os_environ[saved_var] = saved_value


class ContextDecorator:
    """A base class or mixin that enables context managers to work as
    decorators."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __enter__(self):
        # Note: Returning self means that in "with ... as x", x will be self
        return self

    def __exit__(self, typ, val, traceback):
        pass

    def __call__(self, func):
        @wraps(func)
        def inner(*args, **kwds):  # pylint:disable=missing-docstring
            with self:
                return func(*args, **kwds)

        return inner


class push_dir(ContextDecorator):
    """Context manager to change current directory."""

    def __init__(self, directory=None, make_directory=False):
        """
        :param directory:
          Path to set as current working directory. If ``None``
          is passed, current working directory is used instead.

        :param make_directory:
          If True, ``directory`` is created.
        """
        self.directory = None
        self.make_directory = None
        self.old_cwd = None
        super().__init__(directory=directory, make_directory=make_directory)

    def __enter__(self):
        self.old_cwd = Path.cwd()
        if self.directory:
            if self.make_directory:
                mkdir_p(self.directory)
            os_chdir(self.directory)
        return self

    def __exit__(self, typ, val, traceback):
        os_chdir(self.old_cwd)


def _remove_tree(path: Path) -> None:
    """Recursively delete a file or directory using pathlib only."""
    if not path.exists():
        return
    if path.is_file() or path.is_symlink():
        try:
            path.unlink()
        except OSError:
            pass
        return
    for child in path.iterdir():
        _remove_tree(child)
    try:
        path.rmdir()
    except OSError:
        pass


def read_env_file(
    file_path: os.PathLike | str, build_dir_root: os.PathLike | str
) -> dict[str, str]:
    """Read a simple .env-style file and return a dict of key/value pairs.

    Supported syntax:
    - Blank lines and lines starting with '#' are ignored.
    - Optional leading 'export ' prefix is ignored.
    - KEY=VALUE pairs; surrounding single or double quotes are stripped.
    - Whitespace around keys and the '=' is ignored.

    This function does not perform variable expansion or modify os.environ.
    """
    result: dict[str, str] = {}
    path = Path(file_path)
    if not path.exists():
        return result
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return result

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        value = value.replace("${BUILD_DIR_ROOT}", str(build_dir_root))
        # Strip surrounding quotes if present
        if (len(value) >= 2) and (
            (value[0] == value[-1] == '"') or (value[0] == value[-1] == "'")
        ):
            value = value[1:-1]
        result[key] = value
    return result


def _which(exe_name: str) -> str | Path | None:
    """Simple PATH-based lookup using pathlib only."""
    pathext: list[str] = environ.get("PATHEXT", ".EXE;.BAT;.CMD").split(";")
    paths: list[str] = environ.get("PATH", "").split(";")
    exe: Path = Path(exe_name)
    candidates = [exe] if exe.suffix else [Path(exe_name + ext) for ext in pathext]
    for p in paths:
        if not p:
            continue
        base = Path(p)
        for c in candidates:
            fp = base / c
            try:
                if fp.exists():
                    return fp
            except OSError:
                continue
    return None


def detect_platform() -> tuple[str, str]:
    # returns (os_name, arch)
    uname = os.uname() if hasattr(os, "uname") else None
    sysname = (
        uname.sysname if uname else ("Windows" if os.name == "nt" else sys.platform)
    )
    machine = (
        uname.machine
        if uname
        else (os.environ.get("PROCESSOR_ARCHITECTURE", "").lower())
    )
    os_name = (
        "linux"
        if sysname.lower().startswith("linux")
        else (
            "darwin"
            if sysname.lower().startswith("darwin") or sys.platform == "darwin"
            else ("windows" if os.name == "nt" else "unknown")
        )
    )
    # Normalize machine
    arch = machine
    if os_name == "darwin":
        if machine in ("x86_64",):
            arch = "x64"
        elif machine in ("arm64", "aarch64"):
            arch = "arm64"
    elif os_name == "linux":
        if machine in ("x86_64",):
            arch = "x64"
        elif machine in ("i686", "i386"):
            arch = "x86"
        elif machine in ("aarch64",):
            arch = "aarch64"
    return os_name, arch


def which_required(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(
            f"MISSING: {name} not found in PATH; aborting until required executables can be found"
        )
    return path
