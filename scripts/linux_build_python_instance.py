from __future__ import annotations

import copy
from os import environ
from pathlib import Path

from build_python_instance_base import BuildPythonInstanceBase
import sys
import textwrap
import shutil

from linux_venv_utils import create_linux_venvs
from wheel_builder_utils import echo_check_call, _remove_tree


class LinuxBuildPythonInstance(BuildPythonInstanceBase):

    def clone(self):
        # Pattern for generating a deep copy of the current object state as a new build instance
        cls = self.__class__
        new = cls.__new__(cls)
        new.__dict__ = copy.deepcopy(self.__dict__)
        return new

    def prepare_build_env(self) -> None:
        # #############################################
        # ### Setup build tools
        self._build_type = "Release"
        self._use_tbb: str = "ON"
        self._tbb_dir = self.IPP_SOURCE_DIR / "oneTBB-prefix" / "lib" / "cmake" / "TBB"
        self._cmake_executable = "cmake"
        # manylinux: the interpreter is provided; ensure basic tools are available
        self.venv_paths()
        self.update_venv_itk_build_configurations()
        self.cmake_compiler_configurations.set(
            "CMAKE_MAKE_PROGRAM:FILEPATH", f"{self.venv_info_dict['ninja_executable']}"
        )
        if self.platform_architechture == "x64":
            target_triple = "x86_64-linux-gnu"
        elif self.platform_architechture in ("aarch64", "arm64"):
            target_triple = "aarch64-linux-gnu"
        elif self.platform_architechture == "x86":
            target_triple = "i686-linux-gnu"
        else:
            target_triple = f"{self.platform_architechture}-linux-gnu"
        self.cmake_compiler_configurations.set(
            "CMAKE_CXX_COMPILER_TARGET:STRING", target_triple
        )
        # TODO: do not use environ here, get from package_env instead
        manylinux_ver = environ.get("MANYLINUX_VERSION", "")
        self.cmake_itk_source_build_configurations.set(
            "ITK_BINARY_DIR:PATH",
            str(
                self.IPP_SOURCE_DIR
                / f"ITK-{self.py_env}-manylinux{manylinux_ver}_{self.platform_architechture}"
            ),
        )

        if self.platform_architechture == "x64":
            target_triple = "x86_64-linux-gnu"
        elif self.platform_architechture in ("aarch64", "arm64"):
            target_triple = "aarch64-linux-gnu"
        elif self.platform_architechture == "x86":
            target_triple = "i686-linux-gnu"
        else:
            target_triple = f"{self.platform_architechture}-linux-gnu"
        self.cmake_compiler_configurations.set(
            "CMAKE_CXX_COMPILER_TARGET:STRING", target_triple
        )
        # Keep values consistent with prior quoting behavior
        self.cmake_compiler_configurations.set("CMAKE_CXX_FLAGS:STRING", "-O3 -DNDEBUG")
        self.cmake_compiler_configurations.set("CMAKE_C_FLAGS:STRING", "-O3 -DNDEBUG")

    def post_build_fixup(self) -> None:
        # Repair all produced wheels with auditwheel and retag meta-wheel
        for whl in (self.IPP_SOURCE_DIR / "dist").glob("*.whl"):
            self.fixup_wheel(str(whl))
        # Special handling for the itk meta wheel to adjust tag
        manylinux_ver = self.package_env_config.get("MANYLINUX_VERSION", "")
        if manylinux_ver:
            for whl in list(
                (self.IPP_SOURCE_DIR / "dist").glob("itk-*linux_*.whl")
            ) + list((self.IPP_SOURCE_DIR / "dist").glob("itk_*linux_*.whl")):
                # Unpack, edit WHEEL tag, repack
                metawheel_dir = self.IPP_SOURCE_DIR / "metawheel"
                metawheel_dist = self.IPP_SOURCE_DIR / "metawheel-dist"
                echo_check_call(
                    [
                        self.venv_info_dict["python_executable"],
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
                        self.venv_info_dict["python_executable"],
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
                        str(new_whl), str((self.IPP_SOURCE_DIR / "dist") / new_whl.name)
                    )
                # Remove old and temp
                try:
                    whl.unlink()
                except OSError:
                    pass
                _remove_tree(metawheel_dir)
                _remove_tree(metawheel_dist)

    def final_import_test(self) -> None:
        self._final_import_test_fn(self.py_env, Path(self.dist_dir))

    def fixup_wheel(self, filepath, lib_paths: str = "") -> None:
        # Use auditwheel to repair wheels and set manylinux tags
        manylinux_ver = self.package_env_config.get("MANYLINUX_VERSION", "")
        if len(manylinux_ver) > 1:
            plat = None
            if self.platform_architechture == "x64" and manylinux_ver:
                plat = f"manylinux{manylinux_ver}_x86_64"
            cmd = [
                self.venv_info_dict["python_executable"],
                "-m",
                "auditwheel",
                "repair",
            ]
            if plat:
                cmd += ["--plat", plat]
            cmd += [str(filepath), "-w", str(self.IPP_SOURCE_DIR / "dist")]
            # Provide LD_LIBRARY_PATH for oneTBB and common system paths
            extra_lib = str(self.IPP_SOURCE_DIR / "oneTBB-prefix" / "lib")
            env = dict(self.package_env_config)
            env["LD_LIBRARY_PATH"] = ":".join(
                [
                    env.get("LD_LIBRARY_PATH", ""),
                    extra_lib,
                    "/usr/lib64",
                    "/usr/lib",
                ]
            )
            echo_check_call(cmd, env=env)
        print(
            f"Building outside of manylinux environment does not require wheel fixups."
        )
        return

    def venv_paths(self) -> None:
        """Resolve virtualenv tool paths.
        py_env may be a name under IPP_SOURCE_DIR/venvs or an absolute/relative path to a venv.
        """
        # First determine if py_env is the full path to a python environment
        _command_line_pip_executable = Path(self.py_env) / "bin" / "pip3"
        _dockcross_pip_executable = Path("/opt/python") / "bin" / "pip3"
        if _command_line_pip_executable.exists():
            venv_dir = Path(self.py_env)
            local_pip_executable = _command_line_pip_executable
        elif _dockcross_pip_executable.exists():
            venv_dir = Path("/opt/python")
            local_pip_executable = _dockcross_pip_executable
        else:
            venv_root_dir: Path = self.IPP_SOURCE_DIR / "venvs"
            _venvs_dir_list = create_linux_venvs(self.py_env, venv_root_dir)
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
                "wheel",
                "auditwheel",
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
        names = []

        # Discover virtualenvs under project 'venvs' folder
        def _discover_ipp_venvs() -> list[str]:
            venvs_dir = self.IPP_SOURCE_DIR / "venvs"
            if not venvs_dir.exists():
                return []
            names.extend([p.name for p in venvs_dir.iterdir() if p.is_dir()])
            # Sort for stable order
            return sorted(names)

        # Discover available manylinux CPython installs under /opt/python
        def _discover_local_pythons() -> list[str]:
            base = Path("/opt/python")
            if not base.exists():
                return []
            names.extend([p.name for p in venvs_dir.iterdir() if p.is_dir()])
            return sorted(names)

        default_py_envs = _discover_linux_pythons() + _discover_ipp_venvs()

        return default_py_envs

    def _final_import_test_fn(self, py_env, param):
        pass
