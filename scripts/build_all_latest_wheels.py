#!/usr/bin/env python3
"""Build ITK + all remote module Python wheels from latest main branches.

Usage::

    python scripts/build_all_latest_wheels.py [--platform-env linux-py311]
    python scripts/build_all_latest_wheels.py --help
"""

import argparse
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, check=True, **kwargs)


def clone(repo: str, dest: Path, branch: str | None = None) -> bool:
    cmd = ["git", "clone", "--depth", "1"]
    if branch:
        cmd += ["--branch", branch]
    cmd += [repo, str(dest)]
    try:
        run(cmd, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False


def parse_remote_modules(itk_dir: Path) -> list[tuple[str, str]]:
    """Parse ITK remote .cmake files, return [(name, git_url), ...]."""
    modules = []
    for rc in sorted((itk_dir / "Modules" / "Remote").glob("*.remote.cmake")):
        name = rc.stem.replace(".remote", "")
        text = rc.read_text()
        m = re.search(r"GIT_REPOSITORY\s+(\S+)", text)
        if m:
            modules.append((name, m.group(1)))
    return modules


def build_wheels(
    ipp_dir: Path,
    platform_env: str,
    build_dir: Path,
    itk_source: Path,
    module_source: Path | None = None,
    skip_itk: bool = False,
) -> bool:
    cmd = [
        "pixi",
        "run",
        "-e",
        platform_env,
        "--",
        "python",
        "scripts/build_wheels.py",
        "--platform-env",
        platform_env,
        "--itk-git-tag",
        "main",
        "--itk-source-dir",
        str(itk_source),
        "--no-build-itk-tarball-cache",
        "--no-use-sudo",
        "--build-dir-root",
        str(build_dir),
    ]
    if module_source:
        cmd += ["--module-source-dir", str(module_source)]
    if skip_itk:
        cmd += ["--skip-itk-build", "--skip-itk-wheel-build"]

    try:
        run(cmd, cwd=ipp_dir)
        return True
    except subprocess.CalledProcessError:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--platform-env", default="linux-py311", help="Pixi environment name"
    )
    parser.add_argument(
        "--ipp-branch",
        default="python-build-system",
        help="ITKPythonPackage branch to use",
    )
    parser.add_argument(
        "--ipp-repo",
        default="https://github.com/BRAINSia/ITKPythonPackage.git",
        help="ITKPythonPackage git URL",
    )
    parser.add_argument(
        "--itk-repo",
        default="https://github.com/InsightSoftwareConsortium/ITK.git",
        help="ITK git URL",
    )
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    workdir = Path(f"/tmp/{timestamp}_LatestITKPython")
    dist_dir = workdir / "dist"
    dist_dir.mkdir(parents=True)
    build_dir = workdir / "build"

    print(f"=== Build directory: {workdir}")
    print(f"=== Platform: {args.platform_env}")

    # 1) Clone ITK
    print("=== Cloning ITK (main)...")
    itk_dir = workdir / "ITK"
    clone(args.itk_repo, itk_dir, branch="main")

    # 2) Clone ITKPythonPackage
    print(f"=== Cloning ITKPythonPackage ({args.ipp_branch})...")
    ipp_dir = workdir / "ITKPythonPackage"
    clone(args.ipp_repo, ipp_dir, branch=args.ipp_branch)

    # 3) Clone remote modules
    print("=== Cloning remote modules...")
    modules_dir = workdir / "modules"
    modules_dir.mkdir()
    remote_modules = parse_remote_modules(itk_dir)

    module_list: list[str] = []
    for name, repo in remote_modules:
        mod_dir = modules_dir / name
        if not clone(repo, mod_dir):
            print(f"  WARNING: Failed to clone {name}, skipping")
            continue
        # Keep only modules with Python wrapping
        if (mod_dir / "wrapping").is_dir() and (mod_dir / "pyproject.toml").is_file():
            module_list.append(name)
        else:
            shutil.rmtree(mod_dir)

    print(f"=== {len(module_list)} modules with Python wrapping")

    # 4) Build ITK wheels
    print("=== Building ITK Python wheels...")
    if not build_wheels(ipp_dir, args.platform_env, build_dir, itk_dir):
        print("FATAL: ITK wheel build failed")
        sys.exit(1)

    # Copy ITK wheels to dist
    for whl in (build_dir / "dist").glob("*.whl"):
        shutil.copy2(whl, dist_dir)

    # 5) Build each remote module wheel
    failed: list[str] = []
    for name in module_list:
        print(f"=== Building {name}...")
        mod_dir = modules_dir / name
        if build_wheels(
            ipp_dir,
            args.platform_env,
            build_dir,
            itk_dir,
            module_source=mod_dir,
            skip_itk=True,
        ):
            for whl in (mod_dir / "dist").glob("*.whl"):
                shutil.copy2(whl, dist_dir)
        else:
            print(f"  FAILED: {name}")
            failed.append(name)

    # 6) Summary
    wheels = list(dist_dir.glob("*.whl"))
    print()
    print("=== Build complete ===")
    print(f"Wheels: {dist_dir}")
    print(f"{len(wheels)} total wheels produced")

    if failed:
        print(f"\nFailed modules ({len(failed)}):")
        for name in failed:
            print(f"  {name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
