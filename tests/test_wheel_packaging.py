import shutil
import subprocess
import tarfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from unittest.mock import patch

import build_python_instance_base
import pytest
from cmake_argument_builder import CMakeArgumentBuilder
from hypothesis import given, settings
from hypothesis import strategies as st
from macos_build_python_instance import MacOSBuildPythonInstance
from wheel_packaging import (
    create_posix_tarball,
    move_earlier_wheels,
    post_build_cleanup,
    remove_uncompressed_tar,
    tarball_paths,
)


def _cleanup(build_root: Path, arch: str) -> None:
    """Run the real cleanup with a source directory under *build_root*."""
    source_dir = build_root / "src"
    source_dir.mkdir(parents=True, exist_ok=True)
    post_build_cleanup(build_root, arch, source_dir, "")


def _run_cleanup(build_root: Path, arch: str) -> set[str]:
    """Run the real cleanup and return the names it left behind."""
    _cleanup(build_root, arch)
    survivors = set()
    for sub in ("build", "dist"):
        survivors |= {p.name for p in (build_root / sub).iterdir()}
    return survivors


def test_cleanup_keeps_a_build_root_inside_the_checkout(tmp_path: Path) -> None:
    """--build-dir-root <ipp>/build must not lose its wheels."""
    build_root = tmp_path / "build"
    (build_root / "dist").mkdir(parents=True)
    (build_root / "dist" / "itk_core-6.0.0-cp311-abi3.whl").touch()
    post_build_cleanup(build_root, "x64", tmp_path, "")
    assert (build_root / "dist" / "itk_core-6.0.0-cp311-abi3.whl").exists()


def test_cleanup_selects_build_dirs_and_archives(tmp_path: Path) -> None:
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


def test_tarball_is_written_under_dist(tmp_path: Path) -> None:
    """The cache goes in dist/, which containers mount; the parent is not."""
    tar_path, zst_path = tarball_paths(tmp_path, "linux", "x64")
    assert tar_path.parent == tmp_path / "dist"
    assert zst_path.parent == tmp_path / "dist"
    assert tar_path.name == "ITKPythonBuilds-linux-x64.tar"
    assert zst_path.name == "ITKPythonBuilds-linux-x64.tar.zst"


def test_uncompressed_tar_is_removed_after_zstd(tmp_path: Path) -> None:
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
def test_cleanup_never_removes_a_wheel(
    other: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Cleanup must never reach the wheels sitting beside the archives."""
    root = tmp_path_factory.mktemp("cleanup")
    (root / "build").mkdir()
    (root / "dist").mkdir()
    (root / "build" / f"ITK-{other}_x64").mkdir(exist_ok=True)
    wheel = root / "dist" / "itk_core-6.0.0-cp311-abi3.whl"
    wheel.touch()
    _cleanup(root, "x64")
    assert wheel.exists()


class _FakeBuilder:
    """A builder stub whose echo_check_call mimics the real semantics.

    ``check=True`` raises on a non-zero status; otherwise the status is
    merely returned, exactly as ``build_environment.echo_check_call`` does.
    """

    def __init__(self, build_dir_root: Path, tar_ok: bool, zstd_ok: bool) -> None:
        source_dir = build_dir_root.parent / "ITKPythonPackage"
        source_dir.mkdir(parents=True, exist_ok=True)
        build_dir_root.mkdir(parents=True, exist_ok=True)
        self.build_dir_root = build_dir_root
        self.source_dir = source_dir
        self._tar_ok = tar_ok
        self._zstd_ok = zstd_ok
        self.commands: list[str] = []

    def create_tarball(self) -> None:
        create_posix_tarball(
            self.build_dir_root,
            "x64",
            self.source_dir,
            "linux",
            self.echo_check_call,
        )

    def echo_check_call(
        self, cmd: Sequence[str | Path], check: bool = False, **kwargs: Any
    ) -> int:
        args = [str(c) for c in cmd]
        tool = args[0]
        self.commands.append(tool)
        ok = self._tar_ok if tool == "tar" else self._zstd_ok
        if ok:
            # Emulate the artifact the real tool would write.
            output = args[args.index("-cf") + 1] if tool == "tar" else args[-1]
            Path(output).write_bytes(b"payload")
            return 0
        if check:
            msg = f"{tool} failed"
            raise RuntimeError(msg)
        return 1


def test_failed_tar_aborts_before_zstd(tmp_path: Path) -> None:
    """A tar that produces nothing must stop the cache from being published."""
    builder = _FakeBuilder(tmp_path / "build-root", tar_ok=False, zstd_ok=True)
    with pytest.raises(RuntimeError):
        builder.create_tarball()
    assert "zstd" not in builder.commands


def test_failed_zstd_does_not_delete_the_uncompressed_tar(tmp_path: Path) -> None:
    """The .tar is the only remaining artifact when zstd fails; keep it."""
    build_root = tmp_path / "build-root"
    builder = _FakeBuilder(build_root, tar_ok=True, zstd_ok=False)
    with pytest.raises(RuntimeError):
        builder.create_tarball()
    dist = build_root / "dist"
    assert [p.name for p in dist.glob("ITKPythonBuilds-*.tar")]
    assert not list(dist.glob("ITKPythonBuilds-*.tar.zst"))


class _RealTarBuilder(_FakeBuilder):
    """Runs the real tar command so its exclusions are exercised; fakes zstd."""

    def echo_check_call(
        self, cmd: Sequence[str | Path], check: bool = False, **kwargs: Any
    ) -> int:
        args = [str(c) for c in cmd]
        if args[0] != "tar":
            return super().echo_check_call(args, check=check, **kwargs)
        self.commands.append("tar")
        status = subprocess.run(args, check=check).returncode
        # Keep a copy: create_posix_tarball deletes the .tar once compressed.
        self.archive = self.build_dir_root / "archive-copy.tar"
        shutil.copy(args[args.index("-cf") + 1], self.archive)
        return status


@pytest.mark.skipif(shutil.which("tar") is None, reason="needs tar")
def test_git_directory_is_excluded_entirely_not_just_its_contents(
    tmp_path: Path,
) -> None:
    """A surviving empty .git makes git report "not a repository".

    Excluding only the contents leaves the directory, so a consumer cannot
    tell "no repository here" from a broken one by looking at the path. That
    is how the cache path failed in CI.
    """
    build_root = tmp_path / "build-root"
    builder = _RealTarBuilder(build_root, tar_ok=True, zstd_ok=True)
    git_dir = build_root / "ITK-source" / "ITK" / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")
    (git_dir.parent / "CMakeLists.txt").write_text("project(ITK)\n")

    builder.create_tarball()

    with tarfile.open(builder.archive) as archive:
        names = archive.getnames()
    assert any(n.endswith("ITK/CMakeLists.txt") for n in names)
    assert not [n for n in names if ".git" in Path(n).parts]


def test_earlier_wheels_move_out_of_the_top_of_dist(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / "itk_core-6.0b2-cp311-abi3-manylinux_2_28_x86_64.whl"
    wheel.write_bytes(b"old")
    tarball = dist / "ITKPythonBuilds-linux-x64.tar.zst"
    tarball.write_bytes(b"cache")
    report = dist / "build_log_manylinux228-py311.json"
    report.write_text("{}")

    moved_to = move_earlier_wheels(dist, "20261119_020000")

    assert moved_to == dist / "earlier-wheels" / "20261119_020000"
    assert list(dist.glob("*.whl")) == []
    assert (moved_to / wheel.name).read_bytes() == b"old"
    assert tarball.exists()
    assert report.exists()


def test_no_wheels_means_nothing_moves(tmp_path: Path) -> None:
    assert move_earlier_wheels(tmp_path, "20261119_020000") is None
    assert list(tmp_path.iterdir()) == []


def test_the_wheel_step_starts_from_an_empty_dist(
    macos_builder: MacOSBuildPythonInstance,
) -> None:
    """Repair and the import test glob dist/*.whl; an earlier wheel must not be there."""
    dist = macos_builder.build_dir_root / "dist"
    dist.mkdir()
    (dist / "itk_core-6.0b2-cp311-abi3-macosx_11_0_arm64.whl").write_bytes(b"")
    new_wheel = dist / "itk_core-6.0b3-cp311-abi3-macosx_11_0_arm64.whl"
    macos_builder.wheel_names = ["itk-core"]
    macos_builder.cleanup = False
    macos_builder.ipp_dir = macos_builder.build_dir_root
    macos_builder.cmake_cmdline_definitions = CMakeArgumentBuilder()
    with (
        patch.object(
            macos_builder,
            "echo_check_call",
            lambda _cmd, **_kw: new_wheel.write_bytes(b""),
        ),
        patch.object(
            build_python_instance_base, "configure_one_pyproject_file", lambda *_: None
        ),
    ):
        macos_builder.build_itk_python_wheels()

    assert sorted(dist.glob("*.whl")) == [new_wheel]


def test_cleanup_removes_listed_module_clones_and_skips_bare_names(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "src"
    (source_dir / "ITKFoo").mkdir(parents=True)
    (source_dir / "Bare").mkdir()
    post_build_cleanup(tmp_path, "x64", source_dir, "Bare@v1:Org/ITKFoo@v2")
    assert not (source_dir / "ITKFoo").exists()
    assert (source_dir / "Bare").exists()
