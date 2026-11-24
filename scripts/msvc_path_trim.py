"""Keep the build directories out of the ``__FILE__`` strings MSVC compiles.

``-d1trimfile:<root>/`` makes ``__FILE__`` relative to the checkout, the
build root, and the ITK source. With ``SCCACHE_BASEDIRS`` a build hits
objects another directory compiled, so without the trim the wheels would
name that other build's directories.

The flags are CMake definitions rather than ``CFLAGS``: CMake reads the
environment only when it first creates the cache, and a reused build tree
keeps its cache.
"""

from __future__ import annotations

from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING

from compiler_flags import FLAG_SOURCES, user_flag_key

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from cmake_argument_builder import CMakeArgumentBuilder

# CMake's MSVC defaults (CMP0117 NEW), which a CMAKE_<LANG>_FLAGS definition replaces.
MSVC_DEFAULT_FLAGS = {
    "CMAKE_C_FLAGS": "/DWIN32 /D_WINDOWS",
    "CMAKE_CXX_FLAGS": "/DWIN32 /D_WINDOWS /EHsc",
}


def msvc_trim_prefixes(roots: Iterable[Path | str]) -> list[str]:
    """Return each root as an absolute ``X:/dir/`` prefix, longest first.

    MSVC matches the prefix with either slash. A backslash would be read as an
    escape where CMake writes the flags into a package config, as DCMTK does.
    """
    prefixes = set()
    for root in roots:
        path = PureWindowsPath(root)
        if not path.is_absolute():
            path = PureWindowsPath(Path(root).resolve())
        prefixes.add(path.as_posix().rstrip("/") + "/")
    # CMake splits flags on spaces, so a root containing one cannot be passed.
    return sorted((p for p in prefixes if " " not in p), key=len, reverse=True)


def msvc_trim_definitions(
    env: Mapping[str, str],
    user_defs: Mapping[str, str] | CMakeArgumentBuilder,
    roots: Iterable[Path | str],
) -> dict[str, str]:
    """Return ``CMAKE_C_FLAGS`` and ``CMAKE_CXX_FLAGS`` with the roots trimmed.

    Each starts from the user's ``-D`` value, else from ``CFLAGS``/``CXXFLAGS``
    and CMake's defaults, as CMake itself would. A value that already trims
    is left alone.
    """
    # sccache reads an unknown /option as a second input file; -option is cached.
    trims = " ".join(f"-d1trimfile:{p}" for p in msvc_trim_prefixes(roots))
    if not trims:
        return {}
    definitions = {}
    for cmake_var, default in MSVC_DEFAULT_FLAGS.items():
        key = user_flag_key(user_defs, cmake_var)
        if key:
            base = user_defs[key]
        else:
            base = f"{env.get(FLAG_SOURCES[cmake_var], '')} {default}".strip()
        if "d1trimfile:" not in base:
            definitions[f"{cmake_var}:STRING"] = f"{base} {trims}"
    return definitions
