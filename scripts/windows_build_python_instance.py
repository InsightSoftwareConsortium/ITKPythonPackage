from __future__ import annotations

from pathlib import Path

from build_python_instance_base import BuildPythonInstanceBase

from scripts.wheel_builder_utils import echo_check_call


class WindowsBuildPythonInstance(BuildPythonInstanceBase):
    def prepare_build_env(self) -> None:
        # Windows
        # Install required tools into each venv
        self.venv_paths()
        self._pip_uninstall_itk_wildcard(self.venv_info_dict["pip_executable"])
        echo_check_call(
            [self.venv_info_dict["pip_executable"], "install", "--upgrade", "pip"]
        )
        echo_check_call(
            [
                self.venv_info_dict["pip_executable"],
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
        # Install dependencies
        echo_check_call(
            [
                self.venv_info_dict["pip_executable"],
                "install",
                "--upgrade",
                "-r",
                str(self.IPP_SOURCE_DIR / "requirements-dev.txt"),
            ]
        )

        # #############################################
        # ### Setup build tools
        self._build_type = "Release"
        self._use_tbb: str = "ON"
        self._tbb_dir = self.IPP_SOURCE_DIR / "oneTBB-prefix" / "lib" / "cmake" / "TBB"
        self._cmake_executable = "cmake.exe"

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

    def venv_paths(self) -> None:
        # Create venv related paths
        venv_executable = f"C:/Python{self.py_env}/Scripts/virtualenv.exe"
        venv_base_dir = Path(self.ITK_SOURCE_DIR) / f"venv-{self.py_env}"
        echo_check_call([venv_executable, str(venv_base_dir)])

        python_executable = venv_base_dir / "Scripts" / "python.exe"
        python_include_dir = f"C:/Python{self.py_env}/include"

        # XXX It should be possible to query skbuild for the library dir associated
        #     with a given interpreter.
        xy_ver = self.py_env.split("-")[0]

        if int(self.py_env.split("-")[0][1:]) >= 11:
            # Stable ABI
            python_library = f"C:/Python{self.py_env}/libs/python3.lib"
        else:
            python_library = f"C:/Python{self.py_env}/libs/python{xy_ver}.lib"

        pip_executable = venv_base_dir / "Scripts" / "pip.exe"

        # Update PATH
        venv_bin_path = venv_base_dir / "Scripts"
        ninja_executable = venv_bin_path / "ninja.exe"

        print(f"NINJA_EXECUTABLE:{ninja_executable}")

        self.venv_info_dict = {
            "python_executable": python_executable,
            "python_include_dir": python_include_dir,
            "python_library": python_library,
            "pip_executable": pip_executable,
            "ninja_executable": ninja_executable,
            "venv_bin_path": venv_bin_path,
            "venv_base_dir": venv_base_dir,
        }

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
