"""Choose and configure the compiler cache a build compiles through.

A cache hit returns the object the compiler produced for the same
preprocessed source, compiler, and flags, so the cache changes build time
only, never the wheels.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from target_platform import OS

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

# A wrapped ITK build overflows ccache's 5 GB default and evicts its own objects.
DEFAULT_MAX_SIZE = "30G"

_SIZE_VARIABLE = {"ccache": "CCACHE_MAXSIZE", "sccache": "SCCACHE_CACHE_SIZE"}

# 0 keeps one sccache server for the whole build; an idle restart zeroes its statistics.
_SCCACHE_IDLE_TIMEOUT = "SCCACHE_IDLE_TIMEOUT"


# Paths under these directories are hashed relative to them, so a cache filled
# from one checkout or build root hits from another.
_BASE_DIR_VARIABLE = {"ccache": "CCACHE_BASEDIR", "sccache": "SCCACHE_BASEDIRS"}

_TRUE_VALUES = ("1", "ON", "TRUE", "YES")


def use_compiler_cache(flag: bool | None, env: Mapping[str, str]) -> bool:
    """Return whether to cache: an explicit flag wins over the environment."""
    if flag is not None:
        return flag
    value = env.get("USE_COMPILER_CACHE") or env.get("USE_CCACHE") or "0"
    return value.upper() in _TRUE_VALUES


def compiler_cache_tool(os_name: OS) -> str:
    """Return the cache program for *os_name*: sccache on Windows, else ccache."""
    return "sccache" if os_name is OS.WINDOWS else "ccache"


def compiler_cache_definitions(tool: str, launcher: Path | str) -> dict[str, str]:
    """Return the CMake definitions that compile C and C++ through *launcher*.

    ITK also runs CastXML and SWIG through the launcher when ITK_USE_CCACHE is
    on, which it defaults to whenever a launcher is set. ccache caches those
    steps; sccache rejects programs it does not know as compilers.
    """
    return {
        "CMAKE_C_COMPILER_LAUNCHER:FILEPATH": str(launcher),
        "CMAKE_CXX_COMPILER_LAUNCHER:FILEPATH": str(launcher),
        "ITK_USE_CCACHE:BOOL": "ON" if tool == "ccache" else "OFF",
    }


def compiler_cache_base_dirs(tool: str, roots: Iterable[Path | str]) -> str | None:
    """Return *tool*'s base directory setting: ccache's common parent, sccache's list.

    None without roots, or when the common parent is a filesystem root.
    """
    paths = sorted({Path(os.path.abspath(root)) for root in roots})  # noqa: PTH100
    if not paths:
        return None
    if tool == "sccache":
        # Longest first, so a nested root is matched before its parent.
        by_depth = sorted(paths, key=lambda path: len(str(path)), reverse=True)
        return os.pathsep.join(str(path) for path in by_depth)
    try:
        common = Path(os.path.commonpath(paths))
    except ValueError:  # different drives
        return None
    return None if common == Path(common.anchor) else str(common)


def compiler_cache_environment(
    tool: str, env: Mapping[str, str], roots: Iterable[Path | str] = ()
) -> dict[str, str]:
    """Return environment settings to add for *tool*; a value in *env* wins.

    *roots* are the directories whose paths reach the compiler: the
    checkout, the build root, and the ITK source.
    """
    added = {_SIZE_VARIABLE[tool]: DEFAULT_MAX_SIZE}
    if tool == "sccache":
        added[_SCCACHE_IDLE_TIMEOUT] = "0"
    base_dirs = compiler_cache_base_dirs(tool, roots)
    if base_dirs is not None:
        added[_BASE_DIR_VARIABLE[tool]] = base_dirs
    return {name: value for name, value in added.items() if not env.get(name)}


def compiler_cache_max_size(tool: str, env: Mapping[str, str]) -> str:
    """Return the cache size limit in effect for *tool* under *env*."""
    return env.get(_SIZE_VARIABLE[tool]) or DEFAULT_MAX_SIZE


def ccache_size_bytes(size: str) -> float | None:
    """Return a ccache size such as ``30G`` or ``75.0 GB`` in bytes; a bare number is GiB."""
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:([kKMGT])(i?)B?)?\s*", size)
    if match is None:
        return None
    number, unit, binary = match.groups()
    if unit is None:
        return float(number) * 1024**3
    base = 1024.0 if binary else 1000.0
    return float(number) * base ** ("KMGT".index(unit.upper()) + 1)


def compiler_cache_size_setting(
    tool: str, launcher: Path | str, env: Mapping[str, str]
) -> dict[str, str]:
    """Return a size setting that keeps a larger limit ccache is configured with.

    ``CCACHE_MAXSIZE`` overrides the cache's own ccache.conf, so the default
    would trim a larger cache during the build.
    """
    if tool != "ccache" or env.get(_SIZE_VARIABLE[tool]):
        return {}
    result = subprocess.run(
        [str(launcher), "--get-config", "max_size"],
        capture_output=True,
        text=True,
        check=False,
        env=dict(env),
    )
    configured = result.stdout.strip()
    configured_bytes = ccache_size_bytes(configured) if result.returncode == 0 else None
    default_bytes = ccache_size_bytes(DEFAULT_MAX_SIZE) or 0
    if configured_bytes is None or configured_bytes <= default_bytes:
        return {}
    return {_SIZE_VARIABLE[tool]: configured}


def compiler_cache_session(
    tool: str, launcher: Path | str, max_size: str
) -> tuple[list[list[str]], list[list[str]]]:
    """Return the commands to run before and after a build.

    ccache saves *max_size* in the cache directory's ccache.conf, so a later
    ccache call outside the build keeps the limit rather than trimming the
    cache to its 5 GB default. sccache has no per-directory setting; its size
    comes from the environment only. Statistics are zeroed first so the
    report covers this build alone. The sccache server keeps the environment
    it started with, so it is restarted after the cache size is set and
    stopped at the end.
    """
    exe = str(launcher)
    if tool == "sccache":
        before = [
            [exe, "--stop-server"],
            [exe, "--start-server"],
            [exe, "--zero-stats"],
        ]
        after = [[exe, "--show-stats"], [exe, "--stop-server"]]
    else:
        before = [[exe, "--max-size", max_size], [exe, "--zero-stats"]]
        after = [[exe, "--show-stats", "--verbose"]]
    return before, after
