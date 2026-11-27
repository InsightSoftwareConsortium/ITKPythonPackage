"""Failure handling in the process helpers the build driver relies on."""

import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from unittest.mock import patch

import pytest
import wheel_builder_utils
from wheel_builder_utils import compute_itk_package_version, which_required


def _completed(
    returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["git"], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", []),
        ([], []),
        ("nvcuda.dll", ["nvcuda.dll"]),
        ("C:/CUDA/bin", ["C:/CUDA/bin"]),
        (["a.dll;b.dll;"], ["a.dll", "b.dll"]),
        (["a.dll", "b.dll"], ["a.dll", "b.dll"]),
        ("a.dll; ;b.dll", ["a.dll", "b.dll"]),
    ],
)
def test_split_semicolon_list(value: Sequence[str] | str, expected: list[str]) -> None:
    assert wheel_builder_utils.split_semicolon_list(value) == expected


def test_which_required_raises_for_a_missing_executable() -> None:
    """A missing tool must not become the string 'None' in an argv list."""
    with pytest.raises(RuntimeError, match="MISSING"):
        which_required("no-such-executable-b7f3c1")


def test_compute_itk_package_version_refuses_an_unusable_describe(
    tmp_path: Path,
) -> None:
    """An empty `git describe` would otherwise name the wheels 0.0.0."""
    responses = {
        "fetch": _completed(0),
        "checkout": _completed(0),
        "describe": _completed(128, "", "fatal: not a git repository"),
    }

    def fake_run(
        cmd: Sequence[str | Path],
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        if str(cmd[1]) == "rev-parse" and "--git-dir" in [str(c) for c in cmd]:
            return _completed(0, ".git")
        return responses[str(cmd[1])]

    with (
        patch.object(wheel_builder_utils, "run_command", fake_run),
        pytest.raises(RuntimeError, match="no usable version"),
    ):
        compute_itk_package_version(tmp_path, "v6.0.0", {})


def test_compute_itk_package_version_refuses_a_zero_version(tmp_path: Path) -> None:
    """A describe that parses to 0.0.0 is not a version to ship."""
    responses = {
        "fetch": _completed(0),
        "checkout": _completed(0),
        "describe": _completed(0, "not-a-tag"),
    }

    def fake_run(
        cmd: Sequence[str | Path],
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        if str(cmd[1]) == "rev-parse" and "--git-dir" in [str(c) for c in cmd]:
            return _completed(0, ".git")
        return responses[str(cmd[1])]

    with (
        patch.object(wheel_builder_utils, "run_command", fake_run),
        pytest.raises(RuntimeError, match=r"0\.0\.0"),
    ):
        compute_itk_package_version(tmp_path, "v6.0.0", {})


def test_compute_itk_package_version_keeps_head_on_failed_checkout(
    tmp_path: Path,
) -> None:
    """A failed checkout must leave the tree where it is.

    Exactly one checkout is attempted: forcing a second one onto 'main'
    would move a cache-restored ITK source tree away from the commit its
    prebuilt binaries were compiled from.
    """
    checked_out: list[str] = []

    def fake_run(
        cmd: Sequence[str | Path],
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        if str(cmd[1]) == "rev-parse" and "--git-dir" in [str(c) for c in cmd]:
            return _completed(0, ".git")
        verb = str(cmd[1])
        if verb == "checkout":
            checked_out.append(str(cmd[2]))
            return _completed(1, "", "no such ref")
        if verb == "rev-parse":
            return _completed(0, "abcdef1234567890abcdef1234567890abcdef12")
        if verb == "describe":
            return _completed(0, "v6.0.0-0-gabcdef1")
        return _completed(0)

    with patch.object(wheel_builder_utils, "run_command", fake_run):
        version = compute_itk_package_version(tmp_path, "v9.9.9", {})

    assert checked_out == ["v9.9.9"]
    assert version.startswith("6.0")


def test_compute_itk_package_version_works_offline(tmp_path: Path) -> None:
    """sync_itk_source accepts a failed fetch when the revision is present."""

    def fake_run(
        cmd: Sequence[str | Path],
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        if str(cmd[1]) == "fetch":
            return _completed(1, "", "network down")
        if str(cmd[1]) == "describe":
            return _completed(0, "v6.0.0-0-gabc1234")
        return _completed(0, ".git")

    with patch.object(wheel_builder_utils, "run_command", fake_run):
        assert compute_itk_package_version(tmp_path, "v6.0.0", {}) == "6.0.0"


def test_streamed_output_is_also_returned(capsys: pytest.CaptureFixture[str]) -> None:
    result = wheel_builder_utils.run_command(
        [sys.executable, "-c", "print('line one'); print('line two')"], stream=True
    )
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["line one", "line two"]
    assert "line one\nline two\n" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("manylinux228-py311", True),
        ("macosx-py311", True),
        ("windows-py311", True),
        ("linux-py311", True),
        ("dev", False),
        ("dev-docs", False),
        ("pixi-pycharm", False),
        ("", False),
    ],
)
def test_is_platform_env(name: str, expected: bool) -> None:
    assert wheel_builder_utils.is_platform_env(name) is expected
