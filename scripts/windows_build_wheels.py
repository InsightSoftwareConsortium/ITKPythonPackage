#!/usr/bin/env python

import argparse
import sys
from pathlib import Path
from os import environ, pathsep

from subprocess import check_call
from dotenv import dotenv_values

from scripts.wheel_builder_utils import _which, _remove_tree

SCRIPT_DIR = Path(__file__).parent
IPP_SOURCE_DIR = SCRIPT_DIR.parent.resolve()
IPP_SUPERBUILD_BINARY_DIR = IPP_SOURCE_DIR / "ITK-source"
package_env_config = dotenv_values(IPP_SOURCE_DIR / "build" / "package.env")
ITK_SOURCE_DIR = package_env_config["ITK_SOURCE_DIR"]

print(f"SCRIPT_DIR: {SCRIPT_DIR}")
print(f"ROOT_DIR: {IPP_SOURCE_DIR}")
print(f"ITK_SOURCE: {IPP_SUPERBUILD_BINARY_DIR}")

sys.path.insert(0, str(SCRIPT_DIR / "internal"))
from wheel_builder_utils import push_dir, push_env
from windows_build_common import DEFAULT_PY_ENVS, venv_paths


def pip_install(python_dir, package, upgrade=True):
    pip = Path(python_dir) / "Scripts" / "pip.exe"
    print(f"Installing {package} using {pip}")
    args = [pip, "install"]
    if upgrade:
        args.append("--upgrade")
    args.append(package)
    check_call(args)


def prepare_build_env(python_version):
    python_dir = Path(f"C:/Python{python_version}")
    if not python_dir.exists():
        raise FileNotFoundError(f"Aborting. python_dir [{python_dir}] does not exist.")

    virtualenv_exe = python_dir / "Scripts" / "virtualenv.exe"
    venv_dir = IPP_SOURCE_DIR / f"venv-{python_version}"
    if not venv_dir.exists():
        print(f"Creating python virtual environment: {venv_dir}")
        check_call([str(virtualenv_exe), str(venv_dir)])
        pip_install(venv_dir, "scikit-build-core")
        pip_install(venv_dir, "ninja")
        pip_install(venv_dir, "delvewheel")


def build_wrapped_itk(
    ninja_executable,
    build_type,
    itk_source_dir,
    build_path,
    python_executable,
    python_include_dir,
    python_library,
):

    tbb_dir = IPP_SOURCE_DIR / "oneTBB-prefix" / "lib" / "cmake" / "TBB"

    # Build ITK python
    with push_dir(directory=build_path, make_directory=True):
        use_tbb: str = "ON"
        cmd = [
            "cmake",
            "-G",
            "Ninja",
            f"-DCMAKE_MAKE_PROGRAM:FILEPATH={ninja_executable}",
            f"-DCMAKE_BUILD_TYPE:STRING={build_type}",
            f"-DITK_SOURCE_DIR:PATH={itk_source_dir}",
            f"-DITK_BINARY_DIR:PATH={build_path}",
            "-DBUILD_TESTING:BOOL=OFF",
            # TODO: CMAKE_PLATFORM OSX_DEPLOYMENT OSX_ARCHITECTURES
            # TODO: CMAKE_COMPILER_ARGS added here for linux mac to respect CC and CXX env settings
            "-DSKBUILD:BOOL=ON",  # TODO: IS THIS NEEDED?  It is not used
            f"-DPython3_EXECUTABLE:FILEPATH={python_executable}",
            f"-DPython3_INCLUDE_DIR:PATH={python_include_dir}",
            f"-DPython3_INCLUDE_DIRS:PATH={python_include_dir}",  # TODO: Outdated variable can be removed
            f"-DPython3_LIBRARY:FILEPATH={python_library}",
            f"-DPython3_SABI_LIBRARY:FILEPATH={python_library}",
            "-DITK_WRAP_unsigned_short:BOOL=ON",
            "-DITK_WRAP_double:BOOL=ON",
            "-DITK_WRAP_complex_double:BOOL=ON",
            "-DITK_WRAP_IMAGE_DIMS:STRING=2;3;4",
            "-DWRAP_ITK_INSTALL_COMPONENT_IDENTIFIER:STRING=PythonWheel",
            "-DWRAP_ITK_INSTALL_COMPONENT_PER_MODULE:BOOL=ON",
            "-DPY_SITE_PACKAGES_PATH:PATH=.",
            "-DITK_LEGACY_SILENT:BOOL=ON",
            "-DITK_WRAP_PYTHON:BOOL=ON",
            "-DITK_WRAP_DOC:BOOL=ON",
            f"-DDOXYGEN_EXECUTABLE:FILEPATH={package_env_config['DOXYGEN_EXECUTABLE']}",
            f"-DModule_ITKTBB:BOOL={use_tbb}",
            f"-DTBB_DIR:PATH={tbb_dir}",
            "-S",
            itk_source_dir,
            "-B",
            build_path,
        ]
        check_call(cmd)
        check_call([ninja_executable, "-C", build_path])


def build_wheel(
    python_version,
    build_type="Release",
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

    with push_env(PATH=f"{path}{pathsep}{environ['PATH']}"):

        # Install dependencies
        check_call(
            [
                pip,
                "install",
                "--upgrade",
                "-r",
                str(IPP_SOURCE_DIR / "requirements-dev.txt"),
            ]
        )

        source_path = f"{package_env_config['ITK_SOURCE_DIR']}"
        build_path = IPP_SOURCE_DIR / f"ITK-win_{python_version}"
        pyproject_configure = SCRIPT_DIR / "pyproject_configure.py"

        # Clean up previous invocations
        if cleanup and Path(build_path).exists():
            _remove_tree(Path(build_path))

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
            with open(SCRIPT_DIR / "WHEEL_NAMES.txt", "r", encoding="utf-8") as content:
                wheel_names = [wheel_name.strip() for wheel_name in content.readlines()]

        env_file = IPP_SOURCE_DIR / "build" / "package.env"
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

            use_tbb: str = "ON"
            # Generate wheel
            check_call(
                [
                    python_executable,
                    "-m",
                    "build",
                    "--verbose",
                    "--wheel",
                    "--outdir",
                    str(IPP_SOURCE_DIR / "dist"),
                    "--no-isolation",
                    "--skip-dependency-check",
                    f"--config-setting=cmake.define.ITK_SOURCE_DIR:PATH={ITK_SOURCE_DIR}",
                    f"--config-setting=cmake.define.ITK_BINARY_DIR:PATH={build_path}",
                    # TODO: add OSX_DEPLOYMENT OSX_ARCHITECTURES here for linux mac
                    f"--config-setting=cmake.define.ITKPythonPackage_USE_TBB:BOOL={use_tbb}",  # TODO: May not be needed
                    "--config-setting=cmake.define.ITKPythonPackage_ITK_BINARY_REUSE:BOOL=ON",
                    f"--config-setting=cmake.define.ITKPythonPackage_WHEEL_NAME:STRING={wheel_name}",
                    f"--config-setting=cmake.define.Python3_EXECUTABLE:FILEPATH={python_executable}",
                    f"--config-setting=cmake.define.Python3_INCLUDE_DIR:PATH={python_include_dir}",
                    f"--config-setting=cmake.define.Python3_INCLUDE_DIRS:PATH={python_include_dir}",  # TODO: outdated variable can be removed
                    f"--config-setting=cmake.define.Python3_LIBRARY:FILEPATH={python_library}",
                    f"--config-setting=cmake.define.DOXYGEN_EXECUTABLE:FILEPATH={package_env_config['DOXYGEN_EXECUTABLE']}",
                    f"--config-setting=cmake.build-type={build_type}",
                ]
                + [
                    o.replace("-D", "--config-setting=cmake.define.")
                    for o in cmake_options
                ]
                + [
                    str(IPP_SOURCE_DIR),
                ]
            )

        # Remove unnecessary files for building against ITK
        if cleanup:
            bp = Path(build_path)
            for p in bp.rglob("*"):
                if p.is_file() and p.suffix in [".cpp", ".xml", ".obj", ".o"]:
                    try:
                        p.unlink()
                    except OSError:
                        pass
            _remove_tree(bp / "Wrapping" / "Generators" / "CastXML")


def fixup_wheel(py_envs, filepath, lib_paths: str = ""):
    lib_paths = lib_paths.strip()
    lib_paths = (lib_paths + ";" if lib_paths else "") + "C:/P/IPP/oneTBB-prefix/bin"
    print(f"Library paths for fixup: {lib_paths}")

    py_env = py_envs[0]

    delve_wheel = IPP_SOURCE_DIR / f"venv-{py_env}" / "Scripts" / "delvewheel.exe"
    cmd = [
        str(delve_wheel),
        "repair",
        "--no-mangle-all",
        "--add-path",
        lib_paths,
        "--ignore-in-wheel",
        "-w",
        str(IPP_SOURCE_DIR / "dist"),
        str(filepath),
    ]
    print(f"Running {' '.join(cmd)} in {Path.cwd()}")
    check_call(cmd)


def fixup_wheels(py_envs, lib_paths: str = ""):
    # TBB library fix-up
    tbb_wheel = "itk_core"
    for wheel in (IPP_SOURCE_DIR / "dist").glob(f"{tbb_wheel}*.whl"):
        fixup_wheel(py_envs, str(wheel), lib_paths)


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
    check_call([python_executable, str(IPP_SOURCE_DIR / "docs" / "code" / "test.py")])
    print("Documentation tests passed.")


def build_wheels(
    py_envs=DEFAULT_PY_ENVS,
    cleanup=False,
    wheel_names=None,
    cmake_options=None,
):
    if cmake_options is None:
        cmake_options = []

    for py_env in py_envs:
        prepare_build_env(py_env)

    build_type = "Release"
    use_tbb: str = "ON"
    with push_dir(directory=IPP_SUPERBUILD_BINARY_DIR, make_directory=True):
        cmake_executable = "cmake.exe"
        tools_venv = IPP_SOURCE_DIR / ("venv-" + py_envs[0])
        ninja_executable = _which("ninja.exe")
        if ninja_executable is None:
            pip_install(tools_venv, "ninja")
            ninja_executable = tools_venv / "Scripts" / "ninja.exe"

        # -----------------------------------------------------------------------
        # Build required components (optional local ITK source, TBB builds) used to populate the archive cache
        cmd = [
            cmake_executable,
            "-G",
            "Ninja",
            "-DITKPythonPackage_BUILD_PYTHON:BOOL=OFF",
            f"-DITKPythonPackage_USE_TBB:BOOL={use_tbb}",
            f"-DCMAKE_BUILD_TYPE:STRING={build_type}",
            f"-DCMAKE_MAKE_PROGRAM:FILEPATH={ninja_executable}",
            f"-DITK_SOURCE_DIR:PATH={package_env_config['ITK_SOURCE_DIR']}",
            f"-DITK_GIT_TAG:STRING={package_env_config['ITK_GIT_TAG']}",
        ]
        cmd += [
            # TODO: PLATFORM CMAKE ITEMS HERE when python used for mac and linux OSX_DEPLOYMENT_TARGET OSX_ARCHITECTURES
            # TODO: ADD CMAKE_COMPILER_ARGS HERE FOR COMPILER PROPAGATION
        ]
        cmd += [
            "-S",
            str(IPP_SOURCE_DIR),
            "-B",
            str(IPP_SUPERBUILD_BINARY_DIR),
        ]

        check_call(cmd)
        check_call([ninja_executable, "-C", str(IPP_SUPERBUILD_BINARY_DIR)])

    # Compile wheels re-using standalone project and archive cache
    for py_env in py_envs:
        tools_venv = IPP_SOURCE_DIR / ("venv-" + py_env)
        ninja_executable = _which("ninja.exe")  # TODO: REMOVE, NINJA ALREADY AVAILABLE!
        if ninja_executable is None:
            pip_install(tools_venv, "ninja")
        build_wheel(
            py_env,
            build_type,
            cleanup=cleanup,
            wheel_names=wheel_names,
            cmake_options=cmake_options,
        )


def main(wheel_names=None):
    parser = argparse.ArgumentParser(
        description="Driver script to build ITK Python wheels."
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
        cleanup=args.cleanup,
        py_envs=args.py_envs,
        wheel_names=wheel_names,
        cmake_options=args.cmake_options,
    )

    # append the oneTBB-prefix\\bin directory for fixing wheels built with local oneTBB
    search_lib_paths = [s for s in args.lib_paths.rstrip(";") if s]
    search_lib_paths.append(IPP_SOURCE_DIR / "oneTBB-prefix" / "bin")
    search_lib_paths_str: str = ";".join(search_lib_paths)
    fixup_wheels(args.py_envs, search_lib_paths_str)
    for py_env in args.py_envs:
        test_wheels(py_env)


if __name__ == "__main__":
    main()
