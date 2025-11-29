__all__ = ["DEFAULT_PY_ENVS", "venv_paths"]

from subprocess import check_call
from pathlib import Path
from os import environ as os_environ

DEFAULT_PY_ENVS = ["39-x64", "310-x64", "311-x64"]

SCRIPT_DIR = Path(__file__).parent
# TODO: Hard-coded module must be 1 direectory above checkedout ITKPythonPackage
MODULE_EXAMPLESROOT_DIR = SCRIPT_DIR.parent.parent.resolve()


def _which(exe_name: Path | str) -> Path | None:
    """Minimal PATH search using pathlib only.

    Returns the first matching executable path as a string, or None if not found.
    """
    # On Windows, honor PATHEXT
    pathext = os_environ.get("PATHEXT", ".EXE;.BAT;.CMD").split(";")
    paths = os_environ.get("PATH", "").split(";")
    candidates: list[Path] = []
    if Path(exe_name).suffix:
        candidates.append(Path(exe_name))
    else:
        for ext in pathext:
            candidates.append(Path(exe_name + ext))
    for p in paths:
        if not p:
            continue
        base = Path(p)
        for c in candidates:
            full = base / c
            try:
                if full.exists():
                    return full
            except OSError:
                # Skip unreadable entries
                continue
    return None


def venv_paths(python_version):

    # Create venv
    venv_executable = f"C:/Python{python_version}/Scripts/virtualenv.exe"
    venv_dir = Path(MODULE_EXAMPLESROOT_DIR) / f"venv-{python_version}"
    check_call([venv_executable, str(venv_dir)])

    python_executable = venv_dir / "Scripts" / "python.exe"
    python_include_dir = f"C:/Python{python_version}/include"

    # XXX It should be possible to query skbuild for the library dir associated
    #     with a given interpreter.
    xy_ver = python_version.split("-")[0]

    if int(python_version.split("-")[0][1:]) >= 11:
        # Stable ABI
        python_library = f"C:/Python{python_version}/libs/python3.lib"
    else:
        python_library = f"C:/Python{python_version}/libs/python{xy_ver}.lib"

    print("")
    print(f"Python3_EXECUTABLE: {python_executable}")
    print(f"Python3_INCLUDE_DIR: {python_include_dir}")
    print(f"Python3_LIBRARY: {python_library}")

    pip = venv_dir / "Scripts" / "pip.exe"

    ninja_executable_path = venv_dir / "Scripts" / "ninja.exe"
    if ninja_executable_path.exists():
        ninja_executable = ninja_executable_path
    else:
        ninja_executable = _which("ninja.exe") or str(ninja_executable_path)
    print(f"NINJA_EXECUTABLE:{ninja_executable}")

    # Update PATH
    path = venv_dir / "Scripts"

    return (
        python_executable,
        python_include_dir,
        python_library,
        pip,
        ninja_executable,
        path,
    )
