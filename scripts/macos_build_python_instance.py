from __future__ import annotations

from pathlib import Path

from build_python_instance_base import BuildPythonInstanceBase
from scripts.macos_venv_utils import create_macos_venvs

from scripts.wheel_builder_utils import echo_check_call


class MacOSBuildPythonInstance(BuildPythonInstanceBase):
    def prepare_build_env(self) -> None:

        # #############################################
        # ### Setup build tools
        self._build_type = "Release"
        self._use_tbb: str = "OFF"
        self._tbb_dir = self.IPP_SOURCE_DIR / "oneTBB-prefix" / "lib" / "cmake" / "TBB"
        self._cmake_executable = "cmake"
        # macOS: Assume venv already exists under IPP_SOURCE_DIR/venvs/<name>
        # Install required tools into each venv
        self.venv_paths()
        self.update_venv_itk_build_configurations()
        self.cmake_compiler_configurations.set(
            "CMAKE_MAKE_PROGRAM:FILEPATH", f"{self.venv_info_dict['ninja_executable']}"
        )

        macosx_target = self.package_env_config.get("MACOSX_DEPLOYMENT_TARGET", "")
        if macosx_target:
            self.cmake_compiler_configurations.set(
                "CMAKE_OSX_DEPLOYMENT_TARGET:STRING", macosx_target
            )
        osx_arch = "arm64" if self.platform_architechture == "arm64" else "x86_64"
        self.cmake_compiler_configurations.set(
            "CMAKE_OSX_ARCHITECTURES:STRING", osx_arch
        )
        self.cmake_itk_source_build_configurations.set(
            "ITK_BINARY_DIR:PATH",
            str(self.IPP_SOURCE_DIR / f"ITK-{self.py_env}-macosx_{osx_arch}"),
        )

    def post_build_fixup(self) -> None:
        # delocate on macOS x86_64 only
        if self.platform_architechture != "arm64":
            self.fixup_wheels()

    def final_import_test(self) -> None:
        self._final_import_test_fn(self.py_env, Path(self.dist_dir))

    def fixup_wheel(self, filepath, lib_paths: str = "") -> None:
        # macOS fix-up with delocate (only needed for x86_64)
        if self.platform_architechture != "arm64":
            delocate_listdeps = (
                self.venv_info_dict["venv_bin_path"] / "delocate-listdeps"
            )
            delocate_wheel = self.venv_info_dict["venv_bin_path"] / "delocate-wheel"
            echo_check_call([str(delocate_listdeps), str(filepath)])
            echo_check_call([str(delocate_wheel), str(filepath)])

    def venv_paths(self) -> None:
        # Create venv related paths
        """Resolve macOS virtualenv tool paths.
        py_env may be a name under IPP_SOURCE_DIR/venvs or an absolute/relative path to a venv.
        """
        venv_dir = Path(self.py_env)
        if not venv_dir.exists():
            venv_root_dir: Path = self.IPP_SOURCE_DIR / "venvs"
            _venvs_dir_list = create_macos_venvs(self.py_env, venv_root_dir)
            if len(_venvs_dir_list) != 1:
                raise ValueError(
                    f"Expected exactly one venv for {self.py_env}, found {_venvs_dir_list}"
                )
            venv_dir = _venvs_dir_list[0]
            local_pip_executable = venv_dir / "bin" / "pip3"
            echo_check_call([local_pip_executable, "install", "--upgrade", "pip"])
            echo_check_call(
                [
                    local_pip_executable,
                    "install",
                    "--upgrade",
                    "build",
                    "ninja",
                    "numpy",
                    "scikit-build-core",
                    #  os-specific tools below
                    "delocate",
                ]
            )
            # Install dependencies
            echo_check_call(
                [
                    local_pip_executable,
                    "install",
                    "--upgrade",
                    "-r",
                    str(self.IPP_SOURCE_DIR / "requirements-dev.txt"),
                ]
            )
            self._pip_uninstall_itk_wildcard(local_pip_executable)
        (
            python_executable,
            python_include_dir,
            python_library,
            pip_executable,
            ninja_executable,
            venv_bin_path,
            venv_base_dir,
        ) = self.find_unix_exectable_paths(venv_dir)
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
        # macOS defaults: discover virtualenvs under project 'venvs' folder
        def _discover_mac_venvs() -> list[str]:
            venvs_dir = self.IPP_SOURCE_DIR / "venvs"
            if not venvs_dir.exists():
                return []
            names = [p.name for p in venvs_dir.iterdir() if p.is_dir()]
            # Sort for stable order
            return sorted(names)

        default_py_envs = _discover_mac_venvs()

        return default_py_envs

    def _final_import_test_fn(self, py_env, param):
        pass
