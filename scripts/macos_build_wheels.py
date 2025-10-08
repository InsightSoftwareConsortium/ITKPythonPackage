#!/usr/bin/env python

import os
import argparse

SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
STANDALONE_DIR = os.path.join(ROOT_DIR, "standalone-build")

print("SCRIPT_DIR: %s" % SCRIPT_DIR)
print("ROOT_DIR: %s" % ROOT_DIR)
print("STANDALONE_DIR: %s" % STANDALONE_DIR)

sys.path.insert(0, os.path.join(SCRIPT_DIR, "internal"))
from wheel_builder_utils import push_dir, push_env
from windows_build_common import DEFAULT_PY_ENVS, venv_paths

# import glob
# import os
# import shutil
# from subprocess import check_call
# import sys

# SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
# ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
# STANDALONE_DIR = os.path.join(ROOT_DIR, "standalone-build")
# PROJECT_NAME = "VTK"

# sys.path.insert(0, os.path.join(SCRIPT_DIR, "internal"))
# from wheel_builder_utils import push_dir, push_env
# from macos_build_common import DEFAULT_PY_ENVS, venv_paths


# def pip_install(python_dir, package, upgrade=True):
    # pip = os.path.join(python_dir, "bin", "pip")
    # print("Installing %s using %s" % (package, pip))
    # args = [pip, "install"]
    # if upgrade:
        # args.append("--upgrade")
    # args.append(package)
    # check_call(args)


# def prepare_build_env(python_version):
    # python_dir = "/Library/Frameworks/Python.framework/Versions/%s" % python_version
    # if not os.path.exists(python_dir):
        # raise FileNotFoundError(
            # "Aborting. python_dir [%s] does not exist." % python_dir)

    # venv = os.path.join(python_dir, "bin", "pyvenv")
    # venv_dir = os.path.join(ROOT_DIR, "venv-%s" % python_version)
    # print("Creating python virtual environment: %s" % venv_dir)
    # if not os.path.exists(venv_dir):
        # check_call([venv, venv_dir])
    # pip_install(venv_dir, "scikit-build")


# def build_wheel(python_version, cleanup=False):

    # py_exe, \
    # py_inc_dir, \
    # py_lib, \
    # pip, \
    # ninja_executable, \
    # path = venv_paths(python_version)

    # with push_env(PATH="%s%s%s" % (path, os.pathsep, os.environ["PATH"])):

        # # Install dependencies
        # check_call([pip, "install", "--upgrade",
                    # "-r", os.path.join(ROOT_DIR, "requirements-dev.txt")])

        # build_type = 'Release'
        # build_path = "%s/%s-osx_%s" % (ROOT_DIR, PROJECT_NAME, python_version)
        # osx_target="10.9"

        # # Clean up previous invocations
        # if cleanup and os.path.exists(build_path):
            # shutil.rmtree(build_path)

        # print("#")
        # print("# Build single %s wheel" % PROJECT_NAME)
        # print("#")

        # # Generate wheel
        # check_call([
            # py_exe,
            # "setup.py", "bdist_wheel",
            # "--build-type", build_type,
            # "-G", "Ninja",
            # "--plat-name", "macosx-%s-x86_64" % osx_target,
            # "--",
            # "-DPYTHON_EXECUTABLE:FILEPATH=%s" % py_exe,
            # "-DPYTHON_INCLUDE_DIR:PATH=%s" % py_inc_dir,
            # "-DPYTHON_LIBRARY:FILEPATH=%s" % py_lib
        # ])

        # # Cleanup
        # check_call([py_exe, "setup.py", "clean"])


# def build_wheels(py_envs=DEFAULT_PY_ENVS, cleanup=False):

    # for py_env in py_envs:
        # prepare_build_env(py_env)

    # with push_dir(directory=STANDALONE_DIR, make_directory=True):

        # tools_venv = os.path.join(ROOT_DIR, "venv-%s" % DEFAULT_PY_ENVS[0])
        # pip_install(tools_venv, "ninja")
        # ninja_executable = os.path.join(tools_venv, "bin", "ninja")

        # # Build standalone project and populate archive cache
        # check_call([
            # "cmake",
            # "-DVTKPythonPackage_BUILD_PYTHON:BOOL=OFF",
            # "-G", "Ninja",
            # "-DCMAKE_MAKE_PROGRAM:FILEPATH=%s" % ninja_executable,
            # ROOT_DIR
        # ])

    # # Compile wheels re-using standalone project and archive cache
    # for py_env in py_envs:
        # build_wheel(py_env, cleanup=cleanup)


# def main(py_envs=DEFAULT_PY_ENVS, cleanup=True):

    # build_wheels(py_envs=py_envs, cleanup=cleanup)


# if __name__ == '__main__':
    # main()
