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


#: What `uncommitted_changes` returns for a tree without changes.
NO_CHANGES: str = hashlib.sha256().hexdigest()


def uncommitted_changes(
    directory: Path,
    git: str,
    env: Mapping[str, str],
    skip: frozenset[str] = frozenset(),
) -> str:
    """Return a hash of the uncommitted changes in the repository at *directory*.

    It covers the changes to tracked files and the untracked files git does
    not ignore, except those under a top-level name in *skip* and those in a
    CMake build tree, a directory holding ``CMakeCache.txt``.
    """
    diff = subprocess.run(
        [git, "diff", "HEAD", "--binary"],
        cwd=directory,
        env=env,
        capture_output=True,
        check=True,
    )
    digest = hashlib.sha256(diff.stdout)
    untracked = subprocess.run(
        [git, "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=directory,
        env=env,
        capture_output=True,
        check=True,
    )
    names = sorted(os.fsdecode(n) for n in untracked.stdout.split(b"\0") if n)
    build_trees = tuple(
        name.removesuffix("CMakeCache.txt")
        for name in names
        if name.endswith("/CMakeCache.txt")
    )
    for name in names:
        if name.split("/")[0] in skip or name.startswith(build_trees):
            continue
        digest.update(os.fsencode(name) + b"\0")
        digest.update(_untracked_digest(Path(directory) / name, git, env))
    return digest.hexdigest()


def _untracked_digest(path: Path, git: str, env: Mapping[str, str]) -> bytes:
    """Return what identifies the content of the untracked *path*."""
    if path.is_symlink():
        return os.fsencode(path.readlink())
    if path.is_dir():
        # git lists a nested repository as one entry, "<name>/".
        head = subprocess.run(
            [git, "rev-parse", "--verify", "HEAD"],
            cwd=path,
            env=env,
            capture_output=True,
            check=False,
        )
        try:
            changes = uncommitted_changes(path, git, env)
        except subprocess.CalledProcessError as error:
            changes = type(error).__name__
        return head.stdout + changes.encode()
    try:
        with path.open("rb") as f:
            return hashlib.file_digest(f, "sha256").digest()
    except OSError as error:
        return type(error).__name__.encode()


def resolved_itk_commit(itk_source_dir: Path, fallback: str, git: str = "git") -> str:
    """Return the commit checked out in *itk_source_dir*, else *fallback*.

    A branch name is not enough: the same name builds a new commit each day.
    A tree restored from a build cache has no repository, hence the fallback.
    Uncommitted changes add ``+<hash>``, as they change what is built.
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
    if result.returncode != 0:
        return fallback
    commit = result.stdout.strip()
    try:
        changes = uncommitted_changes(itk_source_dir, git, env)
    except (OSError, subprocess.CalledProcessError):
        return commit
    return commit if changes == NO_CHANGES else f"{commit}+{changes}"


#: Names a module build writes into, or that hold caches, inside a module tree.
MODULE_STATE_SKIP: frozenset[str] = frozenset(
    {
        "build",
        "dist",
        "ITKPythonPackage",
        "ITKPythonPackage-build",
        "MODULE_DEPENDENCIES",
        "__pycache__",
        "pyproject.toml.orig",
        "pyproject.toml.built",
    }
)


def module_source_state(module_dir: Path, git: str = "git") -> str:
    """Return a remote module's git HEAD plus a hash of its uncommitted changes.

    Without a repository, return a hash of the module's files instead.
    """
    env = os.environ.copy()
    env["GIT_CEILING_DIRECTORIES"] = str(Path(module_dir).resolve().parent)
    try:
        head = subprocess.run(
            [git, "rev-parse", "--verify", "HEAD^{commit}"],
            cwd=module_dir,
            env=env,
            capture_output=True,
            check=False,
        )
        if head.returncode == 0:
            changes = uncommitted_changes(module_dir, git, env, MODULE_STATE_SKIP)
            return f"{head.stdout.decode().strip()}+{changes}"
    except (OSError, subprocess.CalledProcessError):
        pass
    digest = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(module_dir):
        dirnames[:] = sorted(
            d for d in dirnames if d not in MODULE_STATE_SKIP and not d.startswith(".")
        )
        for name in sorted(filenames):
            if name in MODULE_STATE_SKIP:
                continue
            path = Path(dirpath) / name
            digest.update(path.relative_to(module_dir).as_posix().encode() + b"\0")
            digest.update(path.read_bytes() + b"\0")
    return f"content:{digest.hexdigest()}"


def build_inputs(
    itk_commit: str,
    package_version: str,
    fingerprint: str,
    module_state: str | None = None,
) -> dict[str, str]:
    """Return the inputs recorded in the step report."""
    inputs = {
        "itk_commit": itk_commit,
        "package_version": package_version,
        "fingerprint": fingerprint,
    }
    if module_state is not None:
        inputs["module_state"] = module_state
    return inputs
