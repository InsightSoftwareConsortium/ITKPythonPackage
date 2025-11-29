"""This module provides convenient function facilitating scripting.

These functions have been copied from scikit-build project.
See https://github.com/scikit-build/scikit-build
"""

from pathlib import Path
from os import environ as os_environ, chdir as os_chdir, environ
from contextlib import contextmanager
from functools import wraps
from subprocess import check_call as subprocess_check_call


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


def _which(exe_name: str) -> str | None:
    """Simple PATH-based lookup using pathlib only."""
    pathext = environ.get("PATHEXT", ".EXE;.BAT;.CMD").split(";")
    paths = environ.get("PATH", "").split(";")
    exe = Path(exe_name)
    candidates = [exe] if exe.suffix else [Path(exe_name + ext) for ext in pathext]
    for p in paths:
        if not p:
            continue
        base = Path(p)
        for c in candidates:
            fp = base / c
            try:
                if fp.exists():
                    return str(fp)
            except OSError:
                continue
    return None


def echo_check_call(cmd: list | tuple | str | Path, **kwargs: dict) -> int:
    """Print the command then run subprocess.check_call.

    Parameters
    ----------
    cmd :
        Command to execute, same as subprocess.check_call.
    **kwargs :
        Additional keyword arguments forwarded to subprocess.check_call.
    """
    # Prepare a friendly command-line string for display
    try:
        if isinstance(cmd, (list, tuple)):
            display_cmd = " ".join(str(c) for c in cmd)
        else:
            display_cmd = str(cmd)
    except Exception as e:
        display_cmd = str(cmd)
    print(f">>Start Running: {display_cmd} in {Path.cwd()}")
    cmd_return_status: int = subprocess_check_call(cmd, **kwargs)
    print(f"<<Finished Running: {cmd_return_status=}")
    return cmd_return_status
