from __future__ import annotations

from pathlib import Path

from build_python_instance_base import BuildPythonInstanceBase

from scripts.wheel_builder_utils import echo_check_call, _which


class WindowsBuildPythonInstance(BuildPythonInstanceBase):
    def prepare_build_env(self) -> None:
        # Windows
        # Install required tools into each venv
        (
            python_executable,
            _python_include_dir,
            _python_library,
            pip,
            self._ninja_executable,
            _path,
            venv_dir,
        ) = self.venv_paths()

        # python_version = self.py_env
        # python_dir = Path(f"C:/Python{python_version}")
        # if not python_dir.exists():
        #     raise FileNotFoundError(
        #         f"Aborting. python_dir [{python_dir}] does not exist."
        #     )
        #
        # virtualenv_exe = python_dir / "Scripts" / "virtualenv.exe"
        # venv_dir = self.IPP_SOURCE_DIR / f"venv-{python_version}"
        # if not venv_dir.exists():
        #     print(f"Creating python virtual environment: {venv_dir}")
        #     echo_check_call([str(virtualenv_exe), str(venv_dir)])
        # pip = str(venv_dir / "Scripts" / "pip.exe")
        self._pip_uninstall_itk_wildcard(pip)
        echo_check_call([pip, "install", "--upgrade", "pip"])
        echo_check_call(
            [
                pip,
                "install",
                "--upgrade",
                "build",
                "ninja",
                "numpy",
                "scikit-build-core",
                #  os-specific tools below
                "delvewheel",
                "pkginfo",
            ]
        )

        # #############################################
        # ### Setup build tools
        self._build_type = "Release"
        self._use_tbb: str = "ON"
        self._tbb_dir = self.IPP_SOURCE_DIR / "oneTBB-prefix" / "lib" / "cmake" / "TBB"
        self._cmake_executable = "cmake.exe"
        ninja_executable_path = venv_dir / "Scripts" / "ninja.exe"
        if ninja_executable_path.exists():
            ninja_executable = ninja_executable_path
        else:
            ninja_executable = _which("ninja.exe") or str(ninja_executable_path)
        print(f"NINJA_EXECUTABLE:{ninja_executable}")

    def post_build_fixup(self) -> None:
        # append the oneTBB-prefix\\bin directory for fixing wheels built with local oneTBB
        search_lib_paths = (
            [s for s in str(self.windows_extra_lib_paths[0]).rstrip(";") if s]
            if self.windows_extra_lib_paths
            else []
        )
        search_lib_paths.append(str(self.IPP_SOURCE_DIR / "oneTBB-prefix" / "bin"))
        search_lib_paths_str: str = ";".join(map(str, search_lib_paths))
        self.fixup_wheels(search_lib_paths_str)

    def final_import_test(self) -> None:
        self._final_import_test_fn(self.py_env, Path(self.dist_dir))

    def fixup_wheel(self, filepath, lib_paths: str = "") -> None:
        # Windows fixup_wheel
        lib_paths = lib_paths.strip()
        lib_paths = (
            lib_paths + ";" if lib_paths else ""
        ) + "C:/P/IPP/oneTBB-prefix/bin"
        print(f"Library paths for fixup: {lib_paths}")

        delve_wheel = (
            self.IPP_SOURCE_DIR / f"venv-{self.py_env}" / "Scripts" / "delvewheel.exe"
        )
        cmd = [
            str(delve_wheel),
            "repair",
            "--no-mangle-all",
            "--add-path",
            lib_paths,
            "--ignore-in-wheel",
            "-w",
            str(self.IPP_SOURCE_DIR / "dist"),
            str(filepath),
        ]
        echo_check_call(cmd)

    def venv_paths(self) -> tuple[str, str, str, str, str, str, Path]:
        # Create venv related paths
        venv_executable = f"C:/Python{self.py_env}/Scripts/virtualenv.exe"
        venv_dir = Path(self.ITK_SOURCE_DIR) / f"venv-{self.py_env}"
        echo_check_call([venv_executable, str(venv_dir)])

        python_executable = venv_dir / "Scripts" / "python.exe"
        python_include_dir = f"C:/Python{self.py_env}/include"

        # XXX It should be possible to query skbuild for the library dir associated
        #     with a given interpreter.
        xy_ver = self.py_env.split("-")[0]

        if int(self.py_env.split("-")[0][1:]) >= 11:
            # Stable ABI
            python_library = f"C:/Python{self.py_env}/libs/python3.lib"
        else:
            python_library = f"C:/Python{self.py_env}/libs/python{xy_ver}.lib"

        pip = venv_dir / "Scripts" / "pip.exe"

        # Update PATH
        path = venv_dir / "Scripts"

        return (
            str(python_executable),
            python_include_dir,
            python_library,
            str(pip),
            self._ninja_executable,
            str(path),
            venv_dir,
        )

    def discover_python_venvs(
        self, platform_os_name: str, platform_architechure: str
    ) -> list[str]:
        default_py_envs = [
            f"39-{platform_architechure}",
            f"310-{platform_architechure}",
            f"311-{platform_architechure}",
        ]
        return default_py_envs

    def _final_import_test_fn(self, py_env, param):
        pass
