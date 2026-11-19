"""CMake definitions that discard unreferenced code and fold identical functions.

Mirrors ``SimpleITK_DEAD_STRIP`` (SimpleITK/SimpleITK#2784) for GNU toolchains
on ELF: every function and data object gets its own section, and gold drops
the sections nothing references (``--gc-sections``) and merges functions whose
address is never taken (``--icf=safe``).
"""

from __future__ import annotations

from collections.abc import Mapping

SECTION_FLAGS = "-ffunction-sections -fdata-sections"
LINKER_FLAGS = "-fuse-ld=gold -Wl,--gc-sections -Wl,--icf=safe"


def dead_strip_cmake_definitions(
    os_name: str, env: Mapping[str, str]
) -> dict[str, str]:
    """Return the ``-D`` definitions that enable dead stripping on *os_name*.

    Only Linux gets any: ld64 -dead_strip changed the macOS wheels by under
    0.1%, and MSVC Release links already discard and fold. Flags already in ``CFLAGS``/``CXXFLAGS``/
    ``LDFLAGS`` are kept, because a ``-DCMAKE_<LANG>_FLAGS`` definition
    replaces what CMake would have read from them.
    """
    if os_name != "linux":
        return {}

    def joined(var: str, extra: str) -> str:
        return f"{env.get(var, '')} {extra}".strip()

    linker = joined("LDFLAGS", LINKER_FLAGS)
    return {
        "CMAKE_C_FLAGS:STRING": joined("CFLAGS", SECTION_FLAGS),
        "CMAKE_CXX_FLAGS:STRING": joined("CXXFLAGS", SECTION_FLAGS),
        "CMAKE_SHARED_LINKER_FLAGS:STRING": linker,
        "CMAKE_MODULE_LINKER_FLAGS:STRING": linker,
        "CMAKE_EXE_LINKER_FLAGS:STRING": linker,
        # CMake detects GNU ld and passes it --dependency-file, which gold rejects.
        "CMAKE_LINK_DEPENDS_USE_LINKER:BOOL": "OFF",
    }
