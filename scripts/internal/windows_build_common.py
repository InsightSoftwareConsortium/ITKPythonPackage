__all__ = ["DEFAULT_PY_ENVS", "venv_paths"]

import os
import shutil
from subprocess import check_call

DEFAULT_PY_ENVS = ["310-x64", "311-x64"]

SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))


def venv_paths(python_version):
    # Create venv
    venv_executable = "C:/Python%s/Scripts/virtualenv.exe" % (python_version)
    venv_dir = os.path.join(ROOT_DIR, "venv-%s" % python_version)
    check_call([venv_executable, venv_dir])

    python_executable = os.path.join(venv_dir, "Scripts", "python.exe")
    python_include_dir = "C:/Python%s/include" % (python_version)

    # XXX It should be possible to query skbuild for the library dir associated
    #     with a given interpreter.
    xy_ver = python_version.split("-")[0]

    # Version-specific library (e.g., python311.lib) - required for
    # CMake's FindPython3 to extract version info for Development.Module
    python_library = "C:/Python%s/libs/python%s.lib" % (python_version, xy_ver)

    # Stable ABI library (python3.lib) - for Development.SABIModule
    if int(xy_ver[1:]) >= 11:
        python_sabi_library = "C:/Python%s/libs/python3.lib" % (python_version)
    else:
        python_sabi_library = python_library

    print()
    print("Python3_EXECUTABLE: %s" % python_executable)
    print("Python3_INCLUDE_DIR: %s" % python_include_dir)
    print("Python3_LIBRARY: %s" % python_library)
    print("Python3_SABI_LIBRARY: %s" % python_sabi_library)

    pip = os.path.join(venv_dir, "Scripts", "pip.exe")

    ninja_executable = os.path.join(venv_dir, "Scripts", "ninja.exe")
    if not os.path.exists(ninja_executable):
        ninja_executable = shutil.which("ninja.exe")
    print("NINJA_EXECUTABLE:%s" % ninja_executable)

    # Update PATH
    path = os.path.join(venv_dir, "Scripts")

    return (
        python_executable,
        python_include_dir,
        python_library,
        python_sabi_library,
        pip,
        ninja_executable,
        path,
    )
