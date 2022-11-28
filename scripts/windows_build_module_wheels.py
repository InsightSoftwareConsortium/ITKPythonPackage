#!/usr/bin/env python

# See usage with .\scripts\windows_build_module_wheels.py --help

from subprocess import check_call
import os
import glob
import sys
import argparse
import shutil

SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.getcwd())

print("SCRIPT_DIR: %s" % SCRIPT_DIR)
print("ROOT_DIR: %s" % ROOT_DIR)

sys.path.insert(0, os.path.join(SCRIPT_DIR, "internal"))

from wheel_builder_utils import push_dir, push_env
from windows_build_common import DEFAULT_PY_ENVS, venv_paths

def install_and_import(package):
    """
    Install package with pip and import in current script.
    """
    import importlib
    try:
        importlib.import_module(package)
    except ImportError:
        import pip
        pip.main(['install', package])
    finally:
        globals()[package] = importlib.import_module(package)

def build_wheels(py_envs=DEFAULT_PY_ENVS, cleanup=True, cmake_options=[]):
    for py_env in py_envs:
        python_executable, \
                python_include_dir, \
                python_library, \
                pip, \
                ninja_executable, \
                path = venv_paths(py_env)

        with push_env(PATH="%s%s%s" % (path, os.pathsep, os.environ["PATH"])):

            # Install dependencies
            requirements_file = os.path.join(ROOT_DIR, "requirements-dev.txt")
            if os.path.exists(requirements_file):
                check_call([pip, "install", "--upgrade", "-r", requirements_file])
            check_call([pip, "install", "cmake"])
            check_call([pip, "install", "scikit_build", "--upgrade"])
            check_call([pip, "install", "ninja"])
            check_call([pip, "install", "delvewheel"])

            build_type = "Release"
            source_path = ROOT_DIR
            itk_build_path = os.path.abspath("%s/ITK-win_%s" % (os.path.join(SCRIPT_DIR, '..'), py_env))
            print('ITKDIR: %s' % itk_build_path)

            # Generate wheel
            check_call([
                python_executable,
                "setup.py", "bdist_wheel",
                "--build-type", build_type, "-G", "Ninja",
                "--",
                "-DCMAKE_MAKE_PROGRAM:FILEPATH=%s" % ninja_executable,
                "-DITK_DIR:PATH=%s" % itk_build_path,
                "-DWRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel",
                "-DSWIG_EXECUTABLE:FILEPATH=%s/Wrapping/Generators/SwigInterface/swig/bin/swig.exe" % itk_build_path,
                "-DBUILD_TESTING:BOOL=OFF",
                "-DCMAKE_INSTALL_LIBDIR:STRING=lib",
                "-DPython3_EXECUTABLE:FILEPATH=%s" % python_executable,
                "-DPython3_INCLUDE_DIR:PATH=%s" % python_include_dir,
                "-DPython3_INCLUDE_DIRS:PATH=%s" % python_include_dir,
                "-DPython3_LIBRARY:FILEPATH=%s" % python_library
            ] + cmake_options)
            # Cleanup
            if cleanup:
                check_call([python_executable, "setup.py", "clean"])

def rename_wheel_init(py_env, filepath):
    """
    Rename module __init__ file in wheel.
    This is required to prevent modules to override ITK's __init__ file on install.
    If the module ships its own __init__ file, it is automatically renamed to
    __init_{module_name}__ by this function. The renamed __init__ file will be executed
    by ITK's __init__ file when loading ITK.
    """
    python_executable, python_include_dir, python_library, pip, ninja_executable, path = venv_paths(py_env)

    # Get module info
    install_and_import("pkginfo")
    w = pkginfo.Wheel(filepath)
    module_name = w.name.split("itk-")[-1]
    module_version = w.version

    dist_dir = os.path.dirname(filepath)
    wheel_dir = os.path.join(dist_dir, "itk_" + module_name.replace('-','_') + "-" + module_version)
    init_dir = os.path.join(wheel_dir, "itk")
    init_file = os.path.join(init_dir, "__init__.py")

    # Unpack wheel and rename __init__ file if it exists.
    check_call([python_executable, "-m", "wheel", "unpack", filepath, "-d", dist_dir])
    if os.path.isfile(init_file):
        shutil.move(init_file, os.path.join(init_dir, "__init_" + module_name + "__.py"))
    # Pack wheel and clean wheel folder
    check_call([python_executable, "-m", "wheel", "pack", wheel_dir, "-d", dist_dir])
    shutil.rmtree(wheel_dir)

def fixup_wheel(py_envs, filepath, lib_paths:str='', exclude_libs:str=''):
    lib_paths = ';'.join(["C:/P/IPP/oneTBB-prefix/bin",lib_paths.strip()]).strip(';')
    print(f'Library paths for fixup: {lib_paths}')

    py_env = py_envs[0]
    
    delve_wheel = os.path.join("C:/P/IPP", "venv-" + py_env, "Scripts", "delvewheel.exe")
    check_call([delve_wheel, "repair", "--no-mangle-all", "--add-path",
        lib_paths, "--no-dll", exclude_libs, "--ignore-in-wheel", "-w",
        os.path.join(ROOT_DIR, "dist"), filepath])

    # The delve_wheel patch loading shared libraries is added to the module
    # __init__ file. Rename this file here to prevent conflicts on installation.
    # The renamed __init__ file will be executed when loading ITK.
    rename_wheel_init(py_env, filepath)

def fixup_wheels(py_envs, lib_paths:str='', exclude_libs:str=''):
    # shared library fix-up
    for wheel in glob.glob(os.path.join(ROOT_DIR, "dist", "*.whl")):
        fixup_wheel(py_envs, wheel, lib_paths, exclude_libs)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Driver script to build ITK Python module wheels.')
    parser.add_argument('--py-envs', nargs='+', default=DEFAULT_PY_ENVS,
            help='Target Python environment versions, e.g. "37-x64".')
    parser.add_argument('--no-cleanup', dest='cleanup', action='store_false', help='Do not clean up temporary build files.')
    parser.add_argument('--lib-paths', nargs=1, default='', help='Add semicolon-delimited library directories for delvewheel to include in the module wheel')
    parser.add_argument('--exclude-libs', nargs=1, default='', help='Add semicolon-delimited library names that must not be included in the module wheel, e.g. "nvcuda.dll"')
    parser.add_argument('cmake_options', nargs='*', help='Extra options to pass to CMake, e.g. -DBUILD_SHARED_LIBS:BOOL=OFF')
    args = parser.parse_args()

    build_wheels(cleanup=args.cleanup, py_envs=args.py_envs, cmake_options=args.cmake_options)
    fixup_wheels(args.py_envs, ';'.join(args.lib_paths), ';'.join(args.exclude_libs))
