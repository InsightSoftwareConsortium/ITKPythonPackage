"""Tests for where the Windows builder writes repaired wheels and what it archives."""

import zipfile
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from windows_build_python_instance import WindowsBuildPythonInstance


def _fake_delvewheel(wheel: Path) -> tuple[Callable[..., int], list[Path]]:
    """A delvewheel stand-in that writes the repaired *wheel* into its ``-w`` dir.

    Returns the stand-in and the list of output directories it was given.
    """
    out_dirs: list[Path] = []

    def fake_repair(cmd: Sequence[object], *args: object, **kwargs: object) -> int:
        rendered = [str(c) for c in cmd]
        out_dir = Path(rendered[rendered.index("-w") + 1])
        out_dirs.append(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / wheel.name).write_bytes(b"repaired")
        return 0

    return fake_repair, out_dirs


def test_remote_module_repaired_wheel_lands_in_the_module_dist(
    tmp_path: Path, windows_builder: WindowsBuildPythonInstance
) -> None:
    """A remote module's repaired wheel belongs in the module's own ``dist/``.

    The expectation is derived from ``module_source_dir`` rather than
    written out, so hardcoding any other path in the builder fails here
    even if the fixture happened to make the two agree.
    """
    windows_builder.module_source_dir = tmp_path / "BioCell"
    expected_dir = windows_builder.module_source_dir / "dist"
    main_dist = windows_builder.build_dir_root / "dist"
    main_dist.mkdir(parents=True, exist_ok=True)
    wheel = main_dist / "biocell-1.0.0-cp311-abi3-win_amd64.whl"
    wheel.touch()

    fake_repair, out_dirs = _fake_delvewheel(wheel)
    with patch.object(windows_builder, "echo_check_call", side_effect=fake_repair):
        windows_builder.fixup_wheel(
            str(wheel), lib_paths="C:/tbb/bin", remote_module_wheel=True
        )

    assert out_dirs[0].parent == expected_dir
    assert (expected_dir / wheel.name).exists()


def test_non_remote_repaired_wheel_lands_in_the_build_dist(
    tmp_path: Path, windows_builder: WindowsBuildPythonInstance
) -> None:
    """Without ``remote_module_wheel`` the main build ``dist/`` is still used."""
    windows_builder.module_source_dir = tmp_path / "BioCell"
    main_dist = windows_builder.build_dir_root / "dist"
    main_dist.mkdir(parents=True, exist_ok=True)
    wheel = main_dist / "itk_core-6.0.0-cp311-abi3-win_amd64.whl"
    wheel.touch()

    fake_repair, out_dirs = _fake_delvewheel(wheel)
    with patch.object(windows_builder, "echo_check_call", side_effect=fake_repair):
        windows_builder.fixup_wheel(str(wheel), lib_paths="C:/tbb/bin")

    assert out_dirs[0].parent == main_dist
    assert not (windows_builder.module_source_dir / "dist").exists()


def test_repair_that_writes_nothing_fails_even_beside_the_input(
    windows_builder: WindowsBuildPythonInstance,
) -> None:
    """ITK wheels are repaired in the ``dist/`` they were built in.

    The unrepaired input already sits at the output name there, so the
    check must look somewhere delvewheel alone writes.
    """
    main_dist = windows_builder.build_dir_root / "dist"
    main_dist.mkdir(parents=True, exist_ok=True)
    wheel = main_dist / "itk_core-6.0.0-cp311-abi3-win_amd64.whl"
    wheel.write_bytes(b"unrepaired")

    with (
        patch.object(windows_builder, "echo_check_call", return_value=0),
        pytest.raises(RuntimeError, match="delvewheel repair failed"),
    ):
        windows_builder.fixup_wheel(str(wheel))


def test_repaired_wheel_replaces_the_input_in_place(
    windows_builder: WindowsBuildPythonInstance,
) -> None:
    """A successful repair leaves only the repaired wheel in ``dist/``."""
    main_dist = windows_builder.build_dir_root / "dist"
    main_dist.mkdir(parents=True, exist_ok=True)
    wheel = main_dist / "itk_core-6.0.0-cp311-abi3-win_amd64.whl"
    wheel.write_bytes(b"unrepaired")

    fake_repair, _ = _fake_delvewheel(wheel)
    with patch.object(windows_builder, "echo_check_call", side_effect=fake_repair):
        windows_builder.fixup_wheel(str(wheel))

    assert wheel.read_bytes() == b"repaired"
    assert sorted(p.name for p in main_dist.iterdir()) == [wheel.name]


def _run_build_tarball(
    windows_builder: WindowsBuildPythonInstance, tmp_path: Path
) -> list[str]:
    """Drive ``build_tarball`` down the 7-Zip branch and return the command."""
    windows_builder.ipp_dir = tmp_path / "IPP"
    windows_builder.ipp_dir.mkdir(parents=True, exist_ok=True)
    captured: dict[str, list[str]] = {}

    def fake_call(cmd: Sequence[object], *args: object, **kwargs: object) -> int:
        captured["cmd"] = [str(c) for c in cmd]
        return 0

    with (
        patch("windows_build_python_instance.shutil.which", return_value="/fake/7z"),
        patch.object(windows_builder, "echo_check_call", side_effect=fake_call),
    ):
        windows_builder.build_tarball()
    return captured["cmd"]


def test_seven_zip_command_carries_no_recursive_flag(
    tmp_path: Path, windows_builder: WindowsBuildPythonInstance
) -> None:
    """``-r`` makes 7-Zip treat each name as a recursive pattern.

    With it, the bare directory name ``build`` matches every directory of
    that name beneath the build root, so a remote module's CMake tree is
    swept into the cached tarball and later extracted over a consumer's
    checkout. Directory arguments recurse without ``-r`` anyway.
    """
    cmd = _run_build_tarball(windows_builder, tmp_path)

    assert cmd[1] == "a"
    assert "-r" not in cmd
    assert "-r0" not in cmd


def test_seven_zip_archives_absolute_roots_not_bare_names(
    tmp_path: Path, windows_builder: WindowsBuildPythonInstance
) -> None:
    """Each archived root is an absolute path under the build root.

    A bare ``build``/``ITK`` name is what makes ``-r`` dangerous; pinning
    the absolute form keeps the arguments unambiguous to 7-Zip.
    """
    cmd = _run_build_tarball(windows_builder, tmp_path)

    for root in ("ITK", "build"):
        expected = str(windows_builder.build_dir_root / root)
        assert expected in cmd
        assert root not in cmd
    assert str(windows_builder.ipp_dir) in cmd


def test_zip_fallback_archives_the_seven_zip_roots(
    tmp_path: Path, windows_builder: WindowsBuildPythonInstance
) -> None:
    """Without 7-Zip the zip holds the same roots and exclusions."""
    root = windows_builder.build_dir_root
    windows_builder.ipp_dir = tmp_path / "IPP"
    files = {
        root / "ITK" / "CMakeLists.txt": True,
        root / "ITK" / ".git" / "HEAD": False,
        root / "build" / "lib" / "itk.lib": True,
        root / "build" / "obj" / "a.obj": False,
        root / "build" / "Wrapping" / "Modules" / "x.i": False,
        root / "build" / "Wrapping" / "Generators" / "y.i": True,
        root / "dist" / "itk-6.0.0-cp311-abi3-win_amd64.whl": False,
        windows_builder.ipp_dir / "scripts" / "build_wheels.py": True,
        windows_builder.ipp_dir / "scripts" / "__pycache__" / "z.pyc": False,
    }
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")

    with (
        patch("windows_build_python_instance.shutil.which", return_value=None),
        patch.object(windows_builder, "echo_check_call") as call,
    ):
        windows_builder.build_tarball()
    call.assert_not_called()

    with zipfile.ZipFile(root / "ITKPythonBuilds-windows.zip") as archive:
        names = set(archive.namelist())
    expected = {
        path.relative_to(
            windows_builder.ipp_dir.parent
            if path.is_relative_to(windows_builder.ipp_dir)
            else root
        ).as_posix()
        for path, kept in files.items()
        if kept
    }
    assert names == expected


def test_venv_paths_names_the_version_and_stable_abi_libraries(
    tmp_path: Path, windows_builder: WindowsBuildPythonInstance
) -> None:
    env_root = tmp_path / "env"
    (env_root / "include").mkdir(parents=True)
    (env_root / "libs").mkdir()
    (env_root / "libs" / "python311.lib").touch()
    (env_root / "libs" / "python3.lib").touch()
    windows_builder.config = replace(
        windows_builder.config, python_executable=env_root / "python.exe"
    )

    env = windows_builder.venv_paths()

    assert env.root_dir == env_root
    assert env.include_dir == env_root / "include"
    assert env.library == env_root / "libs" / "python311.lib"
    assert env.sabi_library == env_root / "libs" / "python3.lib"
    assert env.bin_path == env_root
    assert env.executable is None


def test_venv_paths_refuses_a_missing_stable_abi_library(
    tmp_path: Path, windows_builder: WindowsBuildPythonInstance
) -> None:
    env_root = tmp_path / "env"
    (env_root / "include").mkdir(parents=True)
    (env_root / "libs").mkdir()
    (env_root / "libs" / "python311.lib").touch()
    windows_builder.config = replace(
        windows_builder.config, python_executable=env_root / "python.exe"
    )
    with pytest.raises(FileNotFoundError, match=r"python3\.lib"):
        windows_builder.venv_paths()
