from pathlib import Path

from build_python_instance_base import BuildPythonInstanceBase


class MacOSBuildPythonInstance(BuildPythonInstanceBase):
    """macOS-specific wheel builder.

    Handles macOS deployment target and architecture settings, and uses
    ``delocate`` for wheel repair on x86_64 builds.
    """

    def prepare_build_env(self) -> None:
        """Set up the macOS build environment, deployment target, and architecture."""
        # #############################################
        # ### Setup build tools
        self.package_env_config["USE_TBB"] = "OFF"
        self.package_env_config["TBB_DIR"] = "NOT_FOUND"

        # The interpreter is provided; ensure basic tools are available
        self.venv_paths()
        self.update_venv_itk_build_configurations()
        macosx_target = self.package_env_config.get("MACOSX_DEPLOYMENT_TARGET", "")
        if macosx_target:
            self.cmake_compiler_configurations.set(
                "CMAKE_OSX_DEPLOYMENT_TARGET:STRING", macosx_target
            )

        target_arch = self.package_env_config["ARCH"]

        self.cmake_compiler_configurations.set(
            "CMAKE_OSX_ARCHITECTURES:STRING", target_arch
        )

        # build will be here if downloaded
        binaries_path = Path(
            self.build_dir_root
            / "build"
            / f"ITK-{self.platform_env}-{self.platform_env}_{target_arch}"
        )

        if Path(binaries_path).exists():
            itk_binary_build_name = binaries_path
        else:
            itk_binary_build_name: Path = (
                self.build_dir_root
                / "build"
                / f"ITK-{self.platform_env}-{self.get_pixi_environment_name()}_{target_arch}"
            )

        self.cmake_itk_source_build_configurations.set(
            "ITK_BINARY_DIR:PATH", itk_binary_build_name.as_posix()
        )

        # Keep values consistent with prior quoting behavior
        # self.cmake_compiler_configurations.set("CMAKE_CXX_FLAGS:STRING", "-O3 -DNDEBUG")
        # self.cmake_compiler_configurations.set("CMAKE_C_FLAGS:STRING", "-O3 -DNDEBUG")

    def post_build_fixup(self) -> None:
        """Run ``delocate`` on x86_64 wheels to bundle shared libraries."""
        # delocate on macOS x86_64 only
        if self.package_env_config["ARCH"] == "x86_64":
            self.fixup_wheels()

    def build_tarball(self):
        """Create a zstd-compressed tarball of the ITK build tree."""
        self.create_posix_tarball()

    def discover_python_venvs(
        self, platform_os_name: str, platform_architechure: str
    ) -> list[str]:
        """Discover available Python environments under the project ``venvs/`` dir.

        Parameters
        ----------
        platform_os_name : str
            Operating system identifier (unused, kept for interface).
        platform_architechure : str
            Architecture identifier (unused, kept for interface).

        Returns
        -------
        list[str]
            Sorted list of discovered environment names.
        """
        names = []

        # Discover virtualenvs under project 'venvs' folder
        def _discover_ipp_venvs() -> list[str]:
            venvs_dir = self.build_dir_root / "venvs"
            if not venvs_dir.exists():
                return []
            names.extend([p.name for p in venvs_dir.iterdir() if p.is_dir()])
            # Sort for stable order
            return sorted(names)

        default_platform_envs = _discover_ipp_venvs()

        return default_platform_envs

    def fixup_wheel(
        self, filepath, lib_paths: str = "", remote_module_wheel: bool = False
    ) -> None:
        """Repair a wheel using ``delocate`` on x86_64, cleaning AppleDouble files first.

        Parameters
        ----------
        filepath : str
            Path to the ``.whl`` file.
        lib_paths : str, optional
            Unused on macOS (kept for interface compatibility).
        remote_module_wheel : bool, optional
            Unused on macOS (kept for interface compatibility).
        """
        self.remove_apple_double_files()
        # macOS fix-up with delocate (only needed for x86_64)
        if self.package_env_config["ARCH"] != "arm64":
            venv_bin_path = self.venv_info_dict.get("venv_bin_path", None)
            if venv_bin_path:
                delocate_listdeps = f"{venv_bin_path}/delocate-listdeps"
                delocate_wheel = f"{venv_bin_path}/delocate-wheel"
                self.echo_check_call([str(delocate_listdeps), str(filepath)])
                self.echo_check_call([str(delocate_wheel), str(filepath)])
            else:
                print(
                    "=" * 20
                    + "WARNING: Could not find venv binary to delocate wheel"
                    + "=" * 20
                )

    def remove_apple_double_files(self):
        """Remove AppleDouble ``._*`` files using ``dot_clean`` if available."""
        try:
            # Optional: clean AppleDouble files if tool is available
            self.echo_check_call(
                ["dot_clean", str(self.package_env_config["IPP_SOURCE_DIR"])]
            )
        except Exception:
            # dot_clean may not be available; continue without it
            pass
