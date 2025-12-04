from __future__ import annotations

from typing import Dict, Iterable, Iterator, Mapping, MutableMapping, Tuple


class CMakeArgumentBuilder:
    """
    Utility to manage CMake-style key/value definitions and render them as
    command-line arguments for both direct CMake invocation and Python
    scikit-build-core builds.

    Keys should include any CMake type suffix as part of the key, e.g.
    'CMAKE_BUILD_TYPE:STRING'. Values are rendered verbatim.

    Example:
        flags = {
            'CMAKE_BUILD_TYPE:STRING': 'Release',
            'CMAKE_OSX_ARCHITECTURES:STRING': 'arm64',
        }
        builder = CMakeArgumentBuilder(flags)
        builder.getCMakeCommandLineArguments()
        # => ['-DCMAKE_BUILD_TYPE:STRING=Release', '-DCMAKE_OSX_ARCHITECTURES:STRING=arm64']
        builder.getPythonBuildCommandLineArguments()
        # => ['--config-setting=cmake.define.CMAKE_BUILD_TYPE:STRING=Release',
        #     '--config-setting=cmake.define.CMAKE_OSX_ARCHITECTURES:STRING=arm64']
    """

    def __init__(self, initial: Mapping[str, str] | None = None) -> None:
        # dict preserves insertion order; keep user's order when possible
        self._defs: Dict[str, str] = dict(initial) if initial else {}

    # Basic mapping helpers (optional convenience)
    def set(self, key: str, value: str) -> None:
        """Set or replace a definition (key should include type suffix if desired)."""
        self._defs[key] = value

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._defs.get(key, default)

    def update(self, other: Mapping[str, str] | Iterable[Tuple[str, str]]) -> None:
        if isinstance(other, Mapping):
            self._defs.update(other)
        else:
            for k, v in other:
                self._defs[k] = v

    def __contains__(self, key: str) -> bool:  # pragma: no cover - trivial
        return key in self._defs

    def __getitem__(self, key: str) -> str:  # pragma: no cover - trivial
        return self._defs[key]

    def __iter__(self) -> Iterator[str]:  # pragma: no cover - trivial
        return iter(self._defs)

    def items(self) -> Iterable[Tuple[str, str]]:  # pragma: no cover - trivial
        return self._defs.items()

    # Renderers
    def getCMakeCommandLineArguments(self) -> list[str]:
        """
        Render definitions as CMake `-D` arguments.

        Returns a list like: ['-D<KEY>=<VALUE>', ...]
        where <KEY> may contain a CMake type suffix (e.g., ':STRING').
        """
        return [f"-D{k}={v}" for k, v in self._defs.items()]

    def getPythonBuildCommandLineArguments(self) -> list[str]:
        """
        Render definitions as scikit-build-core `--config-setting` arguments.

        Returns a list like:
        ['--config-setting=cmake.define.<KEY>=<VALUE>', ...]
        where <KEY> may contain a CMake type suffix (e.g., ':STRING').
        """
        prefix = "--config-setting=cmake.define."
        return [f"{prefix}{k}={v}" for k, v in self._defs.items()]


__all__ = ["CMakeArgumentBuilder"]
