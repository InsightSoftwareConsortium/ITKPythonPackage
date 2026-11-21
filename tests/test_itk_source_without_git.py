"""A cache-restored ITK tree has no .git and must not abort the build."""

import subprocess
from pathlib import Path

import build_wheels
import pytest
import wheel_builder_utils


class _FakeGit:
    """Answer git commands for sync_itk_source and record what was asked."""

    def __init__(self, failing: set[str], head: str = "abc123") -> None:
        self.failing = failing
        self.head = head
        self.calls: list[list[str]] = []
        self.envs: list[dict[str, str] | None] = []

    def __call__(self, cmd, cwd=None, env=None, check=False):
        cmd = [str(c) for c in cmd]
        self.calls.append(cmd)
        self.envs.append(env)
        name = " ".join(cmd[1:3])
        failed = any(name.startswith(f) for f in self.failing)
        stdout = self.head if cmd[1:3] == ["rev-parse", "HEAD"] else ""
        return subprocess.CompletedProcess(cmd, 1 if failed else 0, stdout, "")

    def ran(self, *subcommand: str) -> bool:
        return any(c[1 : 1 + len(subcommand)] == list(subcommand) for c in self.calls)


def _sync(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake_git: _FakeGit,
    tag: str = "v6.0.0",
) -> str:
    monkeypatch.setattr(build_wheels, "run_commandLine_subprocess", fake_git)
    return build_wheels.sync_itk_source(tmp_path, tag)


def test_a_tree_without_a_repository_is_used_as_it_is(tmp_path, monkeypatch):
    git = _FakeGit(failing={"rev-parse --git-dir"})
    assert _sync(monkeypatch, tmp_path, git) == "v6.0.0"
    assert not git.ran("fetch")
    assert not git.ran("checkout")


def test_a_repository_is_fetched_and_checked_out(tmp_path, monkeypatch):
    git = _FakeGit(failing=set())
    assert _sync(monkeypatch, tmp_path, git) == "v6.0.0"
    assert git.ran("fetch", "--tags", "origin")
    assert git.ran("checkout", "v6.0.0")


def test_a_failed_fetch_is_fatal_when_the_revision_is_missing(tmp_path, monkeypatch):
    git = _FakeGit(failing={"fetch", "rev-parse --verify"})
    with pytest.raises(RuntimeError, match="Failed to fetch ITK tags"):
        _sync(monkeypatch, tmp_path, git)


def test_a_failed_fetch_is_survived_when_the_revision_is_present(tmp_path, monkeypatch):
    git = _FakeGit(failing={"fetch"})
    assert _sync(monkeypatch, tmp_path, git) == "v6.0.0"
    assert git.ran("checkout", "v6.0.0")


def test_a_failed_checkout_keeps_the_commit_already_checked_out(tmp_path, monkeypatch):
    git = _FakeGit(failing={"checkout"}, head="deadbeef")
    assert _sync(monkeypatch, tmp_path, git) == "deadbeef"


def test_every_git_call_stops_at_the_itk_tree(tmp_path, monkeypatch):
    """A cache extracted inside a module checkout must not act on that checkout."""
    git = _FakeGit(failing={"checkout"})
    _sync(monkeypatch, tmp_path, git)
    ceiling = str(tmp_path.resolve().parent)
    assert git.envs
    assert all(env and env["GIT_CEILING_DIRECTORIES"] == ceiling for env in git.envs)


def test_a_tree_inside_another_repository_is_not_a_repository(tmp_path):
    """The real git honors the ceiling for a tree nested in a module checkout."""
    module = tmp_path / "module"
    source = module / "ITKPythonPackage-build" / "ITK"
    source.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(module)], check=True)
    probe = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=source,
        env=build_wheels.itk_git_env(source),
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode != 0


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
        check=False,
    )
    assert probe.returncode != 0  # what the new guard checks


def test_gitauto_is_the_default_version(monkeypatch):
    monkeypatch.delenv("ITK_PACKAGE_VERSION", raising=False)
    assert (
        build_wheels.remotemodulebuildandtestaction()["ITK_PACKAGE_VERSION"]
        == "gitauto"
    )


@pytest.mark.parametrize("sentinel", ["gitauto", "auto", "", None])
def test_sentinel_values_derive_the_version_from_git(sentinel):
    assert build_wheels.derives_package_version(sentinel)


@pytest.mark.parametrize("supplied", ["v6.0rc01.dev20260915", "6.0.1", "1.2.3.post4"])
def test_an_explicit_version_never_consults_git(supplied):
    """An override must not reach the git-based derivation.

    The derivation needs a repository, and a source tree restored from a build
    cache has none, so an override is the only way such a build can name its
    version.
    """
    assert not build_wheels.derives_package_version(supplied)


def test_version_derivation_explains_a_cache_tree(tmp_path, monkeypatch):
    """Without a repository the error must name the fix, not just the failure."""

    def not_a_repository(cmd, cwd=None, env=None, check=False):
        return subprocess.CompletedProcess(cmd, 128, "", "fatal: not a git repository")

    monkeypatch.setattr(
        wheel_builder_utils, "run_commandLine_subprocess", not_a_repository
    )
    with pytest.raises(RuntimeError, match="Pass --itk-package-version"):
        wheel_builder_utils.compute_itk_package_version(tmp_path, "v6.0.0", {})
