"""Wheels from the same ITK commit get the same zip timestamps."""

import subprocess
from pathlib import Path

import pytest
from build_wheels import itk_commit_time, source_date_epoch


def test_the_itk_commit_time_is_used():
    assert source_date_epoch({}, "1763600000\n") == "1763600000"


def test_a_value_the_caller_set_wins():
    env = {"SOURCE_DATE_EPOCH": "1700000000"}
    assert source_date_epoch(env, "1763600000") == "1700000000"


def test_an_empty_caller_value_is_ignored():
    assert source_date_epoch({"SOURCE_DATE_EPOCH": ""}, "1763600000") == "1763600000"


@pytest.mark.parametrize("commit_time", [None, "", "  ", "not-a-time"])
def test_without_a_commit_time_nothing_is_set(commit_time):
    assert source_date_epoch({}, commit_time) is None


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_the_commit_time_comes_from_the_requested_revision(tmp_path, monkeypatch):
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GIT_COMMITTER_DATE", "@1700000000 +0000")
    monkeypatch.setenv("GIT_AUTHOR_DATE", "@1600000000 +0000")
    _git(tmp_path, "init", "-q")
    _git(
        tmp_path,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "c",
    )
    _git(tmp_path, "tag", "v1")
    assert source_date_epoch({}, itk_commit_time(tmp_path, "v1")) == "1700000000"


def test_a_tree_inside_another_repository_has_no_commit_time(tmp_path, monkeypatch):
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(name, raising=False)
    _git(tmp_path, "init", "-q")
    _git(
        tmp_path,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "c",
    )
    restored = tmp_path / "ITK"
    (restored / ".git").mkdir(parents=True)
    assert itk_commit_time(restored, "HEAD") is None
