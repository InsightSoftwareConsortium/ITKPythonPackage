#!/usr/bin/env python

# See usage with .\scripts\windows_build_module_wheels.py --help
import sys
import argparse
from pathlib import Path
from os import environ, pathsep

from wheel_builder_utils import read_env_file

from wheel_builder_utils import _remove_tree
from build_python_instance_base import echo_check_call
from cmake_argument_builder import CMakeArgumentBuilder

# Get module info
import pkginfo

SCRIPT_DIR = Path(__file__).parent
IPP_SOURCE_DIR = SCRIPT_DIR.parent.resolve()
IPP_SUPERBUILD_BINARY_DIR = IPP_SOURCE_DIR / "ITK-source"
package_env_config = read_env_file(IPP_SOURCE_DIR / "build" / "package.env")
ITK_SOURCE_DIR = package_env_config["ITK_SOURCE_DIR"]

print(f"SCRIPT_DIR: {SCRIPT_DIR}")
print(f"ROOT_DIR: {IPP_SOURCE_DIR}")
print(f"ITK_SOURCE: {IPP_SUPERBUILD_BINARY_DIR}")

sys.path.insert(0, str(SCRIPT_DIR / "internal"))

from wheel_builder_utils import push_env
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

        pip.main(["install", package])
    finally:
        globals()[package] = importlib.import_module(package)


def build_wheels(py_envs=DEFAULT_PY_ENVS, cmake_options=None):
    if cmake_options is None:
        cmake_options = []
    for py_env in py_envs:
        (
            python_executable,
            python_include_dir,
            python_library,
            pip,
            ninja_executable,
            path,
        ) = venv_paths(py_env)

        with push_env(PATH=f"{path}{pathsep}{environ['PATH']}"):
            # Install dependencies
            echo_check_call(
                [python_executable, "-m", "pip", "install", "pip", "--upgrade"]
            )
            requirements_file = IPP_SOURCE_DIR / "requirements-dev.txt"
            if requirements_file.exists():
                echo_check_call(
                    [pip, "install", "--upgrade", "-r", str(requirements_file)]
                )
            echo_check_call([pip, "install", "cmake"])
            echo_check_call([pip, "install", "scikit-build-core", "--upgrade"])

            echo_check_call([pip, "install", "ninja", "--upgrade"])
            echo_check_call([pip, "install", "delvewheel"])

            itk_build_path = (SCRIPT_DIR.parent / f"ITK-win_{py_env}").resolve()
            print(f"ITKDIR: {itk_build_path}")

            minor_version = py_env.split("-")[0][1:]
            if int(minor_version) >= 11:
                # Stable ABI
                wheel_py_api = f"cp3{minor_version}"
            else:
                wheel_py_api = ""
            # Generate wheel
            # Build up cmake.define arguments via the builder
            defs = CMakeArgumentBuilder(
                {
                    "SKBUILD:BOOL": "ON",
                    "PY_SITE_PACKAGES_PATH:PATH": ".",
                    "CMAKE_BUILD_TYPE:STRING": "Release",
                    "CMAKE_MAKE_PROGRAM:FILEPATH": f"{ninja_executable}",
                    "ITK_DIR:PATH": f"{itk_build_path}",
                    "WRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING": "PythonWheel",
                    "SWIG_EXECUTABLE:FILEPATH": f"{itk_build_path}/Wrapping/Generators/SwigInterface/swig/bin/swig.exe",
                    "BUILD_TESTING:BOOL": "OFF",
                    "CMAKE_INSTALL_LIBDIR:STRING": "lib",
                    "Python3_EXECUTABLE:FILEPATH": f"{python_executable}",
                    "Python3_INCLUDE_DIR:PATH": f"{python_include_dir}",
                    "Python3_INCLUDE_DIRS:PATH": f"{python_include_dir}",
                    "Python3_LIBRARY:FILEPATH": f"{python_library}",
                    "Python3_SABI_LIBRARY:FILEPATH": f"{python_library}",
                }
            )
            # Merge any user-provided -D options
            for opt in cmake_options:
                if not isinstance(opt, str) or not opt.startswith("-D"):
                    continue
                try:
                    key, value = opt[2:].split("=", 1)
                except ValueError:
                    continue
                defs.set(key, value)

            cmd = [
                python_executable,
                "-m",
                "build",
                "--verbose",
                "--wheel",
                "--outdir",
                "dist",
                "--no-isolation",
                "--skip-dependency-check",
                f"--config-setting=wheel.py-api={wheel_py_api}",
                "--config-setting=cmake.args=-G Ninja",
            ]
            cmd += defs.getPythonBuildCommandLineArguments()
            cmd += [self.package_env_config["IPP_SOURCE_DIR"] / "BuildWheelsSupport"]
            echo_check_call(cmd)


def rename_wheel_init(py_env, filepath, add_module_name=True):
    """
    Rename module __init__ (if add_module_name is True) or __init_module__ (if
    add_module_name is False) file in wheel.  This is required to prevent
    modules to override ITK's __init__ file on install or to prevent delvewheel
    to override __init_module__ file.  If the module ships its own __init__
    file, it is automatically renamed to __init_{module_name}__ by this
    function. The renamed __init__ file will be executed by ITK's __init__ file
    when loading ITK.
    """
    (
        python_executable,
        python_include_dir,
        python_library,
        pip,
        ninja_executable,
        path,
    ) = venv_paths(py_env)

    w = pkginfo.Wheel(filepath)
    module_name = w.name.split("itk-")[-1]
    module_version = w.version

    dist_dir = Path(filepath).parent
    wheel_dir = dist_dir / (
        "itk_" + module_name.replace("-", "_") + "-" + module_version
    )
    init_dir = wheel_dir / "itk"
    init_file = init_dir / "__init__.py"
    init_file_module = init_dir / ("__init_" + module_name.split("-")[0] + "__.py")

    # Unpack wheel and rename __init__ file if it exists.
    echo_check_call(
        [python_executable, "-m", "wheel", "unpack", filepath, "-d", str(dist_dir)]
    )
    if add_module_name and init_file.is_file():
        init_file.rename(init_file_module)
    if not add_module_name and init_file_module.is_file():
        init_file_module.rename(init_file)

    # Pack wheel and clean wheel folder
    echo_check_call(
        [python_executable, "-m", "wheel", "pack", str(wheel_dir), "-d", str(dist_dir)]
    )
    _remove_tree(wheel_dir)


def fixup_wheel(py_envs, filepath, lib_paths: str = "", exclude_libs: str = ""):
    lib_paths = ";".join(["C:/P/IPP/oneTBB-prefix/bin", lib_paths.strip()]).strip(";")
    print(f"Library paths for fixup: {lib_paths}")

    py_env = py_envs[0]

    # Make sure the module __init_module__.py file has the expected name for
    # delvewheel, i.e., __init__.py.
    rename_wheel_init(py_env, filepath, False)

    delve_wheel = Path("C:/P/IPP") / ("venv-" + py_env) / "Scripts" / "delvewheel.exe"
    echo_check_call(
        [
            delve_wheel,
            "repair",
            "--no-mangle-all",
            "--add-path",
            lib_paths,
            "--no-dll",
            exclude_libs,
            "--ignore-in-wheel",
            "-w",
            str(IPP_SOURCE_DIR / "dist"),
            filepath,
        ]
    )

    # The delve_wheel patch loading shared libraries is added to the module
    # __init__ file. Rename this file here to prevent conflicts on installation.
    # The renamed __init__ file will be executed when loading ITK.
    rename_wheel_init(py_env, filepath)


def fixup_wheels(py_envs, lib_paths: str = "", exclude_libs: str = ""):
    # shared library fix-up
    for wheel in (IPP_SOURCE_DIR / "dist").glob("*.whl"):
        fixup_wheel(py_envs, wheel, lib_paths, exclude_libs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Driver script to build ITK Python module wheels."
    )
    parser.add_argument(
        "--py-envs",
        nargs="+",
        default=DEFAULT_PY_ENVS,
        help='Target Python environment versions, e.g. "39-x64".',
    )
    parser.add_argument(
        "--no-cleanup",
        dest="cleanup",
        action="store_false",
        help="Do not clean up temporary build files.",
    )
    parser.add_argument(
        "--lib-paths",
        nargs=1,
        default="",
        help="Add semicolon-delimited library directories for delvewheel to include in the module wheel",
    )
    parser.add_argument(
        "--exclude-libs",
        nargs=1,
        default="",
        help='Add semicolon-delimited library names that must not be included in the module wheel, e.g. "nvcuda.dll"',
    )
    parser.add_argument(
        "cmake_options",
        nargs="*",
        help="Extra options to pass to CMake, e.g. -DBUILD_SHARED_LIBS:BOOL=OFF",
    )
    args = parser.parse_args()

    build_wheels(py_envs=args.py_envs, cmake_options=args.cmake_options)
    # append the oneTBB-prefix\\bin directory for fixing wheels built with local oneTBB
    search_lib_paths = [s for s in args.lib_paths.rstrip(";") if s]
    search_lib_paths.append(f"{IPP_SOURCE_DIR}\\oneTBB-prefix\\bin")
    search_lib_paths_str: str = ";".join(search_lib_paths)
    fixup_wheels(args.py_envs, ";".join(args.lib_paths), search_lib_paths_str)
