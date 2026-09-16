"""Failure handling in the process helpers the build driver relies on."""

import subprocess
from unittest.mock import patch

import pytest
import wheel_builder_utils
from wheel_builder_utils import compute_itk_package_version, which_required


def _completed(returncode: int, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(
        args=["git"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_which_required_raises_for_a_missing_executable():
    """A missing tool must not become the string 'None' in an argv list."""
    with pytest.raises(RuntimeError, match="MISSING"):
        which_required("no-such-executable-b7f3c1")


def test_compute_itk_package_version_refuses_an_unusable_describe(tmp_path):
    """An empty `git describe` would otherwise name the wheels 0.0.0."""
    responses = {
        "fetch": _completed(0),
        "checkout": _completed(0),
        "describe": _completed(128, "", "fatal: not a git repository"),
    }

    def fake_run(cmd, cwd=None, env=None, check=False):
        return responses[str(cmd[1])]

    with patch.object(wheel_builder_utils, "run_commandLine_subprocess", fake_run):
        with pytest.raises(RuntimeError, match="no usable version"):
            compute_itk_package_version(tmp_path, "v6.0.0", None, {})


def test_compute_itk_package_version_refuses_a_zero_version(tmp_path):
    """A describe that parses to 0.0.0 is not a version to ship."""
    responses = {
        "fetch": _completed(0),
        "checkout": _completed(0),
        "describe": _completed(0, "not-a-tag"),
    }

    def fake_run(cmd, cwd=None, env=None, check=False):
        return responses[str(cmd[1])]

    with patch.object(wheel_builder_utils, "run_commandLine_subprocess", fake_run):
        with pytest.raises(RuntimeError, match="0.0.0"):
            compute_itk_package_version(tmp_path, "v6.0.0", None, {})


def test_compute_itk_package_version_keeps_head_on_failed_checkout(tmp_path):
    """A failed checkout must leave the tree where it is.

    Exactly one checkout is attempted: forcing a second one onto 'main'
    would move a cache-restored ITK source tree away from the commit its
    prebuilt binaries were compiled from.
    """
    checked_out: list[str] = []

    def fake_run(cmd, cwd=None, env=None, check=False):
        verb = str(cmd[1])
        if verb == "checkout":
            checked_out.append(str(cmd[2]))
            return _completed(1, "", "no such ref")
        if verb == "rev-parse":
            return _completed(0, "abcdef1234567890abcdef1234567890abcdef12")
        if verb == "describe":
            return _completed(0, "v6.0.0-0-gabcdef1")
        return _completed(0)

    with patch.object(wheel_builder_utils, "run_commandLine_subprocess", fake_run):
        version = compute_itk_package_version(tmp_path, "v9.9.9", None, {})

    assert checked_out == ["v9.9.9"]
    assert version.startswith("6.0")


def test_compute_itk_package_version_raises_when_fetch_fails(tmp_path):
    def fake_run(cmd, cwd=None, env=None, check=False):
        return _completed(1, "", "network down")

    with patch.object(wheel_builder_utils, "run_commandLine_subprocess", fake_run):
        with pytest.raises(RuntimeError, match="git fetch"):
            compute_itk_package_version(tmp_path, "v6.0.0", None, {})
