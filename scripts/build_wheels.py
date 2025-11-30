#!/usr/bin/env python

import argparse
import sys
import shutil
import subprocess
from pathlib import Path
from os import environ, pathsep

from dotenv import dotenv_values

from wheel_builder_utils import (
    _which,
    _remove_tree,
    echo_check_call,
    detect_platform,
    push_dir,
    push_env,
)


SCRIPT_DIR = Path(__file__).parent
# TODO: Hard-coded module must be 1 direectory above checkedout ITKPythonPackage
# MODULE_EXAMPLESROOT_DIR: Path = SCRIPT_DIR.parent.parent.resolve()

IPP_SOURCE_DIR = SCRIPT_DIR.parent.resolve()
IPP_SUPERBUILD_BINARY_DIR = IPP_SOURCE_DIR / "ITK-source"
package_env_config = dotenv_values(IPP_SOURCE_DIR / "build" / "package.env")
ITK_SOURCE_DIR = package_env_config["ITK_SOURCE_DIR"]

print(f"SCRIPT_DIR: {SCRIPT_DIR}")
print(f"ROOT_DIR: {IPP_SOURCE_DIR}")
print(f"ITK_SOURCE: {IPP_SUPERBUILD_BINARY_DIR}")

sys.path.insert(0, str(SCRIPT_DIR / "internal"))

OS_NAME: str = "UNKNOWN"
ARCH: str = "UNKNOWN"


def venv_paths(py_env: str):
    if OS_NAME == "windows":

        # Create venv
        venv_executable = f"C:/Python{py_env}/Scripts/virtualenv.exe"
        venv_dir = Path(ITK_SOURCE_DIR) / f"venv-{py_env}"
        echo_check_call([venv_executable, str(venv_dir)])

        python_executable = venv_dir / "Scripts" / "python.exe"
        python_include_dir = f"C:/Python{py_env}/include"

        # XXX It should be possible to query skbuild for the library dir associated
        #     with a given interpreter.
        xy_ver = py_env.split("-")[0]

        if int(py_env.split("-")[0][1:]) >= 11:
            # Stable ABI
            python_library = f"C:/Python{py_env}/libs/python3.lib"
        else:
            python_library = f"C:/Python{py_env}/libs/python{xy_ver}.lib"

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

    elif OS_NAME == "darwin":
        """Resolve macOS virtualenv tool paths.
        py_env may be a name under IPP_SOURCE_DIR/venvs or an absolute/relative path to a venv.
        """
        venv_dir = Path(py_env)
        if not venv_dir.exists():
            venv_dir = IPP_SOURCE_DIR / "venvs" / py_env
        # Common macOS layout
        return find_unix_exectable_paths(venv_dir)
    elif OS_NAME == "linux":
        """Resolve Linux manylinux Python tool paths.

        py_env is expected to be a directory name under /opt/python (e.g., cp311-cp311),
        or an absolute path to the specific Python root.
        """
        venv_dir = Path(py_env)
        if not venv_dir.exists():
            venv_dir = Path("/opt/python") / py_env
        return find_unix_exectable_paths(venv_dir)
    else:
        raise ValueError(f"Unknown platform {OS_NAME}")


def find_unix_exectable_paths(venv_dir: Path) -> tuple[str, str, str, str, str, str]:
    python_executable = venv_dir / "bin" / "python3"
    if not python_executable.exists():
        raise FileNotFoundError(f"Python executable not found: {python_executable}")
    pip = venv_dir / "bin" / "pip3"
    if not pip.exists():
        raise FileNotFoundError(f"pip executable not found: {pip}")

    # Prefer venv's ninja, else fall back to PATH
    ninja_executable_path: Path = venv_dir / "bin" / "ninja"
    ninja_executable: Path = find_unix_ninja_executable(ninja_executable_path)
    if not ninja_executable.exists():
        raise FileNotFoundError(f"Ninja executable not found: {ninja_executable}")
    # Compute Python include dir using sysconfig for the given interpreter
    try:
        python_include_dir = (
            subprocess.check_output(
                [
                    str(python_executable),
                    "-c",
                    "import sysconfig; print(sysconfig.get_paths()['include'])",
                ],
                text=True,
            ).strip()
            or ""
        )
    except Exception as e:
        print(f"Failed to compute Python include dir: {e}\n defaulting to empty")
        python_include_dir = ""

    # modern CMake with Python3 can infer the library from executable; leave empty
    python_library = ""

    # Update PATH
    path = venv_dir / "bin"
    return (
        str(python_executable),
        python_include_dir,
        python_library,
        str(pip),
        str(ninja_executable),
        str(path),
    )


def find_unix_ninja_executable(ninja_executable_path) -> Path | None:
    ninja_executable = (
        str(ninja_executable_path)
        if ninja_executable_path.exists()
        else (shutil.which("ninja") or str(ninja_executable_path))
    )
    return Path(ninja_executable)


def discover_python_venvs(
    platform_os_name: str, platform_architechure: str
) -> list[str]:
    # Conditionally import Windows helpers; define macOS helpers inline
    if platform_os_name == "windows":
        default_py_envs = [
            f"39-{platform_architechure}",
            f"310-{platform_architechure}",
            f"311-{platform_architechure}",
        ]
    elif platform_os_name == "darwin":
        # macOS defaults: discover virtualenvs under project 'venvs' folder
        def _discover_mac_venvs() -> list[str]:
            venvs_dir = IPP_SOURCE_DIR / "venvs"
            if not venvs_dir.exists():
                return []
            names = [p.name for p in venvs_dir.iterdir() if p.is_dir()]
            # Sort for stable order
            return sorted(names)

        default_py_envs = _discover_mac_venvs()

    elif platform_os_name == "linux":
        # Discover available manylinux CPython installs under /opt/python
        def _discover_linux_pythons() -> list[str]:
            base = Path("/opt/python")
            if not base.exists():
                return []
            names = [
                p.name for p in base.iterdir() if p.is_dir() and p.name.startswith("cp")
            ]
            names.sort()
            return names

        default_py_envs = _discover_linux_pythons()

    else:
        raise ValueError(f"Unknown platform {platform_os_name}")
    return default_py_envs


def pip_install(python_dir, package, upgrade=True):
    # for OS_NAME == "darwin"  and OS_NAME == "linux"
    pip3_executable = Path(python_dir) / "bin" / "pip3"
    # Handle Windows and macOS venv layouts
    if OS_NAME == "windows":
        pip3_executable = Path(python_dir) / "Scripts" / "pip.exe"
    print(f"Installing {package} using {pip3_executable}")
    args = [pip3_executable, "install"]
    if upgrade:
        args.append("--upgrade")
    args.append(package)
    echo_check_call(args)


def prepare_build_env(python_version):
    if OS_NAME == "windows":
        python_dir = Path(f"C:/Python{python_version}")
        if not python_dir.exists():
            raise FileNotFoundError(
                f"Aborting. python_dir [{python_dir}] does not exist."
            )

        virtualenv_exe = python_dir / "Scripts" / "virtualenv.exe"
        venv_dir = IPP_SOURCE_DIR / f"venv-{python_version}"
        if not venv_dir.exists():
            print(f"Creating python virtual environment: {venv_dir}")
            echo_check_call([str(virtualenv_exe), str(venv_dir)])
        pip_install(venv_dir, "scikit-build-core")
        pip_install(venv_dir, "ninja")
        pip_install(venv_dir, "delvewheel")
    elif OS_NAME == "darwin":
        # macOS: Assume venv already exists under IPP_SOURCE_DIR/venvs/<name>
        # Install required tools into each venv
        (
            python_executable,
            _python_include_dir,
            _python_library,
            pip,
            _ninja_executable,
            _path,
        ) = venv_paths(python_version)
        echo_check_call([pip, "install", "--upgrade", "pip"])
        echo_check_call(
            [
                pip,
                "install",
                "--upgrade",
                "scikit-build-core",
                "ninja",
                "delocate",
                "build",
            ]
        )
    elif OS_NAME == "linux":
        # manylinux: the interpreter is provided; ensure basic tools are available
        (
            python_executable,
            _python_include_dir,
            _python_library,
            pip,
            _ninja_executable,
            _path,
        ) = venv_paths(python_version)
        echo_check_call([pip, "install", "--upgrade", "pip"])
        echo_check_call(
            [
                pip,
                "install",
                "--upgrade",
                "build",
                "ninja",
                "auditwheel",
                "wheel",
                "scikit-build-core",
            ]
        )
    else:
        raise ValueError(f"Unknown platform {OS_NAME}")


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
            # Respect macOS deployment target and architecture if present
        ]
        if OS_NAME == "darwin":
            use_tbb: str = "OFF"
            macosx_target = package_env_config.get("MACOSX_DEPLOYMENT_TARGET", "")
            if macosx_target:
                cmd.append(f"-DCMAKE_OSX_DEPLOYMENT_TARGET:STRING={macosx_target}")
            osx_arch = "arm64" if ARCH == "arm64" else "x86_64"
            cmd.append(f"-DCMAKE_OSX_ARCHITECTURES:STRING={osx_arch}")
        elif OS_NAME == "linux":
            use_tbb: str = "ON"
            # Match flags used in manylinux shell script
            if ARCH == "x64":
                target_triple = "x86_64-linux-gnu"
            elif ARCH in ("aarch64", "arm64"):
                target_triple = "aarch64-linux-gnu"
            elif ARCH == "x86":
                target_triple = "i686-linux-gnu"
            else:
                target_triple = f"{ARCH}-linux-gnu"
            cmd.append(f"-DCMAKE_CXX_COMPILER_TARGET:STRING={target_triple}")
            cmd.append('-DCMAKE_CXX_FLAGS:STRING="-O3 -DNDEBUG"')
            cmd.append('-DCMAKE_C_FLAGS:STRING="-O3 -DNDEBUG"')
        elif OS_NAME == "windows":
            use_tbb: str = "ON"
        else:
            raise ValueError(f"Unknown platform {OS_NAME}")

        # Set cmake flags for the compiler if CC or CXX are specified
        cxx_compiler: str = package_env_config.get("CXX", "")
        if cxx_compiler != "":
            cmd.append(f"-DCMAKE_CXX_COMPILER:STRING={cxx_compiler}")

        c_compiler: str = package_env_config.get("CC", "")
        if c_compiler != "":
            cmd.append(f"-DCMAKE_C_COMPILER:STRING={c_compiler}")

        if package_env_config.get("USE_CCACHE", "OFF") == "ON":
            ccache_exe: Path = _which("ccache")
            cmd.append(f"-DCMAKE_C_COMPILER_LAUNCHER:FILEPATH={ccache_exe}")
            cmd.append(f"-DCMAKE_CXX_COMPILER_LAUNCHER:FILEPATH={ccache_exe}")

        # Python settings
        cmd.append("-DSKBUILD:BOOL=ON")
        cmd.append(f"-DPython3_EXECUTABLE:FILEPATH={python_executable}")
        if python_include_dir:
            cmd.append(f"-DPython3_INCLUDE_DIR:PATH={python_include_dir}")
            cmd.append(f"-DPython3_INCLUDE_DIRS:PATH={python_include_dir}")
        if python_library:
            cmd.append(f"-DPython3_LIBRARY:FILEPATH={python_library}")
            cmd.append(f"-DPython3_SABI_LIBRARY:FILEPATH={python_library}")

        # ITK wrapping options
        cmd += [
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
        echo_check_call(cmd)
        echo_check_call([ninja_executable, "-C", build_path])


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
        echo_check_call(
            [
                pip,
                "install",
                "--upgrade",
                "-r",
                str(IPP_SOURCE_DIR / "requirements-dev.txt"),
            ]
        )

        source_path = f"{package_env_config['ITK_SOURCE_DIR']}"
        # Build path naming per platform
        if OS_NAME == "windows":
            build_path = IPP_SOURCE_DIR / f"ITK-win_{python_version}"
        elif OS_NAME == "darwin":
            osx_arch = "arm64" if ARCH == "arm64" else "x86_64"
            build_path = IPP_SOURCE_DIR / f"ITK-{python_version}-macosx_{osx_arch}"
        elif OS_NAME == "linux":
            # TODO: do not use environ here, get from package_env instead
            manylinux_ver = environ.get("MANYLINUX_VERSION", "")
            build_path = (
                IPP_SOURCE_DIR / f"ITK-{python_version}-manylinux{manylinux_ver}_{ARCH}"
            )
        else:
            raise ValueError(f"Unknown platform {OS_NAME}")
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
            echo_check_call(
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
            cmd = [
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
                f"--config-setting=cmake.define.ITKPythonPackage_USE_TBB:BOOL={use_tbb}",
                "--config-setting=cmake.define.ITKPythonPackage_ITK_BINARY_REUSE:BOOL=ON",
                f"--config-setting=cmake.define.ITKPythonPackage_WHEEL_NAME:STRING={wheel_name}",
                f"--config-setting=cmake.define.Python3_EXECUTABLE:FILEPATH={python_executable}",
                f"--config-setting=cmake.define.DOXYGEN_EXECUTABLE:FILEPATH={package_env_config['DOXYGEN_EXECUTABLE']}",
                f"--config-setting=cmake.build-type={build_type}",
            ]
            if OS_NAME == "darwin":
                macosx_target = package_env_config.get("MACOSX_DEPLOYMENT_TARGET", "")
                if macosx_target:
                    cmd.append(
                        f"--config-setting=cmake.define.CMAKE_OSX_DEPLOYMENT_TARGET:STRING={macosx_target}"
                    )
                osx_arch = "arm64" if ARCH == "arm64" else "x86_64"
                cmd.append(
                    f"--config-setting=cmake.define.CMAKE_OSX_ARCHITECTURES:STRING={osx_arch}"
                )
            elif OS_NAME == "linux":
                if ARCH == "x64":
                    target_triple = "x86_64-linux-gnu"
                elif ARCH in ("aarch64", "arm64"):
                    target_triple = "aarch64-linux-gnu"
                elif ARCH == "x86":
                    target_triple = "i686-linux-gnu"
                else:
                    target_triple = f"{ARCH}-linux-gnu"
                cmd.append(
                    f"--config-setting=cmake.define.CMAKE_CXX_COMPILER_TARGET:STRING={target_triple}"
                )
                cmd.append(
                    "--config-setting=cmake.define.CMAKE_CXX_FLAGS:STRING=-O3 -DNDEBUG"
                )
                cmd.append(
                    "--config-setting=cmake.define.CMAKE_C_FLAGS:STRING=-O3 -DNDEBUG"
                )
            if python_include_dir:
                cmd.append(
                    f"--config-setting=cmake.define.Python3_INCLUDE_DIR:PATH={python_include_dir}"
                )
                cmd.append(
                    f"--config-setting=cmake.define.Python3_INCLUDE_DIRS:PATH={python_include_dir}"
                )
            if python_library:
                cmd.append(
                    f"--config-setting=cmake.define.Python3_LIBRARY:FILEPATH={python_library}"
                )
            cmd += [
                o.replace("-D", "--config-setting=cmake.define.") for o in cmake_options
            ]
            cmd += [str(IPP_SOURCE_DIR)]
            echo_check_call(cmd)

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


def fixup_wheel(py_env, filepath, lib_paths: str = ""):
    if OS_NAME == "windows":
        lib_paths = lib_paths.strip()
        lib_paths = (
            lib_paths + ";" if lib_paths else ""
        ) + "C:/P/IPP/oneTBB-prefix/bin"
        print(f"Library paths for fixup: {lib_paths}")

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
        echo_check_call(cmd)
    elif OS_NAME == "darwin":
        # macOS fix-up with delocate (only needed for x86_64)
        if ARCH != "arm64":
            (
                _py,
                _inc,
                _lib,
                pip,
                _ninja,
                _path,
            ) = venv_paths(py_env)
            delocate_listdeps = Path(_path) / "delocate-listdeps"
            delocate_wheel = Path(_path) / "delocate-wheel"
            echo_check_call([str(delocate_listdeps), str(filepath)])
            echo_check_call([str(delocate_wheel), str(filepath)])
    elif OS_NAME == "linux":
        # Use auditwheel to repair wheels and set manylinux tags
        (
            python_executable,
            _inc,
            _lib,
            _pip,
            _ninja,
            _path,
        ) = venv_paths(py_env)
        plat = None
        manylinux_ver = environ.get("MANYLINUX_VERSION", "")
        if ARCH == "x64" and manylinux_ver:
            plat = f"manylinux{manylinux_ver}_x86_64"
        cmd = [python_executable, "-m", "auditwheel", "repair"]
        if plat:
            cmd += ["--plat", plat]
        cmd += [str(filepath), "-w", str(IPP_SOURCE_DIR / "dist")]
        # Provide LD_LIBRARY_PATH for oneTBB and common system paths
        extra_lib = str(IPP_SOURCE_DIR / "oneTBB-prefix" / "lib")
        env = dict(environ)
        env["LD_LIBRARY_PATH"] = ":".join(
            [
                env.get("LD_LIBRARY_PATH", ""),
                extra_lib,
                "/usr/lib64",
                "/usr/lib",
            ]
        )
        echo_check_call(cmd, env=env)
    else:
        raise ValueError(f"Unknown platform {OS_NAME}")


def fixup_wheels(py_envs, lib_paths: str = ""):
    # TBB library fix-up (applies to itk_core wheel)
    tbb_wheel = "itk_core"
    for wheel in (IPP_SOURCE_DIR / "dist").glob(f"{tbb_wheel}*.whl"):
        fixup_wheel(py_envs, str(wheel), lib_paths)


def final_wheel_import_test(python_env):
    (
        python_executable,
        _python_include_dir,
        _python_library,
        pip,
        _ninja_executable,
        _path,
    ) = venv_paths(python_env)
    echo_check_call([pip, "install", "numpy"])
    echo_check_call([pip, "install", "--upgrade", "pip"])
    echo_check_call(
        [pip, "install", "itk", "--no-cache-dir", "--no-index", "-f", "dist"]
    )
    print("Wheel successfully installed.")
    # Basic imports
    echo_check_call([python_executable, "-c", "import itk;"])
    echo_check_call(
        [python_executable, "-c", "import itk; image = itk.Image[itk.UC, 2].New()"]
    )
    echo_check_call(
        [
            python_executable,
            "-c",
            "import itkConfig; itkConfig.LazyLoading=False; import itk;",
        ]
    )
    # Full doc tests
    echo_check_call(
        [python_executable, str(IPP_SOURCE_DIR / "docs" / "code" / "test.py")]
    )
    print("Documentation tests passed.")


def build_wheels(
    py_env,
    cleanup=False,
    wheel_names=None,
    cmake_options=None,
):
    if cmake_options is None:
        cmake_options = []

    build_type = "Release"
    use_tbb: str = "ON"
    with push_dir(directory=IPP_SUPERBUILD_BINARY_DIR, make_directory=True):
        cmake_executable = "cmake.exe" if OS_NAME == "windows" else "cmake"
        if OS_NAME == "windows":
            tools_venv = IPP_SOURCE_DIR / ("venv-" + py_env)
            ninja_executable = _which("ninja.exe")
            if ninja_executable is None:
                pip_install(tools_venv, "ninja")
                ninja_executable = tools_venv / "Scripts" / "ninja.exe"
        elif OS_NAME == "darwin":
            # Use ninja from PATH or ensure it's available in first venv
            ninja_executable = shutil.which("ninja")
            if not ninja_executable:
                (
                    _py,
                    _inc,
                    _lib,
                    pip,
                    _ninja,
                    _path,
                ) = venv_paths(py_env)
                echo_check_call([pip, "install", "ninja"])
                ninja_executable = shutil.which("ninja") or str(Path(_path) / "ninja")
        elif OS_NAME == "linux":
            # Prefer system ninja, else ensure it's available in the first Python env
            ninja_executable = shutil.which("ninja")
            if not ninja_executable and py_env:
                (
                    _py,
                    _inc,
                    _lib,
                    pip,
                    _ninja,
                    _path,
                ) = venv_paths(py_env)
                echo_check_call([pip, "install", "ninja"])
                ninja_executable = shutil.which("ninja") or str(Path(_path) / "ninja")
        else:
            raise ValueError(f"Unknown platform {OS_NAME}")

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
        if OS_NAME == "darwin":
            macosx_target = package_env_config.get("MACOSX_DEPLOYMENT_TARGET", "")
            if macosx_target:
                cmd.append(f"-DCMAKE_OSX_DEPLOYMENT_TARGET:STRING={macosx_target}")
            osx_arch = "arm64" if ARCH == "arm64" else "x86_64"
            cmd.append(f"-DCMAKE_OSX_ARCHITECTURES:STRING={osx_arch}")
        cmd += [
            "-S",
            str(IPP_SOURCE_DIR),
            "-B",
            str(IPP_SUPERBUILD_BINARY_DIR),
        ]

        echo_check_call(cmd)
        echo_check_call([ninja_executable, "-C", str(IPP_SUPERBUILD_BINARY_DIR)])

    # Compile wheels re-using standalone project and archive cache
    if OS_NAME == "windows":
        tools_venv = IPP_SOURCE_DIR / ("venv-" + py_env)
        ninja_executable = _which("ninja.exe")  # ensure availability
        if ninja_executable is None:
            pip_install(tools_venv, "ninja")
    elif OS_NAME == "darwin":
        # Ensure ninja present in mac venvs
        (
            _py,
            _inc,
            _lib,
            pip,
            _ninja,
            _path,
        ) = venv_paths(py_env)
        echo_check_call([pip, "install", "ninja"])
    elif OS_NAME == "linux":
        # TODO
        pass
    else:
        raise ValueError(f"Unknown platform {OS_NAME}")

    build_wheel(
        py_env,
        build_type,
        cleanup=cleanup,
        wheel_names=wheel_names,
        cmake_options=cmake_options,
    )


def post_build_wheel_fixup(
    platform_name: str, platform_architechture: str, extra_lib_paths: list[str], py_env
):
    # Wheel fix-up
    if platform_name == "windows":
        # append the oneTBB-prefix\\bin directory for fixing wheels built with local oneTBB
        search_lib_paths = (
            [s for s in str(extra_lib_paths[0]).rstrip(";") if s]
            if extra_lib_paths
            else []
        )
        search_lib_paths.append(str(IPP_SOURCE_DIR / "oneTBB-prefix" / "bin"))
        search_lib_paths_str: str = ";".join(map(str, search_lib_paths))
        fixup_wheels(py_env, search_lib_paths_str)
    elif platform_name == "darwin":
        # delocate on macOS x86_64 only
        if platform_architechture != "arm64":
            fixup_wheels(py_env)
    elif platform_name == "linux":
        # Repair all produced wheels with auditwheel and retag meta-wheel
        for whl in (IPP_SOURCE_DIR / "dist").glob("*.whl"):
            fixup_wheel(py_env, str(whl))
        # Special handling for the itk meta wheel to adjust tag
        (python_executable, *_rest) = venv_paths(py_env)
        manylinux_ver = environ.get("MANYLINUX_VERSION", "")
        if manylinux_ver:
            for whl in list((IPP_SOURCE_DIR / "dist").glob("itk-*linux_*.whl")) + list(
                (IPP_SOURCE_DIR / "dist").glob("itk_*linux_*.whl")
            ):
                # Unpack, edit WHEEL tag, repack
                metawheel_dir = IPP_SOURCE_DIR / "metawheel"
                metawheel_dist = IPP_SOURCE_DIR / "metawheel-dist"
                echo_check_call(
                    [
                        python_executable,
                        "-m",
                        "wheel",
                        "unpack",
                        "--dest",
                        str(metawheel_dir),
                        str(whl),
                    ]
                )
                # Find unpacked dir
                unpacked_dirs = list(metawheel_dir.glob("itk-*/itk*.dist-info/WHEEL"))
                for wheel_file in unpacked_dirs:
                    content = wheel_file.read_text(encoding="utf-8").splitlines()
                    base = whl.name.replace("linux", f"manylinux{manylinux_ver}")
                    tag = Path(base).stem
                    new = []
                    for line in content:
                        if line.startswith("Tag: "):
                            new.append(f"Tag: {tag}")
                        else:
                            new.append(line)
                    wheel_file.write_text("\n".join(new) + "\n", encoding="utf-8")
                echo_check_call(
                    [
                        python_executable,
                        "-m",
                        "wheel",
                        "pack",
                        "--dest",
                        str(metawheel_dist),
                        str(metawheel_dir / "itk-*"),
                    ]
                )
                # Move and clean
                for new_whl in metawheel_dist.glob("*.whl"):
                    shutil.move(
                        str(new_whl), str((IPP_SOURCE_DIR / "dist") / new_whl.name)
                    )
                # Remove old and temp
                try:
                    whl.unlink()
                except OSError:
                    pass
                _remove_tree(metawheel_dir)
                _remove_tree(metawheel_dist)
    else:
        raise ValueError(f"Unknown platform {platform_name}")


def build_one_python_instance(
    py_env,
    wheel_names,
    platform_name: str,
    platform_architechture: str,
    cleanup: bool,
    cmake_options: list[str],
    windows_extra_lib_paths: list[str],
):
    prepare_build_env(py_env)

    build_wheels(
        py_env=py_env,
        cleanup=cleanup,
        wheel_names=wheel_names,
        cmake_options=cmake_options,
    )

    post_build_wheel_fixup(
        platform_name, platform_architechture, windows_extra_lib_paths, py_env
    )

    final_wheel_import_test(py_env)


def main(wheel_names=None) -> None:

    global OS_NAME, ARCH
    # Platform detection
    OS_NAME, ARCH = detect_platform()

    parser = argparse.ArgumentParser(
        description="Driver script to build ITK Python wheels."
    )
    parser.add_argument(
        "--py-envs",
        nargs="+",
        default=discover_python_venvs(OS_NAME, ARCH),
        help=(
            "Windows: Python versions like '39-x64'. macOS: names or paths of venvs under 'venvs/'."
        ),
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
        help=(
            "Windows only: semicolon-delimited library directories for delvewheel to include in module wheel"
        ),
    )
    parser.add_argument(
        "cmake_options",
        nargs="*",
        help="Extra options to pass to CMake, e.g. -DBUILD_SHARED_LIBS:BOOL=OFF",
    )
    args = parser.parse_args()

    for py_env in args.py_envs:

        build_one_python_instance(
            py_env,
            wheel_names,
            OS_NAME,
            ARCH,
            args.cleanup,
            args.cmake_options,
            args.lib_paths,
        )


if __name__ == "__main__":
    main()
