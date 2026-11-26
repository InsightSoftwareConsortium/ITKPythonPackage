"""Keep a remote module wheel from replacing ITK's ``itk/__init__.py``.

delvewheel writes its DLL search setup into the wheel's ``itk/__init__.py``,
which on install would overwrite the one from ``itk-core``. ITK's own
``__init__`` runs ``itk/__init_<module>__.py`` for each module instead, so a
module's init lives under that name except while delvewheel patches it.
"""

from __future__ import annotations

import email.parser
import re
import zipfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

ITK_INIT = "itk/__init__.py"
_CONFIG = re.compile(r"^itk/Configuration/(?P<module>[^/]+)Config\.py$")


def module_init_name(wheel: Path) -> str:
    """Return the ``itk/__init_<module>__.py`` member ITK runs for *wheel*."""
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        modules = sorted(m["module"] for n in names if (m := _CONFIG.match(n)))
        if modules:
            return f"itk/__init_{modules[0].lower()}__.py"
        metadata = next(n for n in names if n.endswith(".dist-info/METADATA"))
        name = email.parser.Parser().parsestr(zf.read(metadata).decode())["Name"]
    module = name.lower().removeprefix("itk-").split("-")[0]
    return f"itk/__init_{module}__.py"


def rename_wheel_member(wheel: Path, old: str, new: str) -> bool:
    """Rename member *old* to *new* in *wheel*, RECORD included; False if absent."""
    with zipfile.ZipFile(wheel) as zf:
        infos = zf.infolist()
        if old not in {i.filename for i in infos}:
            return False
        contents = [(i, zf.read(i)) for i in infos]
    tmp = wheel.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
        for info, data in contents:
            if info.filename == old:
                info.filename = new
            if info.filename.endswith(".dist-info/RECORD"):
                out.writestr(info, _renamed_record(data, old, new))
            else:
                out.writestr(info, data)
    tmp.replace(wheel)
    return True


def _renamed_record(record: bytes, old: str, new: str) -> bytes:
    lines = record.decode().splitlines(keepends=True)
    return "".join(
        new + line[len(old) :] if line.startswith(old + ",") else line for line in lines
    ).encode()
