from pathlib import Path
from os import environ as os_environ


def _which(exe_name: Path | str) -> Path | None:
    """Minimal PATH search using pathlib only.

    Returns the first matching executable path as a string, or None if not found.
    """
    # On Windows, honor PATHEXT
    pathext = os_environ.get("PATHEXT", ".EXE;.BAT;.CMD").split(";")
    paths = os_environ.get("PATH", "").split(";")
    candidates: list[Path] = []
    if Path(exe_name).suffix:
        candidates.append(Path(exe_name))
    else:
        for ext in pathext:
            candidates.append(Path(exe_name + ext))
    for p in paths:
        if not p:
            continue
        base = Path(p)
        for c in candidates:
            full = base / c
            try:
                if full.exists():
                    return full
            except OSError:
                # Skip unreadable entries
                continue
    return None
