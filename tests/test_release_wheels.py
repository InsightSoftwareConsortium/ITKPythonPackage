import platform
import subprocess

import pytest
import release_wheels as rw
from release_wheels import Host
from target_platform import OS, Arch

LINUX_X64 = Host(OS.LINUX, Arch.X86_64)
LINUX_ARM64 = Host(OS.LINUX, Arch.AARCH64)
MAC_ARM64 = Host(OS.DARWIN, Arch.AARCH64)
WINDOWS_X64 = Host(OS.WINDOWS, Arch.X86_64)


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        (WINDOWS_X64, ["windows-x64"]),
        (MAC_ARM64, ["macos-arm64", "manylinux-aarch64"]),
        (LINUX_X64, ["manylinux-x64"]),
        (LINUX_ARM64, ["manylinux-aarch64"]),
    ],
)
def test_each_host_builds_the_targets_it_can(host, expected):
    assert rw.select_targets(None, host) == expected


def test_an_unsupported_host_has_no_default():
    with pytest.raises(SystemExit, match="built on darwin x64"):
        rw.select_targets(None, Host(OS.DARWIN, Arch.X86_64))


@pytest.mark.parametrize(
    ("system", "machine", "label"),
    [
        ("Linux", "x86_64", "linux x64"),
        ("Windows", "AMD64", "windows x64"),
        ("Darwin", "arm64", "darwin arm64"),
        ("Linux", "aarch64", "linux arm64"),
        ("Linux", "riscv64", "linux riscv64"),
        ("FreeBSD", "amd64", "freebsd x64"),
    ],
)
def test_host_detection_maps_spellings_and_keeps_the_label(
    monkeypatch, system, machine, label
):
    monkeypatch.setattr(platform, "system", lambda: system)
    monkeypatch.setattr(platform, "machine", lambda: machine)
    host = Host.detect()
    assert host.label == label
    if label == "linux x64":
        assert host == LINUX_X64
    if label == "linux riscv64":
        assert host.arch is None
        with pytest.raises(SystemExit, match="built on linux riscv64"):
            rw.select_targets(None, host)


@pytest.mark.parametrize(
    ("target", "host"),
    [
        ("macos-arm64", LINUX_ARM64),
        ("macos-arm64", LINUX_X64),
        ("windows-x64", MAC_ARM64),
        ("manylinux-x64", WINDOWS_X64),
        ("linux-riscv", LINUX_X64),
    ],
)
def test_targets_the_host_cannot_build_are_refused(target, host):
    with pytest.raises(SystemExit):
        rw.select_targets([target], host)


def test_an_emulated_linux_architecture_can_be_requested():
    assert rw.select_targets(["manylinux-aarch64"], LINUX_X64) == ["manylinux-aarch64"]


@pytest.mark.parametrize(
    ("ref", "is_tag", "version", "expected"),
    [
        ("v6.0b03", True, None, "6.0b03"),
        ("v5.4.0", True, None, "5.4.0"),
        ("2385a1b5d9", False, "6.0b3", "6.0b3"),
        ("2385a1b5d9", False, "v6.0b03", "6.0b03"),
        ("main", False, None, "gitauto"),
        ("v6.0b03", True, "6.0b3.post1", "6.0b3.post1"),
    ],
)
def test_package_version(ref, is_tag, version, expected):
    assert rw.package_version(ref, is_tag, version) == expected


@pytest.mark.parametrize(
    ("ref", "is_tag", "version"),
    [
        ("2385a1b5d9", False, "6.0b3+g2385a1b"),
        ("release-candidate", True, None),
        ("main", False, "latest"),
    ],
)
def test_versions_pypi_rejects_are_refused(ref, is_tag, version):
    with pytest.raises(SystemExit):
        rw.package_version(ref, is_tag, version)


def test_native_build_passes_the_commit_and_version(tmp_path):
    (step,) = rw.plan(["macos-arm64"], tmp_path / "ITK", "abc123", "6.0b3")
    cmd = step.command
    assert cmd[:4] == ["pixi", "run", "-e", "macosx-py311"]
    assert cmd[cmd.index("--platform-env") + 1] == "macosx-py311"
    assert cmd[cmd.index("--itk-source-dir") + 1] == str(tmp_path / "ITK")
    assert cmd[cmd.index("--itk-git-tag") + 1] == "abc123"
    assert cmd[cmd.index("--itk-package-version") + 1] == "6.0b3"
    assert "--build-itk-tarball-cache" in cmd
    assert "--use-compiler-cache" in cmd
    assert step.env == {}


def test_container_build_runs_without_sudo_unless_asked(tmp_path, monkeypatch):
    monkeypatch.delenv("NO_SUDO", raising=False)
    monkeypatch.delenv("MANYLINUX_VERSION", raising=False)
    (step,) = rw.plan(["manylinux-aarch64"], tmp_path / "ITK", "abc123", "gitauto")
    assert step.command[-2].endswith("dockcross-manylinux-build-wheels.sh")
    assert step.env == {
        "ITK_SOURCE_DIR": str(tmp_path / "ITK"),
        "ITK_GIT_TAG": "abc123",
        "ITK_PACKAGE_VERSION": "gitauto",
        "TARGET_ARCH": "aarch64",
        "NO_SUDO": "1",
        "USE_CCACHE": "1",
        "BUILD_WHEELS_EXTRA_FLAGS": "--build-itk-tarball-cache",
    }
    assert step.dist_dir.parent.name == "ITKPythonPackage-manylinux_2_28-aarch64-build"
    monkeypatch.setenv("NO_SUDO", "")
    (step,) = rw.plan(["manylinux-x64"], tmp_path / "ITK", "abc123", "6.0b3")
    assert step.env["NO_SUDO"] == ""
    assert step.env["TARGET_ARCH"] == "x64"
    assert step.dist_dir.parent.name == "ITKPythonPackage-manylinux_2_28-x64-build"


@pytest.fixture
def itk_repository(tmp_path, monkeypatch):
    """A repository with a tag, a branch and a commit only reachable by hash."""
    for key, value in {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
        "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig"),
    }.items():
        monkeypatch.setenv(key, value)
    repo = tmp_path / "upstream"

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True
        ).stdout.strip()

    repo.mkdir()
    git("init", "-q", "-b", "main")
    (repo / "f").write_text("1")
    git("add", "f")
    git("commit", "-q", "-m", "one")
    git("tag", "v1.0b01")
    tagged = git("rev-parse", "HEAD")
    (repo / "f").write_text("2")
    git("commit", "-q", "-am", "two")
    main = git("rev-parse", "HEAD")
    return repo, tagged, main


def test_refs_resolve_to_commits(tmp_path, itk_repository):
    repo, tagged, main = itk_repository
    src = tmp_path / "build" / "ITK"
    assert rw.prepare_itk_source(src, str(repo), "v1.0b01") == (tagged, True)
    assert rw.prepare_itk_source(src, str(repo), "main") == (main, False)
    assert rw.prepare_itk_source(src, str(repo), main[:10]) == (main, False)
    with pytest.raises(SystemExit):
        rw.prepare_itk_source(src, str(repo), "no-such-ref")


def test_a_branch_resolves_to_the_fetched_tip(tmp_path, itk_repository):
    repo, _, _ = itk_repository
    src = tmp_path / "build" / "ITK"
    rw.prepare_itk_source(src, str(repo), "main")
    (repo / "f").write_text("3")
    subprocess.run(["git", "commit", "-q", "-am", "three"], cwd=repo, check=True)
    newer = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert rw.prepare_itk_source(src, str(repo), "main") == (newer, False)


def test_a_source_tree_with_local_changes_is_not_used(tmp_path, itk_repository):
    repo, _, _ = itk_repository
    src = tmp_path / "build" / "ITK"
    rw.prepare_itk_source(src, str(repo), "main")
    (src / "f").write_text("edited")
    with pytest.raises(SystemExit, match="uncommitted"):
        rw.prepare_itk_source(src, str(repo), "main")


def test_a_directory_that_is_not_a_repository_is_not_used(tmp_path, itk_repository):
    repo, _, _ = itk_repository
    src = tmp_path / "build" / "ITK"
    src.mkdir(parents=True)
    with pytest.raises(SystemExit, match="not a git repository"):
        rw.prepare_itk_source(src, str(repo), "main")


def test_every_build_is_stamped_with_the_itk_commit_time(tmp_path, itk_repository):
    repo, tagged, _ = itk_repository
    src = tmp_path / "ITK"
    commit, _ = rw.prepare_itk_source(src, str(repo), "v1.0b01")
    expected = rw._git("log", "-1", "--format=%ct", tagged, cwd=repo).stdout.strip()
    epoch = rw.wheel_epoch(src, commit)
    assert epoch == expected
    steps = rw.plan(
        ["macos-arm64", "manylinux-aarch64"], src, commit, "1.0b1", epoch=epoch
    )
    assert [s.env["SOURCE_DATE_EPOCH"] for s in steps] == [expected, expected]


def test_a_caller_set_epoch_wins(tmp_path, itk_repository, monkeypatch):
    repo, _, _ = itk_repository
    src = tmp_path / "ITK"
    commit, _ = rw.prepare_itk_source(src, str(repo), "main")
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1234567890")
    assert rw.wheel_epoch(src, commit) == "1234567890"


def test_the_summary_lists_this_runs_wheels_only(tmp_path):
    dist = tmp_path / "dist"
    earlier = dist / "earlier-wheels" / "20261119_020000"
    earlier.mkdir(parents=True)
    (earlier / "itk_core-6.0b2-cp311-abi3-macosx_11_0_arm64.whl").write_bytes(b"")
    current = dist / "itk_core-6.0b3-cp311-abi3-macosx_11_0_arm64.whl"
    current.write_bytes(b"")
    step = rw.Step("macos-arm64", [], dist_dir=dist)
    assert rw.built_wheels(step) == [current]
