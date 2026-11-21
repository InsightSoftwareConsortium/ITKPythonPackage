import contextlib
import os
import zipfile
from pathlib import Path

from posix_build_python_instance import PosixBuildPythonInstance


class MacOSBuildPythonInstance(PosixBuildPythonInstance):
    """macOS-specific wheel builder.

    Handles macOS deployment target and architecture settings, and repairs
    every wheel with ``delocate`` for arm64.
    """

    uses_tbb = False

    def _configure_toolchain(self) -> None:
        macosx_target = self.config.macosx_deployment_target
        if macosx_target:
            self.cmake_compiler_configurations.set(
                "CMAKE_OSX_DEPLOYMENT_TARGET:STRING", macosx_target
            )
            # scikit-build-core reads this, not the CMake variable.
            os.environ["MACOSX_DEPLOYMENT_TARGET"] = macosx_target
            # sysconfig ignores MACOSX_DEPLOYMENT_TARGET when it names the wheel tag.
            os.environ["_PYTHON_HOST_PLATFORM"] = (
                f"macosx-{macosx_target}-{self.target.cmake_osx_arch}"
            )
        self.cmake_compiler_configurations.set(
            "CMAKE_OSX_ARCHITECTURES:STRING", self.target.cmake_osx_arch
        )

    def post_build_fixup(self) -> None:
        """Run ``delocate`` on every wheel to bundle shared libraries."""
        # Every ITK wheel links libc++, not only itk_core.
        for wheel in (self.build_dir_root / "dist").glob("*.whl"):
            self.fixup_wheel(str(wheel))

    def fixup_wheel(self, filepath: str) -> None:
        """Repair a wheel in place using ``delocate``, cleaning AppleDouble files first.

        Parameters
        ----------
        filepath : str
            Path to the ``.whl`` file.
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

        # The pixi toolchain links @rpath/libc++, which exists only on the build host.
        venv_bin_path = self.python_env.bin_path
        delocate_listdeps = f"{venv_bin_path}/delocate-listdeps"
        delocate_wheel = f"{venv_bin_path}/delocate-wheel"
        if not Path(delocate_wheel).is_file():
            msg = (
                f"delocate-wheel not found in {venv_bin_path}; cannot repair "
                f"{Path(filepath).name}. Install delocate in the build environment."
            )
            raise RuntimeError(msg)
        self.echo_check_call([str(delocate_listdeps), str(filepath)])
        self.echo_check_call(
            [
                str(delocate_wheel),
                "--require-archs",
                self.config.pixi_suffix,
                str(filepath),
            ],
            check=True,
        )

    def remove_apple_double_files(self) -> None:
        """Remove AppleDouble ``._*`` files using ``dot_clean`` if available."""
        # dot_clean may not be available; continue without it
        with contextlib.suppress(Exception):
            self.echo_check_call(["dot_clean", str(self.ipp_dir)])
