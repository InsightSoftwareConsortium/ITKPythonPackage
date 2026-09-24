import re
import tomllib
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from module_dependencies import build_module_dependencies, update_module_itk_deps

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


def test_metapackage_pin_is_bounded(tmp_path):
    path = _write(tmp_path, METAPACKAGE)
    assert update_module_itk_deps(path, "v6.0.0") is True
    assert '"itk >= 6.0.0b1, < 7"' in path.read_text()


def test_subpackage_pins_both_syntaxes(tmp_path):
    path = _write(tmp_path, SUBPACKAGES)
    assert update_module_itk_deps(path, "v6.0.0") is True
    text = path.read_text()
    assert '"itk-core >= 6.0.0b1, < 7"' in text
    assert '"itk-filtering >= 6.0.0b1, < 7"' in text


def test_no_itk_pins_leaves_file_byte_identical(tmp_path):
    path = _write(tmp_path, NO_ITK)
    before = path.read_bytes()
    assert update_module_itk_deps(path, "v6.0.0") is False
    assert path.read_bytes() == before


def test_unparseable_version_leaves_file_unchanged(tmp_path):
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
def test_bound_is_derived_from_major_minor_only(version, tmp_path_factory):
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
    minor = re.match(r"\d*", minor).group()
    expected = f'"itk >= {major}.{minor}.0b1, < {int(major) + 1}"'
    assert expected in path.read_text()


@given(version=VERSIONS)
# Deadline disabled: each example does real filesystem I/O.
@settings(deadline=None)
def test_rewrite_is_idempotent(version, tmp_path_factory):
    """Maintainer decision 2026-09-16: the rewriter is idempotent."""
    path = _write(tmp_path_factory.mktemp("idem"), METAPACKAGE)
    update_module_itk_deps(path, version)
    once = path.read_bytes()
    update_module_itk_deps(path, version)
    assert path.read_bytes() == once


@given(version=VERSIONS)
# Deadline disabled: each example does real filesystem I/O.
@settings(deadline=None)
def test_output_is_still_valid_toml(version, tmp_path_factory):
    path = _write(tmp_path_factory.mktemp("toml"), SUBPACKAGES)
    update_module_itk_deps(path, version)
    tomllib.loads(path.read_text())


class _DepContext:
    """A build context carrying only what build_module_dependencies reads."""

    def __init__(self, module_source_dir: Path, deps: str, failing: str):
        self.module_source_dir = module_source_dir
        self.module_dependencies_root_dir = module_source_dir / "deps"
        self.itk_module_deps = deps
        self._failing = failing
        self.calls: list[list[str]] = []

    def echo_check_call(self, cmd, check: bool = False, **kwargs) -> int:
        cmd = [str(c) for c in cmd]
        self.calls.append(cmd)
        if self._failing in cmd:
            if check:
                raise RuntimeError(f"git {self._failing} failed")
            return 1
        if cmd[1] == "clone":
            Path(cmd[3]).mkdir(parents=True, exist_ok=True)
        return 0

    def clone(self):  # pragma: no cover - not reached by these tests
        raise AssertionError("dependency build must not start after a git failure")


@pytest.mark.parametrize("failing", ["clone", "fetch", "checkout"])
def test_dependency_git_failures_stop_the_build(tmp_path, failing):
    """A pinned dependency tag is a constraint, not a suggestion."""
    context = _DepContext(tmp_path, "InsightSoftwareConsortium/ITKFoo@v1.2.3", failing)
    with pytest.raises(RuntimeError):
        build_module_dependencies(context)
