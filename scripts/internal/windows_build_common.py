__all__ = ['DEFAULT_PY_ENVS', 'venv_paths']

from subprocess import check_call
import os
import shutil

DEFAULT_PY_ENVS = ["38-x64", "39-x64", "310-x64", "311-x64"]

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

    if int(python_version.split("-")[0][1:]) >= 11:
        # Stable ABI
        python_library = "C:/Python%s/libs/python3.lib" % (python_version)
    else:
        python_library = "C:/Python%s/libs/python%s.lib" % (python_version, xy_ver)

    print("")
    print("Python3_EXECUTABLE: %s" % python_executable)
    print("Python3_INCLUDE_DIR: %s" % python_include_dir)
    print("Python3_LIBRARY: %s" % python_library)

    pip = os.path.join(venv_dir, "Scripts", "pip.exe")

    ninja_executable = os.path.join(venv_dir, "Scripts", "ninja.exe")
    if not os.path.exists(ninja_executable):
        ninja_executable = shutil.which("ninja.exe")
    print("NINJA_EXECUTABLE:%s" % ninja_executable)

    # Update PATH
    path = os.path.join(venv_dir, "Scripts")

    return python_executable, \
        python_include_dir, \
        python_library, \
        pip, \
        ninja_executable, \
        path
