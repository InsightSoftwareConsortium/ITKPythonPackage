import os
import zipfile
from pathlib import Path

from posix_build_python_instance import PosixBuildPythonInstance


class MacOSBuildPythonInstance(PosixBuildPythonInstance):
    """macOS-specific wheel builder.

    Handles macOS deployment target and architecture settings, and repairs
    every wheel with ``delocate`` on both x86_64 and arm64.
    """

    def _configure_toolchain(self) -> None:
        self.package_env_config["USE_TBB"] = "OFF"
        self.package_env_config["TBB_DIR"] = "NOT_FOUND"
        macosx_target = self.package_env_config.get("MACOSX_DEPLOYMENT_TARGET", "")
        if macosx_target:
            self.cmake_compiler_configurations.set(
                "CMAKE_OSX_DEPLOYMENT_TARGET:STRING", macosx_target
            )
            # scikit-build-core reads this, not the CMake variable.
            os.environ["MACOSX_DEPLOYMENT_TARGET"] = macosx_target
            # sysconfig reports the interpreter's own build target and ignores
            # MACOSX_DEPLOYMENT_TARGET, so without this the wheel tag would not
            # match the compiled binaries.
            os.environ["_PYTHON_HOST_PLATFORM"] = (
                f"macosx-{macosx_target}-{self.target.cmake_osx_arch}"
            )
        self.cmake_compiler_configurations.set(
            "CMAKE_OSX_ARCHITECTURES:STRING", self.target.cmake_osx_arch
        )

    def post_build_fixup(self) -> None:
        """Run ``delocate`` on every wheel to bundle shared libraries."""
        # Every ITK wheel links libc++, not only itk_core as the base-class fixup assumes.
        for wheel in (self.build_dir_root / "dist").glob("*.whl"):
            self.fixup_wheel(str(wheel))

    def fixup_wheel(
        self, filepath, lib_paths: str = "", remote_module_wheel: bool = False
    ) -> None:
        """Repair a wheel using ``delocate``, cleaning AppleDouble files first.

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
        # delocate --require-archs errors on a wheel with no compiled binaries (e.g. the itk metapackage).
        with zipfile.ZipFile(filepath) as wheel_zip:
            has_binaries = any(
                name.endswith((".so", ".dylib")) for name in wheel_zip.namelist()
            )
        if not has_binaries:
            print(f"Skipping delocate for {Path(filepath).name}: no compiled binaries")
            return

        # arm64 needs this too: the pixi toolchain links @rpath/libc++ that only exists on the build host.
        venv_bin_path = self.venv_info_dict.get("venv_bin_path", None)
        if venv_bin_path:
            delocate_listdeps = f"{venv_bin_path}/delocate-listdeps"
            delocate_wheel = f"{venv_bin_path}/delocate-wheel"
            self.echo_check_call([str(delocate_listdeps), str(filepath)])
            self.echo_check_call(
                [
                    str(delocate_wheel),
                    "--require-archs",
                    self.package_env_config["ARCH"],
                    str(filepath),
                ],
                check=True,
            )
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
