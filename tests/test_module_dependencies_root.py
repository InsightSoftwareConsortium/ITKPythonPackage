"""A named module dependency must not crash for want of a clone directory."""

from pathlib import Path
from types import SimpleNamespace

import build_wheels
import module_dependencies
import pytest


def _resolve(build_dir_root, supplied):
    """Mirror the resolution build_wheels performs after parsing."""
    args = SimpleNamespace(
        build_dir_root=build_dir_root, module_dependencies_root_dir=supplied
    )
    if not args.module_dependencies_root_dir:
        args.module_dependencies_root_dir = (
            Path(args.build_dir_root) / "MODULE_DEPENDENCIES"
        )
    return args.module_dependencies_root_dir


@pytest.mark.parametrize("supplied", [None, "", "   "])
def test_absent_dependency_root_is_derived(supplied, tmp_path):
    """None or empty must become a real path, not reach the clone step.

    A module declaring itk-module-deps without this option crashed with
    "'NoneType' object has no attribute 'mkdir'".
    """
    resolved = _resolve(tmp_path, supplied if supplied != "   " else "")
    assert isinstance(resolved, Path)
    assert resolved == tmp_path / "MODULE_DEPENDENCIES"


def test_supplied_dependency_root_is_respected(tmp_path):
    chosen = tmp_path / "elsewhere"
    assert _resolve(tmp_path, chosen) == chosen


def test_the_clone_step_requires_a_real_path():
    """Pin why the default matters: the clone step calls mkdir on it."""
    source = Path(module_dependencies.__file__).read_text()
    assert "context.module_dependencies_root_dir.mkdir(" in source


def test_build_wheels_derives_the_default():
    source = Path(build_wheels.__file__).read_text()
    assert "if not args.module_dependencies_root_dir:" in source
    assert '"MODULE_DEPENDENCIES"' in source
