"""A named module dependency must not crash for want of a clone directory."""

import build_wheels
import pytest


@pytest.mark.parametrize("supplied", [None, ""])
def test_absent_dependency_root_is_derived(supplied, tmp_path):
    """None or empty must become a real path, not reach the clone step.

    A module declaring itk-module-deps without this option crashed with
    "'NoneType' object has no attribute 'mkdir'".
    """
    resolved = build_wheels.module_dependencies_root(tmp_path, supplied)
    assert resolved == tmp_path / "MODULE_DEPENDENCIES"


def test_supplied_dependency_root_is_respected(tmp_path):
    chosen = tmp_path / "elsewhere"
    assert build_wheels.module_dependencies_root(tmp_path, chosen) == chosen


def test_a_supplied_string_root_becomes_a_path(tmp_path):
    chosen = str(tmp_path / "elsewhere")
    assert (
        build_wheels.module_dependencies_root(tmp_path, chosen)
        == tmp_path / "elsewhere"
    )
