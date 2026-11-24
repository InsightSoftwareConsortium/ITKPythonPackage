"""CMake definitions that discard unreferenced code from Linux and macOS wheels.

Mirrors ``SimpleITK_DEAD_STRIP`` (SimpleITK/SimpleITK#2784): unreferenced code
is dropped at link time, and Python extension modules export only
``PyInit_*``, as SimpleITK's module does. Without the export limit, every
symbol of the statically linked ITK libraries stays exported and cannot be
discarded, on either platform.

Linux: every function and data object gets its own section, the linker drops
the sections nothing references (``--gc-sections``), and a version script
limits exports. Measured with manylinux_2_28 (GCC 14.2, GNU ld 2.41),
identical code folding (gold ``--icf=safe``) saved nothing beyond this, so the
image's default linker is used and gold, deprecated since binutils 2.44, is
not required.

macOS: ld64 already splits code per symbol and deduplicates, so only
``-dead_strip`` and ``-exported_symbol,_PyInit_*`` are needed, and only on the
Python modules. ``-dead_strip`` alone changed the wheels by under 0.1%.
These are linker decisions: GCC on macOS links with ld64 too.

Windows needs nothing: MSVC exports only ``dllexport`` symbols, and Release
links already use ``/OPT:REF`` and ``/OPT:ICF``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from compiler_flags import environment_flag
from target_platform import OS

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cmake_argument_builder import CMakeArgumentBuilder

SECTION_FLAGS = "-ffunction-sections -fdata-sections"
LINKER_FLAGS = "-Wl,--gc-sections"
DARWIN_MODULE_FLAGS = "-Wl,-dead_strip -Wl,-exported_symbol,_PyInit_*"
PYTHON_MODULE_EXPORTS = (
    Path(__file__).resolve().parent.parent
    / "BuildWheelsSupport"
    / "python_module_exports.map"
)


def dead_strip_cmake_definitions(
    os_name: OS,
    env: Mapping[str, str],
    user_defs: Mapping[str, str] | CMakeArgumentBuilder | None = None,
) -> dict[str, str]:
    """Return the ``-D`` definitions that enable dead stripping on *os_name*.

    Windows gets none. Each flag variable starts from the user's own ``-D``
    value when one was given, otherwise from ``CFLAGS``/``CXXFLAGS``/
    ``LDFLAGS``, so neither the user's flags nor these are lost.
    """
    if os_name not in (OS.LINUX, OS.DARWIN):
        return {}
    user_defs = user_defs or {}

    def joined(cmake_var: str, extra: str) -> str:
        return f"{environment_flag(cmake_var, env, user_defs)} {extra}".strip()

    if os_name is OS.DARWIN:
        return {
            "CMAKE_MODULE_LINKER_FLAGS:STRING": joined(
                "CMAKE_MODULE_LINKER_FLAGS", DARWIN_MODULE_FLAGS
            ),
        }
    module_extra = (
        f"{LINKER_FLAGS} -Wl,--version-script={PYTHON_MODULE_EXPORTS.as_posix()}"
    )
    return {
        "CMAKE_C_FLAGS:STRING": joined("CMAKE_C_FLAGS", SECTION_FLAGS),
        "CMAKE_CXX_FLAGS:STRING": joined("CMAKE_CXX_FLAGS", SECTION_FLAGS),
        "CMAKE_SHARED_LINKER_FLAGS:STRING": joined(
            "CMAKE_SHARED_LINKER_FLAGS", LINKER_FLAGS
        ),
        "CMAKE_MODULE_LINKER_FLAGS:STRING": joined(
            "CMAKE_MODULE_LINKER_FLAGS", module_extra
        ),
        "CMAKE_EXE_LINKER_FLAGS:STRING": joined("CMAKE_EXE_LINKER_FLAGS", LINKER_FLAGS),
    }
