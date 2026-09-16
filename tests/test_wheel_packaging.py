from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from wheel_packaging import (
    create_posix_tarball,
    post_build_cleanup,
    remove_uncompressed_tar,
    tarball_paths,
)


def _cleanup_builder(build_root: Path, arch: str):
    """A builder stub carrying exactly what post_build_cleanup reads."""
    source_dir = build_root / "src"
    source_dir.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        build_dir_root=build_root,
        package_env_config={"IPP_SOURCE_DIR": source_dir, "ARCH": arch},
    )


def _run_cleanup(build_root: Path, arch: str) -> set[str]:
    """Run the real cleanup and return the names it left behind."""
    post_build_cleanup(_cleanup_builder(build_root, arch))
    survivors = set()
    for sub in ("build", "dist"):
        survivors |= {p.name for p in (build_root / sub).iterdir()}
    return survivors


def test_cleanup_selects_build_dirs_and_archives(tmp_path):
    (tmp_path / "build").mkdir()
    (tmp_path / "dist").mkdir()
    (tmp_path / "build" / "ITK-linux-py311_x64").mkdir()
    (tmp_path / "build" / "ITK-linux-py311_aarch64").mkdir()
    # Real archive naming: ITKPythonBuilds-{platform}-{arch}.tar[.zst]
    (tmp_path / "dist" / "ITKPythonBuilds-linux-x64.tar.zst").touch()
    (tmp_path / "dist" / "itk_core-6.0.0-cp311-abi3.whl").touch()

    survivors = _run_cleanup(tmp_path, "x64")
    assert "ITK-linux-py311_x64" not in survivors
    assert "ITK-linux-py311_aarch64" in survivors
    assert "ITKPythonBuilds-linux-x64.tar.zst" not in survivors
    assert "itk_core-6.0.0-cp311-abi3.whl" in survivors


def test_tarball_is_written_under_dist(tmp_path):
    """The cache goes in dist/, which containers mount; the parent is not."""
    tar_path, zst_path = tarball_paths(tmp_path, "linux", "x64")
    assert tar_path.parent == tmp_path / "dist"
    assert zst_path.parent == tmp_path / "dist"
    assert tar_path.name == "ITKPythonBuilds-linux-x64.tar"
    assert zst_path.name == "ITKPythonBuilds-linux-x64.tar.zst"


def test_uncompressed_tar_is_removed_after_zstd(tmp_path):
    """A 2.5 GB .tar must not be left beside the compressed cache."""
    dist = tmp_path / "dist"
    dist.mkdir()
    tar_path = dist / "ITKPythonBuilds-linux-x64.tar"
    zst_path = dist / "ITKPythonBuilds-linux-x64.tar.zst"
    tar_path.touch()
    zst_path.touch()
    remove_uncompressed_tar(tar_path)
    assert not tar_path.exists()
    assert zst_path.exists()


DIRNAMES = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")),
    min_size=1,
    max_size=12,
)


@given(other=DIRNAMES)
# Deadline disabled: each example does real filesystem I/O.
@settings(deadline=None)
def test_cleanup_never_removes_a_wheel(other, tmp_path_factory):
    """Cleanup must never reach the wheels sitting beside the archives."""
    root = tmp_path_factory.mktemp("cleanup")
    (root / "build").mkdir()
    (root / "dist").mkdir()
    (root / "build" / f"ITK-{other}_x64").mkdir(exist_ok=True)
    wheel = root / "dist" / "itk_core-6.0.0-cp311-abi3.whl"
    wheel.touch()
    post_build_cleanup(_cleanup_builder(root, "x64"))
    assert wheel.exists()


class _FakeBuilder:
    """A builder stub whose echo_check_call mimics the real semantics.

    ``check=True`` raises on a non-zero status; otherwise the status is
    merely returned, exactly as ``build_environment.echo_check_call`` does.
    """

    def __init__(self, build_dir_root: Path, tar_ok: bool, zstd_ok: bool):
        source_dir = build_dir_root.parent / "ITKPythonPackage"
        source_dir.mkdir(parents=True, exist_ok=True)
        build_dir_root.mkdir(parents=True, exist_ok=True)
        self.build_dir_root = build_dir_root
        self.package_env_config = {"IPP_SOURCE_DIR": source_dir, "ARCH": "x64"}
        self._tar_ok = tar_ok
        self._zstd_ok = zstd_ok
        self.commands: list[str] = []

    def echo_check_call(self, cmd, check: bool = False, **kwargs) -> int:
        cmd = [str(c) for c in cmd]
        tool = cmd[0]
        self.commands.append(tool)
        ok = self._tar_ok if tool == "tar" else self._zstd_ok
        if ok:
            # Emulate the artifact the real tool would write.
            output = cmd[cmd.index("-cf") + 1] if tool == "tar" else cmd[-1]
            Path(output).write_bytes(b"payload")
            return 0
        if check:
            raise RuntimeError(f"{tool} failed")
        return 1


def test_failed_tar_aborts_before_zstd(tmp_path):
    """A tar that produces nothing must stop the cache from being published."""
    builder = _FakeBuilder(tmp_path / "build-root", tar_ok=False, zstd_ok=True)
    with pytest.raises(RuntimeError):
        create_posix_tarball(builder)
    assert "zstd" not in builder.commands


def test_failed_zstd_does_not_delete_the_uncompressed_tar(tmp_path):
    """The .tar is the only remaining artifact when zstd fails; keep it."""
    build_root = tmp_path / "build-root"
    builder = _FakeBuilder(build_root, tar_ok=True, zstd_ok=False)
    with pytest.raises(RuntimeError):
        create_posix_tarball(builder)
    dist = build_root / "dist"
    assert [p.name for p in dist.glob("ITKPythonBuilds-*.tar")]
    assert not list(dist.glob("ITKPythonBuilds-*.tar.zst"))


def test_git_directory_is_excluded_entirely_not_just_its_contents():
    """A surviving empty .git makes git report "not a repository".

    Excluding only the contents leaves the directory, so a consumer cannot
    tell "no repository here" from a broken one by looking at the path. That
    is how the cache path failed in CI.
    """
    import wheel_packaging

    source = Path(wheel_packaging.__file__).read_text()
    assert '"--exclude=*/.git",' in source
    assert '"--exclude=*/.git/*"' not in source
