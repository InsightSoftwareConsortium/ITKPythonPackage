import re
import tomllib
from collections.abc import Sequence
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from module_dependencies import (
    build_module_dependencies,
    copy_files,
    update_module_itk_deps,
)

METAPACKAGE = """\
[project]
name = "itk-example"
dependencies = ["itk == 5.4.*"]
"""

SUBPACKAGES = """\
[project]
name = "itk-example"
dependencies = ["itk-core == 5.4.*", "itk-filtering ~= 5.4"]
"""

NO_ITK = """\
[project]
name = "unrelated"
dependencies = ["numpy >= 1.26"]
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text(text)
    return path


def test_metapackage_pin_is_bounded(tmp_path: Path) -> None:
    path = _write(tmp_path, METAPACKAGE)
    assert update_module_itk_deps(path, "v6.0.0") is True
    assert '"itk >= 6.0.0b1, < 7"' in path.read_text()


def test_subpackage_pins_both_syntaxes(tmp_path: Path) -> None:
    path = _write(tmp_path, SUBPACKAGES)
    assert update_module_itk_deps(path, "v6.0.0") is True
    text = path.read_text()
    assert '"itk-core >= 6.0.0b1, < 7"' in text
    assert '"itk-filtering >= 6.0.0b1, < 7"' in text


def test_no_itk_pins_leaves_file_byte_identical(tmp_path: Path) -> None:
    path = _write(tmp_path, NO_ITK)
    before = path.read_bytes()
    assert update_module_itk_deps(path, "v6.0.0") is False
    assert path.read_bytes() == before


def test_unparseable_version_leaves_file_unchanged(tmp_path: Path) -> None:
    path = _write(tmp_path, METAPACKAGE)
    before = path.read_bytes()
    assert update_module_itk_deps(path, "not-a-version") is False
    assert path.read_bytes() == before


VERSIONS = st.builds(
    lambda major, minor, suffix: f"v{major}.{minor}{suffix}",
    major=st.integers(min_value=1, max_value=99),
    minor=st.integers(min_value=0, max_value=99),
    suffix=st.sampled_from(["", ".0", ".7", "rc01", "rc02", ".dev20260915"]),
)


@given(version=VERSIONS)
# Deadline disabled: each example does real filesystem I/O.
@settings(deadline=None)
def test_bound_is_derived_from_major_minor_only(
    version: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Floor is >= X.Y.0b1 and ceiling < X+1.

    The floor's ``.0b1`` is a fixed series marker, not the tag's own
    pre-release: this is the property that catches ``itk >= v6.0rc01``.
    """
    path = _write(tmp_path_factory.mktemp("pin"), METAPACKAGE)
    assert update_module_itk_deps(path, version) is True
    major, minor = version.lstrip("v").split(".")[:2]
    # Only the leading digit run of the minor component is significant;
    # a suffix glued directly onto it (e.g. "0rc01") must not contribute
    # digits of its own to the expected floor.
    leading_digits = re.match(r"\d*", minor)
    assert leading_digits is not None
    minor = leading_digits.group()
    expected = f'"itk >= {major}.{minor}.0b1, < {int(major) + 1}"'
    assert expected in path.read_text()


@given(version=VERSIONS)
# Deadline disabled: each example does real filesystem I/O.
@settings(deadline=None)
def test_rewrite_is_idempotent(
    version: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Maintainer decision 2026-09-16: the rewriter is idempotent."""
    path = _write(tmp_path_factory.mktemp("idem"), METAPACKAGE)
    update_module_itk_deps(path, version)
    once = path.read_bytes()
    update_module_itk_deps(path, version)
    assert path.read_bytes() == once


@given(version=VERSIONS)
# Deadline disabled: each example does real filesystem I/O.
@settings(deadline=None)
def test_output_is_still_valid_toml(
    version: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    path = _write(tmp_path_factory.mktemp("toml"), SUBPACKAGES)
    update_module_itk_deps(path, version)
    tomllib.loads(path.read_text())


class _DepContext:
    """The values and callbacks build_module_dependencies is given."""

    def __init__(self, module_source_dir: Path, deps: str, failing: str) -> None:
        self.module_source_dir = module_source_dir
        self.module_dependencies_root_dir = module_source_dir / "deps"
        self.itk_module_deps = deps
        self._failing = failing
        self.calls: list[list[str]] = []

    def echo_check_call(
        self, cmd: Sequence[str | Path], check: bool = False, **kwargs: object
    ) -> int:
        args = [str(c) for c in cmd]
        self.calls.append(args)
        if self._failing in args:
            if check:
                msg = f"git {self._failing} failed"
                raise RuntimeError(msg)
            return 1
        if args[1] == "clone":
            Path(args[3]).mkdir(parents=True, exist_ok=True)
        return 0

    def build_module(self, _source_dir: Path) -> None:  # pragma: no cover
        msg = "dependency build must not start after a git failure"
        raise AssertionError(msg)


@pytest.mark.parametrize("failing", ["clone", "fetch", "checkout"])
def test_dependency_git_failures_stop_the_build(tmp_path: Path, failing: str) -> None:
    """A pinned dependency tag is a constraint, not a suggestion."""
    context = _DepContext(tmp_path, "InsightSoftwareConsortium/ITKFoo@v1.2.3", failing)
    with pytest.raises(RuntimeError):
        build_module_dependencies(
            context.itk_module_deps,
            context.module_source_dir,
            context.module_dependencies_root_dir,
            context.echo_check_call,
            context.build_module,
        )


def test_copy_files_places_each_file_where_asked(tmp_path: Path) -> None:
    src_root = tmp_path / "src"
    (src_root / "sub").mkdir(parents=True)
    (src_root / "a.h").write_text("a")
    (src_root / "sub" / "b.h").write_text("b")
    dst_root = tmp_path / "dst"
    copy_files(src_root.rglob("*"), dst_root, src_root)
    assert (dst_root / "a.h").read_text() == "a"
    assert (dst_root / "sub" / "b.h").read_text() == "b"
    flat = tmp_path / "flat"
    copy_files(src_root.rglob("*.h"), flat)
    assert sorted(p.name for p in flat.iterdir()) == ["a.h", "b.h"]


def test_each_dependency_is_cloned_checked_out_and_built_in_order(
    tmp_path: Path,
) -> None:
    context = _DepContext(tmp_path, "Foo@v1:Org/ITKBar@abc", failing="none")
    built: list[Path] = []
    build_module_dependencies(
        context.itk_module_deps,
        context.module_source_dir,
        context.module_dependencies_root_dir,
        context.echo_check_call,
        built.append,
    )
    assert built == [tmp_path / "deps" / "ITKFoo", tmp_path / "deps" / "ITKBar"]
    clones = [c for c in context.calls if c[1] == "clone"]
    assert [c[2] for c in clones] == [
        "https://github.com/InsightSoftwareConsortium/ITKFoo.git",
        "https://github.com/Org/ITKBar.git",
    ]
    checkouts = [c[-1] for c in context.calls if "checkout" in c]
    assert checkouts == ["v1", "abc"]
