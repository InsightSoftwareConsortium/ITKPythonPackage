#!/usr/bin/env python

import argparse
import glob
import os
import shutil
import sys

from subprocess import check_call


SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
ITK_SOURCE = os.path.join(ROOT_DIR, "ITK-source")

print(f"SCRIPT_DIR: {SCRIPT_DIR}")
print(f"ROOT_DIR: {ROOT_DIR}")
print(f"ITK_SOURCE: {ITK_SOURCE}")

sys.path.insert(0, os.path.join(SCRIPT_DIR, "internal"))
from wheel_builder_utils import push_dir, push_env
from windows_build_common import DEFAULT_PY_ENVS, venv_paths


def pip_install(python_dir, package, upgrade=True):
    pip = os.path.join(python_dir, "Scripts", "pip.exe")
    print(f"Installing {package} using {pip}")
    args = [pip, "install"]
    if upgrade:
        args.append("--upgrade")
    args.append(package)
    check_call(args)


def prepare_build_env(python_version):
    python_dir = f"C:/Python{python_version}"
    if not os.path.exists(python_dir):
        raise FileNotFoundError(f"Aborting. python_dir [{python_dir}] does not exist.")

    virtualenv_exe = os.path.join(python_dir, "Scripts", "virtualenv.exe")
    venv_dir = os.path.join(ROOT_DIR, f"venv-{python_version}")
    if not os.path.exists(venv_dir):
        print(f"Creating python virtual environment: {venv_dir}")
        check_call([virtualenv_exe, venv_dir])
        pip_install(venv_dir, "scikit-build-core")
        pip_install(venv_dir, "ninja")
        pip_install(venv_dir, "delvewheel")


def build_wrapped_itk(
    ninja_executable,
    build_type,
    source_path,
    build_path,
    python_executable,
    python_include_dir,
    python_library,
):

    tbb_dir = os.path.join(ROOT_DIR, "oneTBB-prefix", "lib", "cmake", "TBB")

    # Build ITK python
    with push_dir(directory=build_path, make_directory=True):

        check_call(
            [
                "cmake",
                f"-DCMAKE_MAKE_PROGRAM:FILEPATH={ninja_executable}",
                f"-DCMAKE_BUILD_TYPE:STRING={build_type}",
                f"-DITK_SOURCE_DIR:PATH={source_path}",
                f"-DITK_BINARY_DIR:PATH={build_path}",
                "-DBUILD_TESTING:BOOL=OFF",
                "-DSKBUILD:BOOL=ON",
                f"-DPython3_EXECUTABLE:FILEPATH={python_executable}",
                "-DITK_WRAP_unsigned_short:BOOL=ON",
                "-DITK_WRAP_double:BOOL=ON",
                "-DITK_WRAP_complex_double:BOOL=ON",
                "-DITK_WRAP_IMAGE_DIMS:STRING=2;3;4",
                f"-DPython3_INCLUDE_DIR:PATH={python_include_dir}",
                f"-DPython3_INCLUDE_DIRS:PATH={python_include_dir}",
                f"-DPython3_LIBRARY:FILEPATH={python_library}",
                f"-DPython3_SABI_LIBRARY:FILEPATH={python_library}",
                "-DWRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel",
                "-DWRAP_ITK_INSTALL_COMPONENT_PER_MODULE:BOOL=ON",
                "-DPY_SITE_PACKAGES_PATH:PATH=.",
                "-DITK_LEGACY_SILENT:BOOL=ON",
                "-DITK_WRAP_PYTHON:BOOL=ON",
                "-DITK_WRAP_DOC:BOOL=ON",
                "-DDOXYGEN_EXECUTABLE:FILEPATH=C:/P/doxygen/doxygen.exe",
                "-DModule_ITKTBB:BOOL=ON",
                f"-DTBB_DIR:PATH={tbb_dir}",
                "-G",
                "Ninja",
                source_path,
            ]
        )
        check_call([ninja_executable])


def build_wheel(
    python_version,
    build_type="Release",
    single_wheel=False,
    cleanup=True,
    wheel_names=None,
    cmake_options=None,
):
    if cmake_options is None:
        cmake_options = []

    (
        python_executable,
        python_include_dir,
        python_library,
        pip,
        ninja_executable,
        path,
    ) = venv_paths(python_version)

    with push_env(PATH=f"{path}{os.pathsep}{os.environ['PATH']}"):

        # Install dependencies
        check_call(
            [
                pip,
                "install",
                "--upgrade",
                "-r",
                os.path.join(ROOT_DIR, "requirements-dev.txt"),
            ]
        )

        source_path = f"{ITK_SOURCE}/ITK"
        build_path = f"{ROOT_DIR}/ITK-win_{python_version}"
        pyproject_configure = os.path.join(SCRIPT_DIR, "pyproject_configure.py")
        env_file = os.path.join(os.path.dirname(SCRIPT_DIR), "build", "package.env")

        # Clean up previous invocations
        if cleanup and os.path.exists(build_path):
            shutil.rmtree(build_path)

        if single_wheel:

            print("#")
            print("# Build single ITK wheel")
            print("#")

            # Configure pyproject.toml
            check_call(
                [python_executable, pyproject_configure, "--env-file", env_file, "itk"]
            )

            # Generate wheel
            check_call(
                [
                    python_executable,
                    "-m",
                    "build",
                    "--verbose",
                    "--wheel",
                    "--outdir",
                    "dist",
                    "--no-isolation",
                    "--skip-dependency-check",
                    f"--config-setting=cmake.build-type={build_type}",
                    f"--config-setting=cmake.define.ITK_SOURCE_DIR:PATH={source_path}",
                    f"--config-setting=cmake.define.ITK_BINARY_DIR:PATH={build_path}",
                    "--config-setting=cmake.define.Python3_EXECUTABLE:FILEPATH=%s"
                    % python_executable,
                    "--config-setting=cmake.define.Python3_INCLUDE_DIR:PATH=%s"
                    % python_include_dir,
                    "--config-setting=cmake.define.Python3_INCLUDE_DIRS:PATH=%s"
                    % python_include_dir,
                    "--config-setting=cmake.define.Python3_LIBRARY:FILEPATH=%s"
                    % python_library,
                    "--config-setting=cmake.define.DOXYGEN_EXECUTABLE:FILEPATH=C:/P/doxygen/doxygen.exe",
                ]
                + [
                    o.replace("-D", "--config-setting=cmake.define.")
                    for o in cmake_options
                ]
                + [
                    ".",
                ]
            )

        else:

            print("#")
            print("# Build multiple ITK wheels")
            print("#")

            build_wrapped_itk(
                ninja_executable,
                build_type,
                source_path,
                build_path,
                python_executable,
                python_include_dir,
                python_library,
            )

            # Build wheels
            if wheel_names is None:
                with open(os.path.join(SCRIPT_DIR, "WHEEL_NAMES.txt")) as content:
                    wheel_names = [
                        wheel_name.strip() for wheel_name in content.readlines()
                    ]

            env_file = os.path.join(os.path.dirname(SCRIPT_DIR), "build", "package.env")
            for wheel_name in wheel_names:
                # Configure pyproject.toml
                check_call(
                    [
                        python_executable,
                        pyproject_configure,
                        "--env-file",
                        env_file,
                        wheel_name,
                    ]
                )

                # Generate wheel
                check_call(
                    [
                        python_executable,
                        "-m",
                        "build",
                        "--verbose",
                        "--wheel",
                        "--outdir",
                        "dist",
                        "--no-isolation",
                        "--skip-dependency-check",
                        f"--config-setting=cmake.build-type={build_type}",
                        "--config-setting=cmake.define.ITK_SOURCE_DIR:PATH=%s"
                        % source_path,
                        "--config-setting=cmake.define.ITK_BINARY_DIR:PATH=%s"
                        % build_path,
                        "--config-setting=cmake.define.ITKPythonPackage_ITK_BINARY_REUSE:BOOL=ON",
                        "--config-setting=cmake.define.ITKPythonPackage_WHEEL_NAME:STRING=%s"
                        % wheel_name,
                        "--config-setting=cmake.define.Python3_EXECUTABLE:FILEPATH=%s"
                        % python_executable,
                        "--config-setting=cmake.define.Python3_INCLUDE_DIR:PATH=%s"
                        % python_include_dir,
                        "--config-setting=cmake.define.Python3_INCLUDE_DIRS:PATH=%s"
                        % python_include_dir,
                        "--config-setting=cmake.define.Python3_LIBRARY:FILEPATH=%s"
                        % python_library,
                    ]
                    + [
                        o.replace("-D", "--config-setting=cmake.define.")
                        for o in cmake_options
                    ]
                    + [
                        ".",
                    ]
                )

        # Remove unnecessary files for building against ITK
        if cleanup:
            for root, _, file_list in os.walk(build_path):
                for filename in file_list:
                    extension = os.path.splitext(filename)[1]
                    if extension in [".cpp", ".xml", ".obj", ".o"]:
                        os.remove(os.path.join(root, filename))
            shutil.rmtree(os.path.join(build_path, "Wrapping", "Generators", "CastXML"))


def fixup_wheel(py_envs, filepath, lib_paths: str = ""):
    lib_paths = lib_paths.strip() if lib_paths.isspace() else lib_paths.strip() + ";"
    lib_paths += "C:/P/IPP/oneTBB-prefix/bin"
    print(f"Library paths for fixup: {lib_paths}")

    py_env = py_envs[0]

    delve_wheel = os.path.join(ROOT_DIR, "venv-" + py_env, "Scripts", "delvewheel.exe")
    check_call(
        [
            delve_wheel,
            "repair",
            "--no-mangle-all",
            "--add-path",
            lib_paths,
            "--ignore-in-wheel",
            "-w",
            os.path.join(ROOT_DIR, "dist"),
            filepath,
        ]
    )


def fixup_wheels(single_wheel, py_envs, lib_paths: str = ""):
    # TBB library fix-up
    tbb_wheel = "itk_core"
    if single_wheel:
        tbb_wheel = "itk"
    for wheel in glob.glob(os.path.join(ROOT_DIR, "dist", tbb_wheel + "*.whl")):
        fixup_wheel(py_envs, wheel, lib_paths)


def test_wheels(python_env):
    (
        python_executable,
        python_include_dir,
        python_library,
        pip,
        ninja_executable,
        path,
    ) = venv_paths(python_env)
    check_call([pip, "install", "numpy"])
    check_call([pip, "install", "itk", "--no-cache-dir", "--no-index", "-f", "dist"])
    print("Wheel successfully installed.")
    check_call([python_executable, os.path.join(ROOT_DIR, "docs/code/test.py")])
    print("Documentation tests passed.")


def build_wheels(
    py_envs=DEFAULT_PY_ENVS,
    single_wheel=False,
    cleanup=False,
    wheel_names=None,
    cmake_options=None,
):
    if cmake_options is None:
        cmake_options = []

    for py_env in py_envs:
        prepare_build_env(py_env)

    build_type = "Release"

    with push_dir(directory=ITK_SOURCE, make_directory=True):

        cmake_executable = "cmake.exe"
        tools_venv = os.path.join(ROOT_DIR, "venv-" + py_envs[0])
        ninja_executable = shutil.which("ninja.exe")
        if ninja_executable is None:
            pip_install(tools_venv, "ninja")
            ninja_executable = os.path.join(tools_venv, "Scripts", "ninja.exe")

        # Build standalone project and populate the archive cache
        check_call(
            [
                cmake_executable,
                f"-DCMAKE_BUILD_TYPE:STRING={build_type}",
                "-DITKPythonPackage_BUILD_PYTHON:PATH=0",
                "-G",
                "Ninja",
                f"-DCMAKE_MAKE_PROGRAM:FILEPATH={ninja_executable}",
                ROOT_DIR,
            ]
        )

        check_call([ninja_executable])

    # Compile wheels re-using standalone project and archive cache
    for py_env in py_envs:
        tools_venv = os.path.join(ROOT_DIR, "venv-" + py_env)
        ninja_executable = shutil.which("ninja.exe")
        if ninja_executable is None:
            pip_install(tools_venv, "ninja")
        build_wheel(
            py_env,
            build_type,
            single_wheel=single_wheel,
            cleanup=cleanup,
            wheel_names=wheel_names,
            cmake_options=cmake_options,
        )


def main(wheel_names=None):
    parser = argparse.ArgumentParser(
        description="Driver script to build ITK Python wheels."
    )
    parser.add_argument(
        "--single-wheel",
        action="store_true",
        help="Build a single wheel as opposed to one wheel per ITK module group.",
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
        "cmake_options",
        nargs="*",
        help="Extra options to pass to CMake, e.g. -DBUILD_SHARED_LIBS:BOOL=OFF",
    )
    args = parser.parse_args()

    build_wheels(
        single_wheel=args.single_wheel,
        cleanup=args.cleanup,
        py_envs=args.py_envs,
        wheel_names=wheel_names,
        cmake_options=args.cmake_options,
    )
    fixup_wheels(args.single_wheel, args.py_envs, ";".join(args.lib_paths))
    for py_env in args.py_envs:
        test_wheels(py_env)


if __name__ == "__main__":
    main()
