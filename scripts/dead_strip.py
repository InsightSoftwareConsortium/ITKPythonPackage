"""CMake definitions that discard unreferenced code from Linux wheels.

Mirrors ``SimpleITK_DEAD_STRIP`` (SimpleITK/SimpleITK#2784): every function
and data object gets its own section, the linker drops the sections nothing
references (``--gc-sections``), and Python extension modules export only
``PyInit_*``, as SimpleITK's module does. Without the version script, every
symbol of the statically linked ITK libraries stays exported and cannot be
discarded.

Measured with manylinux_2_28 (GCC 14.2, GNU ld 2.41): identical code folding
(gold ``--icf=safe``) saved nothing beyond this, so the image's default
linker is used and gold, deprecated since binutils 2.44, is not required.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

SECTION_FLAGS = "-ffunction-sections -fdata-sections"
LINKER_FLAGS = "-Wl,--gc-sections"
PYTHON_MODULE_EXPORTS = (
    Path(__file__).resolve().parent.parent
    / "BuildWheelsSupport"
    / "python_module_exports.map"
)


def dead_strip_cmake_definitions(
    os_name: str, env: Mapping[str, str]
) -> dict[str, str]:
    """Return the ``-D`` definitions that enable dead stripping on *os_name*.

    Only Linux gets any: ld64 -dead_strip changed the macOS wheels by under
    0.1%, and MSVC Release links already discard and fold. Flags already in
    ``CFLAGS``/``CXXFLAGS``/``LDFLAGS`` are kept, because a
    ``-DCMAKE_<LANG>_FLAGS`` definition replaces what CMake would have read
    from them.
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
        "CMAKE_MODULE_LINKER_FLAGS:STRING": (
            f"{linker} -Wl,--version-script={PYTHON_MODULE_EXPORTS.as_posix()}"
        ),
        "CMAKE_EXE_LINKER_FLAGS:STRING": linker,
    }
