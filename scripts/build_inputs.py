"""What a build's outputs depend on, as recorded in the step report.

A run whose inputs differ from the recorded ones runs every step again.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

#: ITKPythonPackage files, relative to its root, that shape every build.
FINGERPRINT_SOURCES: tuple[str, ...] = (
    "pixi.lock",
    "BuildWheelsSupport",
    "SuperbuildSupport",
    "cmake",
    "scripts",
)


def fingerprint_files(ipp_dir: Path) -> list[Path]:
    """Return the files under *ipp_dir* that enter the fingerprint, sorted."""
    files: list[Path] = []
    for name in FINGERPRINT_SOURCES:
        source = Path(ipp_dir) / name
        if source.is_file():
            files.append(source)
        elif source.is_dir():
            files.extend(
                p
                for p in source.rglob("*")
                if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
            )
    return sorted(files)


def build_fingerprint(ipp_dir: Path, settings: Mapping[str, str]) -> str:
    """Hash the build scripts, CMake files, ``pixi.lock``, and *settings*."""
    digest = hashlib.sha256()
    for path in fingerprint_files(ipp_dir):
        digest.update(path.relative_to(ipp_dir).as_posix().encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")
    for key, value in sorted(settings.items()):
        digest.update(f"{key}={value}\n".encode())
    return digest.hexdigest()


def resolved_itk_commit(itk_source_dir: Path, fallback: str, git: str = "git") -> str:
    """Return the commit checked out in *itk_source_dir*, else *fallback*.

    A branch name is not enough: the same name builds a new commit each day.
    A tree restored from a build cache has no repository, hence the fallback.
    """
    env = os.environ.copy()
    # A cache-restored tree must not report an enclosing repository's commit.
    env["GIT_CEILING_DIRECTORIES"] = str(Path(itk_source_dir).resolve().parent)
    try:
        result = subprocess.run(
            [git, "rev-parse", "--verify", "HEAD^{commit}"],
            cwd=itk_source_dir,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return fallback
    return result.stdout.strip() if result.returncode == 0 else fallback


def build_inputs(
    itk_commit: str, package_version: str, fingerprint: str
) -> dict[str, str]:
    """Return the inputs recorded in the step report."""
    return {
        "itk_commit": itk_commit,
        "package_version": package_version,
        "fingerprint": fingerprint,
    }
