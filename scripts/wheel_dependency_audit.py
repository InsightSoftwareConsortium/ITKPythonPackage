#!/usr/bin/env python3
"""Check that each ITK wheel requires the wheels its wrapped modules import.

    python scripts/wheel_dependency_audit.py <dir-or-wheels>...

Every wrapped module ships ``itk/Configuration/<Module>Config.py``, whose
``depends`` tuple names the modules it loads. A wheel whose modules depend on
a module in another wheel must require that wheel, directly or through the
wheels it requires; otherwise ``pip install <wheel>`` gives an ``itk`` that
raises ``KeyError`` on first use. Exits 1 and lists each gap.
"""

from __future__ import annotations

import ast
import re
import sys
import zipfile
from dataclasses import dataclass, field
from email.parser import Parser
from pathlib import Path

_CONFIG = re.compile(r"^itk/Configuration/(?P<module>[^/]+)Config\.py$")
_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalize(name: str) -> str:
    """Return the PEP 503 normalized form of a distribution name."""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass
class WheelContents:
    """Distribution name, required distributions, and wrapped modules."""

    name: str
    requires: set[str] = field(default_factory=set)
    modules: dict[str, tuple[str, ...]] = field(default_factory=dict)


def _module_depends(source: str) -> tuple[str, ...]:
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "depends" for t in node.targets
        ):
            return tuple(ast.literal_eval(node.value))
    return ()


def read_wheel(path: Path) -> WheelContents:
    """Read the metadata and module ``depends`` tuples of the wheel at *path*."""
    with zipfile.ZipFile(path) as whl:
        names = whl.namelist()
        metadata_name = next(n for n in names if n.endswith(".dist-info/METADATA"))
        metadata = Parser().parsestr(whl.read(metadata_name).decode())
        contents = WheelContents(normalize(metadata["Name"]))
        for requirement in metadata.get_all("Requires-Dist") or []:
            if ";" in requirement and "extra ==" in requirement:
                continue
            match = _REQUIREMENT_NAME.match(requirement)
            if match:
                contents.requires.add(normalize(match.group(1)))
        for name in names:
            match = _CONFIG.match(name)
            if match:
                source = whl.read(name).decode()
                contents.modules[match.group("module")] = _module_depends(source)
    return contents


def _closure(name: str, wheels: dict[str, WheelContents]) -> set[str]:
    seen: set[str] = set()
    pending = [name]
    while pending:
        current = pending.pop()
        for required in wheels[current].requires if current in wheels else ():
            if required not in seen:
                seen.add(required)
                pending.append(required)
    return seen


def audit(contents: list[WheelContents]) -> list[str]:
    """Return one message per missing wheel requirement or unowned module."""
    wheels = {c.name: c for c in contents}
    owner: dict[str, str] = {}
    problems: list[str] = []
    for wheel in contents:
        for module in wheel.modules:
            if module in owner:
                problems.append(f"{module} is in both {owner[module]} and {wheel.name}")
            owner.setdefault(module, wheel.name)
    for wheel in contents:
        reachable = _closure(wheel.name, wheels)
        missing: dict[str, set[str]] = {}
        for module, depends in sorted(wheel.modules.items()):
            for dep in depends:
                provider = owner.get(dep)
                if provider is None:
                    problems.append(
                        f"{wheel.name}: {module} depends on {dep}, which no wheel provides"
                    )
                elif provider != wheel.name and provider not in reachable:
                    missing.setdefault(provider, set()).add(f"{module} -> {dep}")
        for provider, edges in sorted(missing.items()):
            problems.append(
                f"{wheel.name} must require {provider}: " + ", ".join(sorted(edges))
            )
    return problems


def wheels_in(paths: list[Path]) -> list[Path]:
    """Expand directories in *paths* to the ``itk*.whl`` files they hold."""
    found: list[Path] = []
    for path in paths:
        found.extend(sorted(path.glob("itk*.whl")) if path.is_dir() else [path])
    return found


def check(paths: list[Path], names: list[str] | None = None) -> None:
    """Raise ``RuntimeError`` listing every gap in the wheels at *paths*.

    *names*, when given, limits the audit to those distributions.
    """
    contents = [read_wheel(p) for p in wheels_in(paths)]
    if names is not None:
        wanted = {normalize(n) for n in names}
        contents = [c for c in contents if c.name in wanted]
    problems = audit(contents)
    if problems:
        raise RuntimeError("Wheel dependency audit failed:\n  " + "\n  ".join(problems))


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        check([Path(a) for a in argv])
    except RuntimeError as err:
        print(err, file=sys.stderr)
        return 1
    print("Wheel dependency audit passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
