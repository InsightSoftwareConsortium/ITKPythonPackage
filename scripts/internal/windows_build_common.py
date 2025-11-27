__all__ = ["DEFAULT_PY_ENVS", "venv_paths"]

from subprocess import check_call
import os
import shutil

DEFAULT_PY_ENVS = ["39-x64", "310-x64", "311-x64"]

SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))


def venv_paths(python_version):

    # Create venv
    venv_executable = f"C:/Python{python_version}/Scripts/virtualenv.exe"
    venv_dir = os.path.join(ROOT_DIR, f"venv-{python_version}")
    check_call([venv_executable, venv_dir])

    python_executable = os.path.join(venv_dir, "Scripts", "python.exe")
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

    pip = os.path.join(venv_dir, "Scripts", "pip.exe")

    ninja_executable = os.path.join(venv_dir, "Scripts", "ninja.exe")
    if not os.path.exists(ninja_executable):
        ninja_executable = shutil.which("ninja.exe")
    print(f"NINJA_EXECUTABLE:{ninja_executable}")

    # Update PATH
    path = os.path.join(venv_dir, "Scripts")

    return (
        python_executable,
        python_include_dir,
        python_library,
        pip,
        ninja_executable,
        path,
    )
