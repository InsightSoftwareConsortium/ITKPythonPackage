"""
Utilities to create macOS Python virtual environments for requested versions.

Key behavior:
- Searches for Python.framework versions under `/Library/Frameworks/Python.framework/Versions` by default
  (the standard location for python.org macOS installers).
- Accepts an explicit list of versions to target (e.g., ["3.9", "3.10", "3.11", "3.13"]).
- Creates virtual environments under `<dest_base_dir>/venvs/<major.minor>` using `python3 -m venv` from each
  discovered interpreter.
- Optionally cleans the `<dest_base_dir>/venvs` directory before creating new environments.

Example:
    from macos_venv_utils import create_macos_venvs

    venvs = create_macos_venvs(
        python_versions=["3.9", "3.10", "3.11", "3.13"],
        dest_base_dir="/path/to/build/root",
        cleanup=True,
    )
    print("Created:", venvs)

Note: On Apple Silicon systems that primarily use Homebrew, the python.org framework path may not exist for
      certain versions. You can provide additional prefixes to search with the `prefixes` parameter.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, List, Sequence

from wheel_builder_utils import run_commandLine_subprocess

DEFAULT_MACPYTHON_PREFIX = "/Library/Frameworks/Python.framework/Versions"


def _discover_python_versions(
    versions: Sequence[str] | None,
    prefixes: Sequence[str] | None,
) -> List[Path]:
    """Return a list of Python.framework version directories matching requested versions.

    - If `versions` is None or empty, return all versions found under the prefixes.
    - Otherwise, match any directory whose basename contains the version string (e.g., "*3.10*").
    - Excludes directories named "Current".
    """
    if prefixes is None or len(prefixes) == 0:
        prefixes = [DEFAULT_MACPYTHON_PREFIX]

    found: list[Path] = []

    def add_unique(paths: Iterable[Path]) -> None:
        existing = set(p.resolve() for p in found)
        for p in paths:
            rp = p.resolve()
            if rp not in existing and rp.exists() and rp.is_dir():
                found.append(rp)
                existing.add(rp)

    if not versions:
        for pref in prefixes:
            add_unique(Path(d) for d in glob.glob(os.path.join(pref, "*")))
    else:
        for pref in prefixes:
            for ver in versions:
                pattern = os.path.join(pref, f"*{ver}*")
                add_unique(Path(d) for d in glob.glob(pattern))

    # Filter out "Current" and non-directories
    result = [p for p in found if p.name != "Current" and p.is_dir()]
    # Sort for stable output by version-like name
    result.sort(key=lambda p: p.name)
    return result


def create_macos_venvs(
    python_versions: Sequence[str] | str | None,
    venvs_root: os.PathLike | str,
    *,
    prefixes: Sequence[str] | None = None,
    cleanup: bool = False,
) -> List[Path]:
    """Create virtual environments for the requested macOS Python versions.
    NOTE:  creating venvs from within a debugger has caused errors during the "ensurepip"
           stage of creating the virtual environment.  Using this script outside the debugger
           to pre-populate the virtual environment before starting the debugger has been
           a convenient work-around.

    Parameters
    ----------
    python_versions
        A sequence of version identifiers (e.g., ["3.9", "3.10"]). If None or empty, all versions under
        the provided prefixes are used.
    venvs_root
        The venv base directory where `{venvs_root}/{python_version}/bin/python3` will be created.
    prefixes
        Optional list of prefixes to search for Python.framework versions. If not provided, defaults to
        [`/Library/Frameworks/Python.framework/Versions`]. You can supply additional prefixes (e.g., custom
        installs) if desired.
    cleanup
        When True, remove the existing `<dest_base_dir>/venvs` directory before creating new environments.

    Returns
    -------
    list[pathlib.Path]
        The list of created virtual environment directories.

    Raises
    ------
    FileNotFoundError
        If no matching Python versions are discovered.
    RuntimeError
        If creating any virtual environment fails.
    """
    if isinstance(python_versions, str):
        python_versions: Sequence[str] = python_versions.split()

    venvs_root = Path(venvs_root).expanduser().resolve()

    if cleanup and venvs_root.exists():
        shutil.rmtree(venvs_root)

    venvs_root.mkdir(parents=True, exist_ok=True)

    py_dirs = _discover_python_versions(python_versions, prefixes)
    if not py_dirs:
        ver_desc = ", ".join(python_versions) if python_versions else "<all>"
        pref_desc = ", ".join(prefixes or [DEFAULT_MACPYTHON_PREFIX])
        raise FileNotFoundError(
            f"No macOS Python.framework versions found for versions [{ver_desc}] under prefixes [{pref_desc}]"
        )

    created_penv: list[Path] = []
    failures: list[tuple[Path, str]] = []

    for py_dir in py_dirs:
        py_mm = py_dir.name  # e.g., "3.13"
        venv_dir = venvs_root / py_mm
        python_exec = py_dir / "bin" / "python3"

        # If an environment already exists, skip recreating it.
        if venv_dir.exists():
            created_penv.append(venv_dir)
            continue

        if not python_exec.exists():
            failures.append((py_dir, f"Missing interpreter: {python_exec}"))
            continue

        # NOTE: unsetting PYTHONHOME and PYTHONPATH
        pop_pythonhome = os.environ.pop("PYTHONHOME", None)
        pop_pythonpath = os.environ.pop("PYTHONPATH", None)
        try:
            cmd = [str(python_exec), "-m", "venv", str(venv_dir)]
            print(f"Creating venv {venv_dir}: {' '.join(cmd)}")

            result: subprocess.CompletedProcess = run_commandLine_subprocess(
                cmd,
                check=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Failed to create venv {venv_dir}: {result.stderr}")
            created_penv.append(venv_dir)
        except subprocess.CalledProcessError as e:
            failures.append((py_dir, e.stderr.decode("utf-8", errors="replace")))
        if pop_pythonhome is not None:
            os.environ["PYTHONHOME"] = pop_pythonhome
        if pop_pythonpath is not None:
            os.environ["PYTHONPATH"] = pop_pythonpath

    if failures and not created_penv:
        # If everything failed, raise with a helpful message
        details = "\n".join(f"- {p}: {msg}" for p, msg in failures)
        raise RuntimeError(f"Failed to create any virtual environments:\n{details}")

    return created_penv


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Create macOS virtualenvs for specified Python.framework versions."
    )
    parser.add_argument(
        "venvs_root",
        help="Destination base directory; venvs will be created inside '<venvs_root>/<major.minor>'.",
    )
    parser.add_argument(
        "versions",
        nargs="*",
        help="Version filters like 3.9 3.10 3.11 3.13. If omitted, all versions under the prefix are used.",
    )
    parser.add_argument(
        "--prefix",
        action="append",
        dest="prefixes",
        default=None,
        help=(
            "Search prefix for Python.framework versions; may be specified multiple times. "
            f"Defaults to {DEFAULT_MACPYTHON_PREFIX}."
        ),
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove the existing 'venvs' directory under dest_base_dir before creating new ones.",
    )

    args = parser.parse_args()
    created_venvs = create_macos_venvs(
        python_versions=args.versions,
        venvs_root=args.venvs_root,
        prefixes=args.prefixes,
        cleanup=bool(args.cleanup),
    )
    for venv in created_venvs:
        print(venv)


if __name__ == "__main__":
    main()
