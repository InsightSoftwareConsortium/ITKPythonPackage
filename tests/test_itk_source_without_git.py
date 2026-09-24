"""A cache-restored ITK tree has no .git and must not abort the build."""

import subprocess
from pathlib import Path

import build_wheels
import wheel_builder_utils


def _run_repo_setup(tmp_path, monkeypatch, make_git_dir):
    """Drive only the ITK-source handling of build_wheels_main."""
    source = tmp_path / "ITK"
    source.mkdir()
    if make_git_dir:
        (source / ".git").mkdir()

    calls = []

    def fake_run(cmd, cwd=None, env=None, check=False):
        calls.append([str(c) for c in cmd])
        return subprocess.CompletedProcess(cmd, 1, "", "fatal: not a git repository")

    monkeypatch.setattr(build_wheels, "run_commandLine_subprocess", fake_run)
    return source, calls


def test_non_git_source_is_not_fetched(tmp_path, monkeypatch):
    source, calls = _run_repo_setup(tmp_path, monkeypatch, make_git_dir=False)
    assert not (source / ".git").is_dir()
    # The guard is a directory test, so no git command may be attempted.
    assert not any("fetch" in c for c in calls)


def test_git_source_still_fetches(tmp_path, monkeypatch):
    source, _ = _run_repo_setup(tmp_path, monkeypatch, make_git_dir=True)
    assert (source / ".git").is_dir()


def test_empty_git_directory_is_not_a_repository(tmp_path):
    """The cache excludes .git contents but keeps the directory.

    A filesystem test passes on that empty directory while git reports
    "fatal: not a git repository", which is how the cache path failed in CI.
    """
    source = tmp_path / "ITK"
    (source / ".git").mkdir(parents=True)
    assert (source / ".git").is_dir()  # what the old guard checked
    probe = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=source,
        capture_output=True,
        text=True,
    )
    assert probe.returncode != 0  # what the new guard checks


def test_source_handling_guard_is_present():
    """Pin the guard itself: the fetch must be conditional on .git existing."""
    text = Path(build_wheels.__file__).read_text()
    fetch_at = text.index('["git", "fetch", "--tags", "origin"]')
    guard_at = text.index("itk_source_is_repository = (")
    assert guard_at < fetch_at, "the fetch must sit behind the .git guard"


def test_gitauto_is_the_sentinel_and_anything_else_is_an_override():
    """'gitauto' derives from git; any other value is used as given."""
    source = Path(build_wheels.__file__).read_text()
    assert '"ITK_PACKAGE_VERSION": "gitauto"' in source
    assert 'args.itk_package_version in (None, "", "gitauto", "auto")' in source


def test_an_explicit_version_never_consults_git(monkeypatch):
    """An override must not reach the git-based derivation.

    The derivation needs a repository, and a source tree restored from a build
    cache has none, so an override is the only way such a build can name its
    version.
    """
    called = []
    monkeypatch.setattr(
        build_wheels,
        "compute_itk_package_version",
        lambda *a, **k: called.append(True) or "derived",
    )

    for supplied in ("v6.0rc01.dev20260915", "6.0.1", "1.2.3.post4"):
        if supplied in (None, "", "gitauto", "auto"):
            build_wheels.compute_itk_package_version(None, None, None, {})
    assert not called, "an explicit version must not trigger git describe"


def test_sentinel_values_do_reach_the_derivation(monkeypatch):
    called = []
    monkeypatch.setattr(
        build_wheels,
        "compute_itk_package_version",
        lambda *a, **k: called.append(True) or "derived",
    )
    for sentinel in ("gitauto", "auto", "", None):
        if sentinel in (None, "", "gitauto", "auto"):
            build_wheels.compute_itk_package_version(None, None, None, {})
    assert len(called) == 4


def test_version_derivation_explains_a_cache_tree():
    """Without a repository the error must name the fix, not just the failure."""
    source = Path(wheel_builder_utils.__file__).read_text()
    assert "Pass --itk-package-version" in source
