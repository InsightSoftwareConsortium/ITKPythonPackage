from collections.abc import Iterable, Iterator, Mapping


def drop_quotes(s: str) -> str:
    """Strip surrounding double-quote characters from *s*."""
    return str(s).strip('"')


class CMakeArgumentBuilder:
    """Manage CMake-style key/value definitions and render them as CLI args.

    Keys should include any CMake type suffix (e.g.
    ``'CMAKE_BUILD_TYPE:STRING'``).  Values are rendered verbatim.

    Parameters
    ----------
    initial : Mapping[str, str], optional
        Initial set of definitions to populate the builder.

    Examples
    --------
    >>> flags = {
    ...     'CMAKE_BUILD_TYPE:STRING': 'Release',
    ...     'CMAKE_OSX_ARCHITECTURES:STRING': 'arm64',
    ... }
    >>> builder = CMakeArgumentBuilder(flags)
    >>> builder.getCMakeCommandLineArguments()
    ["-DCMAKE_BUILD_TYPE:STRING='Release'", "-DCMAKE_OSX_ARCHITECTURES:STRING='arm64'"]
    >>> builder.getPythonBuildCommandLineArguments()
    ['--config-setting=cmake.define.CMAKE_BUILD_TYPE:STRING=Release',
     '--config-setting=cmake.define.CMAKE_OSX_ARCHITECTURES:STRING=arm64']
    """

    def __init__(self, initial: Mapping[str, str] | None = None) -> None:
        # dict preserves insertion order; keep user's order when possible
        self._defs: dict[str, str] = dict(initial) if initial else {}

    # Basic mapping helpers (optional convenience)
    def set(self, key: str, value: str) -> None:
        """Set or replace a definition.

        Parameters
        ----------
        key : str
            CMake variable name, optionally with a type suffix
            (e.g. ``'CMAKE_BUILD_TYPE:STRING'``).
        value : str
            Value for the definition.
        """
        self._defs[key] = value

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the value for *key*, or *default* if absent."""
        return self._defs.get(key, default)

    def update(self, other: Mapping[str, str] | Iterable[tuple[str, str]]) -> None:
        """Merge definitions from *other* into this builder.

        Parameters
        ----------
        other : Mapping[str, str] or Iterable[tuple[str, str]]
            Definitions to merge.  Existing keys are overwritten.
        """
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

    def items(self) -> Iterable[tuple[str, str]]:  # pragma: no cover - trivial
        """Return an iterable of ``(key, value)`` definition pairs."""
        return self._defs.items()

    # Renderers
    def getCMakeCommandLineArguments(self) -> list[str]:
        """Render definitions as CMake ``-D`` arguments.

        Returns
        -------
        list[str]
            A list like ``["-D<KEY>='<VALUE>'", ...]``.
        """
        return [f"""-D{k}='{drop_quotes(v)}'""" for k, v in self._defs.items()]

    def getPythonBuildCommandLineArguments(self) -> list[str]:
        """Render definitions as scikit-build-core ``--config-setting`` arguments.

        Returns
        -------
        list[str]
            A list like
            ``["--config-setting=cmake.define.<KEY>='<VALUE>'", ...]``.
        """
        prefix = "--config-setting=cmake.define."
        return [f"""{prefix}{k}='{drop_quotes(v)}'""" for k, v in self._defs.items()]


__all__ = ["CMakeArgumentBuilder"]
