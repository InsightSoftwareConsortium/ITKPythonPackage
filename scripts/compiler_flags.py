"""CMake flag variables, initialized from the environment as CMake would.

CMake reads ``CFLAGS``, ``CXXFLAGS``, and ``LDFLAGS`` only when it creates a
cache, so a reused build tree would keep the flags of its first configure.
Passing the variables as definitions keeps them in step with the environment
and makes them part of the build's fingerprint.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cmake_argument_builder import CMakeArgumentBuilder

# CMake variable -> environment variable CMake would otherwise read it from.
FLAG_SOURCES = {
    "CMAKE_C_FLAGS": "CFLAGS",
    "CMAKE_CXX_FLAGS": "CXXFLAGS",
    "CMAKE_SHARED_LINKER_FLAGS": "LDFLAGS",
    "CMAKE_MODULE_LINKER_FLAGS": "LDFLAGS",
    "CMAKE_EXE_LINKER_FLAGS": "LDFLAGS",
}


def user_flag_key(
    user_defs: Mapping[str, str] | CMakeArgumentBuilder, cmake_var: str
) -> str | None:
    """Return the key under which *user_defs* sets *cmake_var*, typed or not."""
    for key in (f"{cmake_var}:STRING", cmake_var):
        if key in user_defs:
            return key
    return None


def environment_flag(
    cmake_var: str,
    env: Mapping[str, str],
    user_defs: Mapping[str, str] | CMakeArgumentBuilder,
) -> str:
    """Return *cmake_var*: the user's ``-D`` value, else its environment variable."""
    key = user_flag_key(user_defs, cmake_var)
    return user_defs[key] if key else env.get(FLAG_SOURCES[cmake_var], "")


def environment_flag_definitions(
    env: Mapping[str, str], user_defs: Mapping[str, str] | CMakeArgumentBuilder
) -> dict[str, str]:
    """Return every flag variable for a compiler whose CMake defaults are empty."""
    return {
        f"{cmake_var}:STRING": environment_flag(cmake_var, env, user_defs)
        for cmake_var in FLAG_SOURCES
    }
