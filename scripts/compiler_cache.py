"""Choose and configure the compiler cache a build compiles through.

A cache hit returns the object the compiler produced for the same
preprocessed source, compiler, and flags, so the cache changes build time
only, never the wheels.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

# A wrapped ITK build overflows ccache's 5 GB default and evicts its own objects.
DEFAULT_MAX_SIZE = "30G"

_SIZE_VARIABLE = {"ccache": "CCACHE_MAXSIZE", "sccache": "SCCACHE_CACHE_SIZE"}


_TRUE_VALUES = ("1", "ON", "TRUE", "YES")


def use_compiler_cache(flag: bool | None, env: Mapping[str, str]) -> bool:
    """Return whether to cache: an explicit flag wins over the environment."""
    if flag is not None:
        return flag
    value = env.get("USE_COMPILER_CACHE") or env.get("USE_CCACHE") or "0"
    return value.upper() in _TRUE_VALUES


def compiler_cache_tool(os_name: str) -> str:
    """Return the cache program for *os_name*: sccache on Windows, else ccache."""
    return "sccache" if os_name == "windows" else "ccache"


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


def compiler_cache_environment(tool: str, env: Mapping[str, str]) -> dict[str, str]:
    """Return environment settings to add for *tool*; a size in *env* wins."""
    variable = _SIZE_VARIABLE[tool]
    if env.get(variable):
        return {}
    return {variable: DEFAULT_MAX_SIZE}
