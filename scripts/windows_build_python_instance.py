from __future__ import annotations

import copy
import os
from os import environ
from pathlib import Path

from build_python_instance_base import BuildPythonInstanceBase

import shutil

from wheel_builder_utils import push_dir, _remove_tree


class WindowsBuildPythonInstance(BuildPythonInstanceBase):

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
        return "windows"

    def prepare_build_env(self) -> None:
        # #############################################
        # ### Setup build tools
        self._build_type = "Release"
        self._use_tbb: str = "ON"
        # The interpreter is provided; ensure basic tools are available
        self.venv_paths()
        self.update_venv_itk_build_configurations()

        target_arch = self.package_env_config["ARCH"]
        itk_binary_build_name: Path = (
            self.build_dir_root
            / "build"
            / f"ITK-{self.platform_env}-{self.get_pixi_environment_name()}_{target_arch}"
        )

        self.cmake_itk_source_build_configurations.set(
            "ITK_BINARY_DIR:PATH", itk_binary_build_name
        )

        # Keep values consistent with prior quoting behavior
        # self.cmake_compiler_configurations.set("CMAKE_CXX_FLAGS:STRING", "-O3 -DNDEBUG")
        # self.cmake_compiler_configurations.set("CMAKE_C_FLAGS:STRING", "-O3 -DNDEBUG")

    def post_build_fixup(self) -> None:
        # append the oneTBB-prefix\\bin directory for fixing wheels built with local oneTBB
        search_lib_paths = (
            [s for s in str(self.windows_extra_lib_paths[0]).rstrip(";") if s]
            if self.windows_extra_lib_paths
            else []
        )
        search_lib_paths.append(str(self.build_dir_root / "oneTBB-prefix" / "bin"))
        search_lib_paths_str: str = ";".join(map(str, search_lib_paths))
        self.fixup_wheels(search_lib_paths_str)

    def post_build_cleanup(self) -> None:
        """Clean build artifacts

        Actions (leaving dist/ intact):
        - remove oneTBB-prefix (symlink or dir)
        - remove ITKPythonPackage/, tools/, _skbuild/, build/
        - remove top-level *.egg-info
        - remove ITK-* build tree and tarballs
        - if ITK_MODULE_PREQ is set ("org/name@ref:org2/name2@ref2"), remove cloned module dirs
        """
        base = Path(self.package_env_config["IPP_SOURCE_DIR"])

        def rm(tree_path: Path):
            try:
                _remove_tree(tree_path)
            except Exception:
                pass

        # 1) unlink oneTBB-prefix if it's a symlink or file
        tbb_prefix_dir = base / "oneTBB-prefix"
        try:
            if tbb_prefix_dir.is_symlink() or tbb_prefix_dir.is_file():
                tbb_prefix_dir.unlink(missing_ok=True)  # type: ignore[arg-type]
            elif tbb_prefix_dir.exists():
                rm(tbb_prefix_dir)
        except Exception:
            pass

        # 2) standard build directories
        for rel in ("ITKPythonPackage", "tools", "_skbuild", "build"):
            rm(base / rel)

        # 3) egg-info folders at top-level
        for p in base.glob("*.egg-info"):
            rm(p)

        # 4) ITK build tree and tarballs
        target_arch = self.package_env_config["ARCH"]
        for p in base.glob(f"ITK-*-{self.package_env_config}_{target_arch}"):
            rm(p)

        # Tarballs
        for p in base.glob(f"ITKPythonBuilds-{self.package_env_config}*.tar.zst"):
            rm(p)

        # 5) Optional module prerequisites cleanup (ITK_MODULE_PREQ)
        # Format: "InsightSoftwareConsortium/ITKModuleA@v1.0:Kitware/ITKModuleB@sha" -> remove repo names
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
        self._final_import_test_fn(self.platform_env, Path(self.dist_dir))

    def fixup_wheel(self, filepath, lib_paths: str = "") -> None:
        # Windows fixup_wheel
        lib_paths = lib_paths.strip()
        lib_paths = lib_paths + ";" if lib_paths else ""
        print(f"Library paths for fixup: {lib_paths}")

        delve_wheel = (
            self.venv_info_dict["python_root_dir"] / "Scripts" / "delvewheel.exe"
        )
        cmd = [
            str(delve_wheel),
            "repair",
            "--no-mangle-all",
            "--add-path",
            lib_paths.strip(";"),
            "--ignore-in-wheel",
            "-w",
            str(self.build_dir_root / "dist"),
            str(filepath),
        ]
        self.echo_check_call(cmd)

    def build_tarball(self):
        """Create an archive of the ITK Python package build tree (Windows).

        Mirrors scripts/windows-build-tarball.ps1 behavior:
        - Remove contents of IPP/dist
        - Use 7-Zip, when present, to archive the full IPP tree into
          ITKPythonBuilds-windows.zip at the parent directory of IPP (e.g., C:\P)
        - Fallback to Python's zip archive creation if 7-Zip is unavailable
        """

        out_zip = self.build_dir_root / "build" / "ITKPythonBuilds-windows.zip"

        # 1) Clean IPP/dist contents (do not remove the directory itself)
        dist_dir = self.build_dir_root / "dist"
        if dist_dir.exists():
            for p in dist_dir.glob("*"):
                try:
                    if p.is_dir():
                        # shutil.rmtree alternative without importing here
                        for sub in p.rglob("*"):
                            # best-effort clean
                            try:
                                if sub.is_file() or sub.is_symlink():
                                    sub.unlink(missing_ok=True)
                            except Exception:
                                pass
                        try:
                            p.rmdir()
                        except Exception:
                            pass
                    else:
                        p.unlink(missing_ok=True)
                except Exception:
                    # best-effort cleanup; ignore errors to continue packaging
                    pass

        # 2) Try to use 7-Zip if available
        seven_zip_candidates = [
            Path(r"C:\\7-Zip\\7z.exe"),
            Path(r"C:\\Program Files\\7-Zip\\7z.exe"),
            Path(r"C:\\Program Files (x86)\\7-Zip\\7z.exe"),
        ]

        seven_zip = None
        for cand in seven_zip_candidates:
            if cand.exists():
                seven_zip = cand
                break

        if seven_zip is None:
            # Try PATH lookup using where/which behavior from shutil
            import shutil as _shutil

            found = _shutil.which("7z.exe") or _shutil.which("7z")
            if found:
                seven_zip = Path(found)

        if seven_zip is not None:
            # Match the PS1: run from C:\P and create archive of IPP directory
            with push_dir(self.build_dir_root):
                # Using -t7z in the PS1 but naming .zip; preserve behavior
                cmd = [
                    str(seven_zip),
                    "a",
                    "-t7z",
                    "-r",
                    str(out_zip),
                    "-w",
                    str(self.build_dir_root),
                ]
                self.echo_check_call(cmd)
            return

        # 3) Fallback: create a .zip using Python's shutil
        # This will create a zip archive named ITKPythonBuilds-windows.zip
        import shutil as _shutil

        if out_zip.exists():
            try:
                out_zip.unlink()
            except Exception:
                pass
        # make_archive requires base name without extension
        base_name = str(out_zip.with_suffix("").with_suffix(""))
        # shutil.make_archive will append .zip
        _shutil.make_archive(
            base_name,
            "zip",
            root_dir=str(self.build_dir_root),
            base_dir=str(self.build_dir_root.name),
        )

    def venv_paths(self) -> None:
        # Create venv related paths
        python_major: int = int(self.platform_env.split(".")[0])
        python_minor: int = int(self.platform_env.split(".")[1])
        virtualenv_pattern = (
            f"Python{python_major}*{python_minor}*/Scripts/virtualenv.exe"
        )
        all_glob_matches = [p for p in Path("C:\\").glob(virtualenv_pattern)]
        if len(all_glob_matches) > 1:
            raise RuntimeError(
                f"Multiple virtualenv.exe matches found: {all_glob_matches}"
            )
        elif len(all_glob_matches) == 0:
            raise RuntimeError(
                f"No virtualenv.exe matches found for Python {virtualenv_pattern}"
            )
        venv_executable = Path(all_glob_matches[0])
        # On windows use base python interpreter, and not a virtual env
        primary_python_base_dir: Path = venv_executable.parent.parent
        venv_base_dir: Path = primary_python_base_dir
        venv_bin_path = venv_base_dir / "Scripts"
        # venv_base_dir = (
        #     Path(self.build_dir_root) / f"venv-{python_major}.{python_minor}"
        # )
        if not venv_base_dir.exists():
            self.echo_check_call(
                [venv_executable, str(venv_base_dir)], use_pixi_env=False
            )

        python_executable = primary_python_base_dir / "python.exe"
        python_include_dir = primary_python_base_dir / "include"
        if int(python_minor) >= 11:
            # Stable ABI
            python_library = primary_python_base_dir / "libs" / "python3.lib"
        else:
            # XXX It should be possible to query skbuild for the library dir associated
            #     with a given interpreter.
            xy_lib_ver = f"{python_major}{python_minor}"
            python_library = (
                primary_python_base_dir / "libs" / f"python{xy_lib_ver}.lib"
            )

        if venv_base_dir.exists():
            # Install required tools into each venv
            self._pip_uninstall_itk_wildcard(python_executable)
            self.echo_check_call(
                [python_executable, "-m", "pip", "install", "--upgrade", "pip"],
                use_pixi_env=False,
            )
            self.echo_check_call(
                [
                    python_executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "build",
                    "numpy",
                    "scikit-build-core",
                    #  os-specific tools below
                    "delvewheel",
                    "pkginfo",
                ],
                use_pixi_env=False,
            )
            # Install dependencies
            self.echo_check_call(
                [
                    python_executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "-r",
                    str(
                        self.package_env_config["IPP_SOURCE_DIR"]
                        / "requirements-dev.txt"
                    ),
                ],
                use_pixi_env=False,
            )
        self.venv_info_dict = {
            "python_executable": python_executable,
            "python_include_dir": python_include_dir,
            "python_library": python_library,
            "venv_bin_path": venv_bin_path,
            "venv_base_dir": venv_base_dir,
            "python_root_dir": primary_python_base_dir,
        }

    def discover_python_venvs(
        self, platform_os_name: str, platform_architechure: str
    ) -> list[str]:
        default_platform_envs = [
            f"39-{platform_architechure}",
            f"310-{platform_architechure}",
            f"311-{platform_architechure}",
        ]
        return default_platform_envs

    def _final_import_test_fn(self, platform_env, param):
        pass
