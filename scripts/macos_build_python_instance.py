from __future__ import annotations

import copy
from os import environ
from pathlib import Path

from build_python_instance_base import BuildPythonInstanceBase
from macos_venv_utils import create_macos_venvs

from wheel_builder_utils import _remove_tree


class MacOSBuildPythonInstance(BuildPythonInstanceBase):

    def clone(self):
        # Pattern for generating a deep copy of the current object state as a new build instance
        cls = self.__class__
        new = cls.__new__(cls)
        new.__dict__ = copy.deepcopy(self.__dict__)
        return new

    def get_pixi_environment_name(self):
        # The pixi environment name is the same as the manylinux version
        # and is related to the environment setups defined in pixi.toml
        # in the root of this git directory that contains these scripts.
        return "macos"

    def prepare_build_env(self) -> None:
        # #############################################
        # ### Setup build tools
        self._build_type = "Release"
        self._use_tbb: str = "OFF"
        self._tbb_dir = (
            self.package_env_config["IPP_SOURCE_DIR"]
            / "oneTBB-prefix"
            / "lib"
            / "cmake"
            / "TBB"
        )
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
        osx_arch = "arm64" if self.package_env_config["ARCH"] == "arm64" else "x86_64"
        self.cmake_compiler_configurations.set(
            "CMAKE_OSX_ARCHITECTURES:STRING", osx_arch
        )
        self.cmake_itk_source_build_configurations.set(
            "ITK_BINARY_DIR:PATH",
            str(
                self.package_env_config["IPP_SOURCE_DIR"]
                / f"ITK-{self.py_env}-macosx_{osx_arch}"
            ),
        )

    def post_build_fixup(self) -> None:
        # delocate on macOS x86_64 only
        if self.package_env_config["ARCH"] != "arm64":
            self.fixup_wheels()

    def post_build_cleanup(self) -> None:
        """Clean macOS build artifacts (leave dist/ intact).

        Modeled after the manylinux cleanup, adapted to macOS naming:
        - remove oneTBB-prefix (symlink or dir)
        - remove ITKPythonPackage/, tools/, _skbuild/, build/
        - remove top-level *.egg-info
        - remove ITK-*-macosx_<arch>/
        - remove ITKPythonBuilds-macosx*.tar.zst
        - remove any module prereq clones from ITK_MODULE_PREQ
        """
        base = Path(self.package_env_config["IPP_SOURCE_DIR"])

        def rm(p: Path):
            try:
                _remove_tree(p)
            except Exception:
                pass

        # oneTBB-prefix
        tbb = base / "oneTBB-prefix"
        try:
            if tbb.is_symlink() or tbb.is_file():
                tbb.unlink(missing_ok=True)  # type: ignore[arg-type]
            elif tbb.exists():
                rm(tbb)
        except Exception:
            pass

        # Common build dirs
        for rel in ("ITKPythonPackage", "tools", "_skbuild", "build"):
            rm(base / rel)

        # egg-info entries
        for p in base.glob("*.egg-info"):
            rm(p)

        # ITK build tree
        osx_arch = "arm64" if self.package_env_config["ARCH"] == "arm64" else "x86_64"
        for p in base.glob(f"ITK-*-macosx_{osx_arch}"):
            rm(p)

        # Tarballs
        for p in base.glob("ITKPythonBuilds-macosx*.tar.zst"):
            rm(p)

        # Module prerequisites
        itk_preq = self.package_env_config.get("ITK_MODULE_PREQ") or environ.get(
            "ITK_MODULE_PREQ", ""
        )
        if itk_preq:
            for entry in itk_preq.split(":"):
                entry = entry.strip()
                if not entry:
                    continue
                try:
                    module_name = entry.split("@", 1)[0].split("/", 1)[1]
                except Exception:
                    continue
                rm(base / module_name)

    def final_import_test(self) -> None:
        self._final_import_test_fn(self.py_env, Path(self.dist_dir))

    def fixup_wheel(self, filepath, lib_paths: str = "") -> None:
        self.remove_apple_double_files()
        # macOS fix-up with delocate (only needed for x86_64)
        if self.package_env_config["ARCH"] != "arm64":
            delocate_listdeps = (
                self.venv_info_dict["venv_bin_path"] / "delocate-listdeps"
            )
            delocate_wheel = self.venv_info_dict["venv_bin_path"] / "delocate-wheel"
            self.echo_check_call([str(delocate_listdeps), str(filepath)])
            self.echo_check_call([str(delocate_wheel), str(filepath)])

    def build_tarball(self):
        self.create_posix_tarball()

    def remove_apple_double_files(self):
        try:
            # Optional: clean AppleDouble files if tool is available
            self.echo_check_call(
                ["dot_clean", str(self.package_env_config["IPP_SOURCE_DIR"].name)]
            )
        except Exception:
            # dot_clean may not be available; continue without it
            pass

    def venv_paths(self) -> None:
        """Resolve virtualenv tool paths.
        py_env may be a name under IPP_SOURCE_DIR/venvs or an absolute/relative path to a venv.
        """
        # First determine if py_env is the full path to a python environment
        _command_line_pip_executable = Path(self.py_env) / "bin" / "pip3"
        if _command_line_pip_executable.exists():
            venv_dir = Path(self.py_env)
            local_pip_executable = _command_line_pip_executable
        else:
            venv_root_dir: Path = self.package_env_config["IPP_SOURCE_DIR"] / "venvs"
            _venvs_dir_list = create_macos_venvs(self.py_env, venv_root_dir)
            if len(_venvs_dir_list) != 1:
                raise ValueError(
                    f"Expected exactly one venv for {self.py_env}, found {_venvs_dir_list}"
                )
            venv_dir = _venvs_dir_list[0]
            local_pip_executable = venv_dir / "bin" / "pip3"

        self.echo_check_call([local_pip_executable, "install", "--upgrade", "pip"])
        self.echo_check_call(
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
        self.echo_check_call(
            [
                local_pip_executable,
                "install",
                "--upgrade",
                "-r",
                str(self.package_env_config["IPP_SOURCE_DIR"] / "requirements-dev.txt"),
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
        names = []

        # Discover virtualenvs under project 'venvs' folder
        def _discover_ipp_venvs() -> list[str]:
            venvs_dir = self.package_env_config["IPP_SOURCE_DIR"] / "venvs"
            if not venvs_dir.exists():
                return []
            names.extend([p.name for p in venvs_dir.iterdir() if p.is_dir()])
            # Sort for stable order
            return sorted(names)

        default_py_envs = _discover_ipp_venvs()

        return default_py_envs

    def _final_import_test_fn(self, py_env, param):
        pass
