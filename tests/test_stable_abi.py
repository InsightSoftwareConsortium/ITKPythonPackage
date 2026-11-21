"""The stable-ABI tag is a project decision, not a property of the driver."""

import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from build_python_instance_base import verify_stable_abi_wheels
from pyproject_configure import STABLE_ABI_TAG, build_base_pyproject_parameters


def test_stable_abi_tag_is_cp311():
    assert STABLE_ABI_TAG == "cp311"


def test_py_api_ignores_the_running_interpreter():
    """One cp311-abi3 wheel per platform, whatever python drives the build."""
    fake = SimpleNamespace(major=3, minor=14)
    with patch.object(sys, "version_info", fake):
        params = build_base_pyproject_parameters(
            {"ITK_SOURCE_DIR": "ITK"}, "pyproject_configure.py", "6.0.0"
        )
    assert params["PYPROJECT_PY_API"] == "cp311"


def test_a_cp312_abi3_wheel_is_rejected(tmp_path):
    """A cp312-abi3 wheel will not install on 3.11; refuse to ship it."""
    (tmp_path / "itk_foo-1.0.0-cp312-abi3-manylinux_2_28_x86_64.whl").touch()
    with pytest.raises(RuntimeError, match="cp311-abi3"):
        verify_stable_abi_wheels(tmp_path, STABLE_ABI_TAG)


def test_no_wheel_at_all_is_rejected(tmp_path):
    """A build step that produced nothing must not report success."""
    with pytest.raises(RuntimeError, match="No wheel"):
        verify_stable_abi_wheels(tmp_path, STABLE_ABI_TAG)


def test_a_cp311_abi3_wheel_is_accepted(tmp_path):
    wheel = tmp_path / "itk_foo-1.0.0-cp311-abi3-manylinux_2_28_x86_64.whl"
    wheel.touch()
    assert verify_stable_abi_wheels(tmp_path, STABLE_ABI_TAG) == [wheel]
