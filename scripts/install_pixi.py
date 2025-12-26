#!/usr/bin/env python3

from pathlib import Path
import os

from wheel_builder_utils import run_commandLine_subprocess, detect_platform


def download_and_install_pixi(
    binary_ext: str, os_name: str, pixi_home: Path, platform_env: str = "default"
) -> Path:
    pixi_bin_name: str = "pixi" + binary_ext
    # Attempt to find an existing pixi binary on the system first (cross-platform)
    pixi_exec_path: Path = Path(pixi_home) / "bin" / pixi_bin_name

    pixi_install_env = os.environ.copy()
    pixi_install_env["PIXI_NO_PATH_UPDATE"] = "1"
    pixi_install_env["PIXI_HOME"] = str(pixi_home)

    # If not found, we will install into the local build .pixi
    if pixi_exec_path.is_file():
        print(f"Previous install of pixi will be used {pixi_exec_path}.")
    else:
        if os_name == "windows":
            # Use PowerShell to install pixi on Windows
            result = run_commandLine_subprocess(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    "irm -UseBasicParsing https://pixi.sh/install.ps1 | iex",
                ],
                env=pixi_install_env,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Failed to install pixi: {result.stderr}")
        else:
            pixi_install_script: Path = pixi_home / "pixi_install.sh"
            result = run_commandLine_subprocess(
                [
                    "curl",
                    "-fsSL",
                    "https://pixi.sh/install.sh",
                    "-o",
                    str(pixi_install_script),
                ]
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Failed to download {pixi_install_script}: {result.stderr}"
                )
            result = run_commandLine_subprocess(
                [
                    "/bin/sh",
                    str(pixi_install_script),
                ],
                env=pixi_install_env,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Failed to install pixi: {result.stderr}")
            del pixi_install_script

    if not pixi_exec_path.exists():
        raise RuntimeError(
            f"Failed to install {pixi_exec_path} pixi into {pixi_exec_path}"
        )
    # Now install the desired platform
    if (pixi_home.parent / "pixi.toml").exists():
        result = run_commandLine_subprocess(
            [pixi_exec_path, "install", "--environment", platform_env],
            cwd=pixi_home.parent,
            env=pixi_install_env,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to install environment {platform_env}: {result.stderr}"
            )
    else:
        print(
            f"pixi.toml not found {pixi_home.parent / 'pixi.toml'}, skipping environment install."
        )
    return pixi_exec_path


def install_pixi_tools(platform_env: str = "default"):
    _ipp_dir_path: Path = Path(__file__).resolve().parent.parent
    os_name, arch = detect_platform()
    binary_ext: str = ".exe" if os_name == "windows" else ""

    pixi_home: Path = Path(
        os.environ.get("PIXI_HOME")
        if "PIXI_HOME" in os.environ
        else _ipp_dir_path / ".pixi"
    )
    pixi_home.mkdir(parents=True, exist_ok=True)
    pixi_exec_path = Path(
        download_and_install_pixi(binary_ext, os_name, pixi_home, platform_env)
    )
    print(f"Installed pixi locally to {pixi_home} with binary of {pixi_exec_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Driver script to build ITK Python wheels."
    )
    parser.add_argument(
        "--platform-env",
        default="default",
        help=(
            """A platform environment name or path: 
               linux-py39, linux-py310, linux-py311,
               manylinux228-py39, manylinux228-py310, manylinux228-py311,
               windows-py39, windows-py310, windows-py311,
               macos-py39, macos-py310, macos-py311
            """
        ),
    )
    args = parser.parse_args()
    install_pixi_tools(args.platform_env)
