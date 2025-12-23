"""
Utilities to create Linux Python virtual environments for requested versions.

Key behavior:
- Searches for Python executables on PATH (e.g., `python3.9`, `python3.10`, ...).
- Optionally searches additional prefixes for `bin/python3.X` (e.g., `/usr/local`, `/opt`, custom prefixes).
- Creates virtual environments under `<venvs_root>/<major.minor>` using `python -m venv` from each
  discovered interpreter.
- Optionally cleans the `<venvs_root>` directory before creating new environments.

Example:
    from linux_venv_utils import create_linux_venvs

    venvs = create_linux_venvs(
        python_versions=["3.9", "3.10", "3.11", "3.12", "3.13", "3.14"],
        venvs_root="/path/to/build/root/venvs",
        cleanup=True,
    )
    print("Created:", venvs)

Note: Creating venvs from within a debugger sometimes causes errors during the "ensurepip" stage.
      Running this script outside the debugger to pre-create environments can avoid that.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Mapping, Sequence

try:
    from shutil import which  # type: ignore
except Exception:  # pragma: no cover
    # very old Python compatibility; not expected to be needed
    def which(cmd: str) -> str | None:  # type: ignore[override]
        return None


DEFAULT_LINUX_PREFIXES: tuple[str, ...] = (
    "/usr/local",
    "/usr",
    "/opt",
)

# Default set the user asked for
DEFAULT_PYTHON_VERSIONS: tuple[str, ...] = (
    "3.9",
    "3.10",
    "3.11",
    "3.12",
    "3.13",
    "3.14",
)


def _candidate_exec_names(ver: str) -> tuple[str, ...]:
    # Prefer exact minor version executables where available
    return (f"python{ver}", f"python{ver.replace('.', '')}")


def _discover_python_executables(
    versions: Sequence[str] | None,
    prefixes: Sequence[str] | None,
) -> Mapping[str, Path]:
    """Find Python executables for the requested versions.

    Returns a mapping {"3.12": Path("/usr/bin/python3.12"), ...} for those that exist.

    Strategy:
    - If versions is None/empty, use DEFAULT_PYTHON_VERSIONS.
    - For each version, first check PATH via shutil.which for common executable names.
    - Then check each provided prefix (or DEFAULT_LINUX_PREFIXES) for `bin/python{ver}`.
    """
    if not versions:
        versions = list(DEFAULT_PYTHON_VERSIONS)

    if prefixes is None or len(prefixes) == 0:
        prefixes = list(DEFAULT_LINUX_PREFIXES)

    found: dict[str, Path] = {}

    for ver in versions:
        # 1) PATH search
        for cand in _candidate_exec_names(ver):
            exe = which(cand)
            if exe:
                p = Path(exe)
                if p.exists() and os.access(p, os.X_OK):
                    found[ver] = p.resolve()
                    break
        if ver in found:
            continue

        # 2) Prefixes search
        for pref in prefixes:
            for candidate in (f"bin/python{ver}", f"bin/python{ver.replace('.', '')}"):
                p = Path(pref) / candidate
                if p.exists() and p.is_file() and os.access(p, os.X_OK):
                    found[ver] = p.resolve()
                    break
            if ver in found:
                break

    return found


def create_linux_venvs(
    python_versions: Sequence[str] | str | None,
    venvs_root: os.PathLike | str,
    *,
    prefixes: Sequence[str] | None = None,
    cleanup: bool = False,
) -> List[Path]:
    """Create virtual environments for requested Linux Python versions.

    Parameters
    ----------
    python_versions
        Sequence like ["3.9", "3.10"]. If None/empty, defaults to 3.9–3.14.
        A space-separated string is also accepted.
    venvs_root
        The venv base directory where `{venvs_root}/{python_version}/bin/python` will be created.
    prefixes
        Optional list of prefixes to search for executables (looked up under `<prefix>/bin`).
        Defaults to [`/usr/local`, `/usr`, `/opt`].
    cleanup
        When True, remove the existing `<venvs_root>` directory before creating new environments.

    Returns
    -------
    list[pathlib.Path]
        The list of created (or already existing) virtual environment directories.

    Raises
    ------
    FileNotFoundError
        If no matching Python versions are discovered.
    RuntimeError
        If creating any virtual environment fails and none succeeded.
    """
    if isinstance(python_versions, str):
        python_versions = python_versions.split()

    venvs_root = Path(venvs_root).expanduser().resolve()

    if cleanup and venvs_root.exists():
        shutil.rmtree(venvs_root)

    venvs_root.mkdir(parents=True, exist_ok=True)

    exe_map = _discover_python_executables(python_versions, prefixes)
    if not exe_map:
        ver_desc = (
            ", ".join(python_versions or [])
            if python_versions
            else ", ".join(DEFAULT_PYTHON_VERSIONS)
        )
        pref_desc = ", ".join(prefixes or list(DEFAULT_LINUX_PREFIXES))
        raise FileNotFoundError(
            f"No Linux Python executables found for versions [{ver_desc}] under prefixes/paths [{pref_desc}] or PATH"
        )

    created_venvs: list[Path] = []
    failures: list[tuple[str, str]] = []

    # Process in version order for stable results
    for ver in sorted(exe_map.keys(), key=lambda s: [int(x) for x in s.split(".")]):
        python_exec = exe_map[ver]
        venv_dir = venvs_root / ver

        if (venv_dir / "bin" / "python3").exists():
            created_venvs.append(venv_dir)
            continue

        if not python_exec.exists():
            failures.append((ver, f"Missing interpreter: {python_exec}"))
            continue

        # NOTE: unsetting PYTHONHOME and PYTHONPATH
        pop_pythonhome = os.environ.pop("PYTHONHOME", None)
        pop_pythonpath = os.environ.pop("PYTHONPATH", None)
        try:
            cmd = [str(python_exec), "-m", "venv", str(venv_dir)]
            print(f"Creating venv {venv_dir}: {' '.join(cmd)}")

            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            created_venvs.append(venv_dir)
        except subprocess.CalledProcessError as e:
            failures.append((ver, e.stderr.decode("utf-8", errors="replace")))
        finally:
            if pop_pythonhome is not None:
                os.environ["PYTHONHOME"] = pop_pythonhome
            if pop_pythonpath is not None:
                os.environ["PYTHONPATH"] = pop_pythonpath

    if failures and not created_venvs:
        details = "\n".join(f"- Python {ver}: {msg}" for ver, msg in failures)
        raise RuntimeError(f"Failed to create any virtual environments:\n{details}")

    return created_venvs


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Create Linux virtualenvs for specified Python versions if interpreters are available."
    )
    parser.add_argument(
        "venvs_root",
        help="Destination base directory; venvs will be created inside '<venvs_root>/<major.minor>'.",
    )
    parser.add_argument(
        "versions",
        nargs="*",
        help=(
            "Version filters like 3.9 3.10 3.11 3.12 3.13 3.14. If omitted, defaults to 3.9–3.14; "
            "only versions with available interpreters are created."
        ),
    )
    parser.add_argument(
        "--prefix",
        action="append",
        dest="prefixes",
        default=None,
        help=(
            "Additional search prefix for executables; may be specified multiple times. "
            f"Defaults to: {', '.join(DEFAULT_LINUX_PREFIXES)}."
        ),
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove the existing '<venvs_root>' directory before creating new ones.",
    )

    args = parser.parse_args()
    created_venvs = create_linux_venvs(
        python_versions=args.versions,
        venvs_root=args.venvs_root,
        prefixes=args.prefixes,
        cleanup=bool(args.cleanup),
    )
    for venv in created_venvs:
        print(venv)


if __name__ == "__main__":
    main()
