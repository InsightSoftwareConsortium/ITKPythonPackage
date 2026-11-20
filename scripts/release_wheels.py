#!/usr/bin/env python3
"""Build every ITK release wheel this machine can build.

    pixi run release-wheels <itk-ref> [<package-version>]

``<itk-ref>`` is an ITK tag, branch or commit. A tag also names the package
version; a branch or commit needs ``<package-version>`` for wheels that can be
uploaded to PyPI, and otherwise gets a version derived with ``git describe``.

Run the same command on each build machine:

=================  ====================================================
Host               Wheels
=================  ====================================================
Windows x64        Windows x64
macOS arm64        macOS arm64, then Linux aarch64 (docker)
Linux x64          Linux x86_64 (docker)
Linux aarch64      Linux aarch64 (docker)
=================  ====================================================

macOS wheels need a macOS host: the build uses Apple's SDK and tools, and the
import test runs the wheels. ``--targets`` selects a subset, or a Linux
architecture that this host can only build under emulation.

The script uses only the standard library, so ``python3`` works as well as
``pixi run``.
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

IPP_DIR = Path(__file__).resolve().parent.parent
ITK_REPOSITORY = "https://github.com/InsightSoftwareConsortium/ITK.git"
FETCHED_BRANCHES = "refs/remotes/release-source"

TARGETS = ("windows-x64", "macos-arm64", "manylinux-x64", "manylinux-aarch64")
NATIVE_PIXI_ENV = {"windows-x64": "windows-py311", "macos-arm64": "macosx-py311"}
CONTAINER_ARCH = {"manylinux-x64": "x64", "manylinux-aarch64": "aarch64"}
WHEEL_GLOB = {
    "windows-x64": "itk*-win_amd64.whl",
    "macos-arm64": "itk*-macosx_*_arm64.whl",
    "manylinux-x64": "itk*-manylinux_*_x86_64.whl",
    "manylinux-aarch64": "itk*-manylinux_*_aarch64.whl",
}

_PEP440_RELEASE = re.compile(r"^\d+(\.\d+)*((a|b|rc)\d+)?(\.post\d+)?(\.dev\d+)?$")


@dataclass(frozen=True)
class Host:
    """Operating system (``linux``, ``darwin``, ``windows``) and architecture."""

    system: str
    arch: str  # "x64" or "arm64"

    @classmethod
    def detect(cls) -> Host:
        machine = platform.machine().lower()
        arch = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64"}.get(
            machine, machine
        )
        return cls(platform.system().lower(), arch)


@dataclass
class Step:
    """One wheel build: a command, its environment additions and its output."""

    target: str
    command: list[str]
    env: dict[str, str] = field(default_factory=dict)
    dist_dir: Path = Path()


def default_targets(host: Host) -> list[str]:
    """Targets built when ``--targets`` is not given."""
    defaults = {
        ("windows", "x64"): ["windows-x64"],
        ("darwin", "arm64"): ["macos-arm64", "manylinux-aarch64"],
        ("linux", "x64"): ["manylinux-x64"],
        ("linux", "arm64"): ["manylinux-aarch64"],
    }
    try:
        return defaults[(host.system, host.arch)]
    except KeyError:
        raise SystemExit(
            f"No ITK wheel target is built on {host.system} {host.arch}."
        ) from None


def unbuildable_reason(target: str, host: Host) -> str | None:
    """Why *host* cannot build *target*, or None when it can."""
    if target in CONTAINER_ARCH:
        if host.system == "windows":
            return "manylinux wheels are built with docker from Linux or macOS"
        return None
    if target == "macos-arm64" and host != Host("darwin", "arm64"):
        return (
            "macOS wheels need an Apple Silicon Mac: the build uses Apple's "
            "SDK and tools, and the import test runs the wheels"
        )
    if target == "windows-x64" and host != Host("windows", "x64"):
        return "Windows wheels need a Windows x64 host"
    return None


def select_targets(requested: list[str] | None, host: Host) -> list[str]:
    targets = requested or default_targets(host)
    for target in targets:
        if target not in TARGETS:
            raise SystemExit(
                f"Unknown target {target!r}; choose from {', '.join(TARGETS)}."
            )
        reason = unbuildable_reason(target, host)
        if reason:
            raise SystemExit(f"Cannot build {target} here: {reason}.")
    return targets


def package_version(itk_ref: str, ref_is_tag: bool, version: str | None) -> str:
    """Package version to pass on, or ``gitauto`` to derive one per build."""
    if version is None:
        if not ref_is_tag:
            return "gitauto"
        version = itk_ref
    bare = version.removeprefix("v")
    if not _PEP440_RELEASE.match(bare):
        raise SystemExit(
            f"{version!r} is not a version PyPI accepts, such as v6.0b03 or "
            f"6.0b3; pass one after the ITK ref."
        )
    return bare


def native_build_root() -> Path:
    """``build_wheels.py``'s default build root on this host."""
    if platform.system().lower() == "windows":
        return Path("C:/") / "BDR"
    return IPP_DIR.parent / "ITKPythonPackage-build"


def container_build_root() -> Path:
    """Host directory that the manylinux container builds in."""
    manylinux = os.environ.get("MANYLINUX_VERSION") or "_2_28"
    return IPP_DIR.parent / f"ITKPythonPackage-manylinux{manylinux}-build"


def _git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=check, capture_output=True, text=True
    )


def _commit_of(src: Path, rev: str) -> str | None:
    result = _git(
        "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}", cwd=src, check=False
    )
    return result.stdout.strip() or None


def prepare_itk_source(src: Path, repository: str, itk_ref: str) -> tuple[str, bool]:
    """Clone or update *src* from *repository*; return the commit and whether
    *itk_ref* is a tag."""
    if not src.exists():
        src.parent.mkdir(parents=True, exist_ok=True)
        print(f"Cloning {repository} into {src}", flush=True)
        subprocess.run(["git", "clone", "--quiet", repository, str(src)], check=True)
    elif _git("rev-parse", "--git-dir", cwd=src, check=False).returncode != 0:
        raise SystemExit(f"{src} exists but is not a git repository; remove it.")
    elif _git("status", "--porcelain", "--untracked-files=no", cwd=src).stdout:
        raise SystemExit(f"{src} has uncommitted changes; commit or discard them.")

    print(f"Fetching {repository} into {src}", flush=True)
    _git(
        "fetch",
        "--quiet",
        "--force",
        "--tags",
        repository,
        f"+refs/heads/*:{FETCHED_BRANCHES}/*",
        cwd=src,
    )
    if commit := _commit_of(src, f"refs/tags/{itk_ref}"):
        return commit, True
    if commit := _commit_of(src, f"{FETCHED_BRANCHES}/{itk_ref}"):
        return commit, False
    if not _commit_of(src, itk_ref):
        # A commit that no branch of the repository contains, e.g. of a pull
        # request; GitHub serves those by full hash.
        _git("fetch", "--quiet", repository, itk_ref, cwd=src, check=False)
    if commit := _commit_of(src, itk_ref):
        return commit, False
    raise SystemExit(f"{itk_ref!r} is not a tag, branch or commit of {repository}.")


def _pixi() -> str:
    for candidate in (
        shutil.which("pixi"),
        IPP_DIR / ".pixi" / "bin" / "pixi",
        IPP_DIR / ".pixi" / "bin" / "pixi.exe",
    ):
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise SystemExit(
        "pixi was not found; install it with: python3 scripts/install_pixi.py"
    )


def _container_engine() -> str:
    for engine in ("nerdctl", "docker", "podman"):
        if shutil.which(engine):
            return engine
    raise SystemExit("manylinux wheels need docker, podman or nerdctl on PATH.")


def plan(
    targets: list[str], itk_source: Path, commit: str, version: str, pixi: str = "pixi"
) -> list[Step]:
    """The build of each target, in order."""
    steps = []
    for target in targets:
        if target in NATIVE_PIXI_ENV:
            env_name = NATIVE_PIXI_ENV[target]
            steps.append(
                Step(
                    target,
                    [
                        pixi,
                        "run",
                        "-e",
                        env_name,
                        "python",
                        str(IPP_DIR / "scripts" / "build_wheels.py"),
                        "--platform-env",
                        env_name,
                        "--build-dir-root",
                        str(native_build_root()),
                        "--itk-source-dir",
                        str(itk_source),
                        "--itk-git-tag",
                        commit,
                        "--itk-package-version",
                        version,
                        "--build-itk-tarball-cache",
                    ],
                    dist_dir=native_build_root() / "dist",
                )
            )
        else:
            steps.append(
                Step(
                    target,
                    [
                        "bash",
                        str(
                            IPP_DIR / "scripts" / "dockcross-manylinux-build-wheels.sh"
                        ),
                        "py311",
                    ],
                    env={
                        "ITK_SOURCE_DIR": str(itk_source),
                        "ITK_GIT_TAG": commit,
                        "ITK_PACKAGE_VERSION": version,
                        "TARGET_ARCH": CONTAINER_ARCH[target],
                        # Docker Desktop and docker-group users need no sudo.
                        "NO_SUDO": os.environ.get("NO_SUDO", "1"),
                    },
                    dist_dir=container_build_root() / "dist",
                )
            )
    return steps


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        epilog="Targets: " + ", ".join(TARGETS),
    )
    parser.add_argument("itk_ref", help="ITK tag, branch or commit, e.g. v6.0b03")
    parser.add_argument(
        "package_version",
        nargs="?",
        help="wheel version, e.g. 6.0b3; defaults to the tag for a tag ref",
    )
    parser.add_argument(
        "--targets",
        type=lambda s: [t.strip() for t in s.split(",") if t.strip()],
        help="comma-separated subset of targets; default: all this host builds",
    )
    parser.add_argument(
        "--itk-repository",
        default=ITK_REPOSITORY,
        help="repository to fetch the ITK ref from (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the builds and stop"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    host = Host.detect()
    targets = select_targets(args.targets, host)
    itk_source = native_build_root() / "ITK"

    if args.dry_run:
        commit = args.itk_ref
        ref_is_tag = bool(_PEP440_RELEASE.match(args.itk_ref.removeprefix("v")))
        pixi = "pixi"
    else:
        if any(t in CONTAINER_ARCH for t in targets):
            _container_engine()
        pixi = _pixi() if any(t in NATIVE_PIXI_ENV for t in targets) else "pixi"
        commit, ref_is_tag = prepare_itk_source(
            itk_source, args.itk_repository, args.itk_ref
        )
    version = package_version(args.itk_ref, ref_is_tag, args.package_version)
    if version == "gitauto":
        print(
            "WARNING: no package version given for a non-tag ref; the "
            "derived version is for testing and PyPI may reject it.",
            flush=True,
        )
    print(f"ITK {args.itk_ref} = {commit}; package version {version}", flush=True)

    failed = []
    for step in plan(targets, itk_source, commit, version, pixi):
        env_text = " ".join(f"{k}={v}" for k, v in step.env.items())
        print(f"\n=== {step.target}: {env_text} {' '.join(step.command)}", flush=True)
        if args.dry_run:
            continue
        result = subprocess.run(
            step.command, cwd=IPP_DIR, env={**os.environ, **step.env}, check=False
        )
        if result.returncode != 0:
            failed.append(step.target)
            print(f"=== {step.target} FAILED (exit {result.returncode})", flush=True)
            continue
        print(f"=== {step.target} wheels in {step.dist_dir}:", flush=True)
        for wheel in sorted(step.dist_dir.glob(WHEEL_GLOB[step.target])):
            print(f"    {wheel.name}  {wheel.stat().st_size / 1e6:.1f} MB")

    if failed:
        print(f"\nFailed: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
