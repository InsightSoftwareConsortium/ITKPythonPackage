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
    wheel = _module_wheel(main_dist)

    fake_repair, out_dirs = _fake_module_delvewheel()
    with patch.object(windows_builder, "echo_check_call", side_effect=fake_repair):
        windows_builder.fixup_wheel(
            str(wheel), lib_paths="C:/tbb/bin", remote_module_wheel=True
        )

    assert out_dirs[0].parent == expected_dir
    assert (expected_dir / wheel.name).exists()


def _module_wheel(dist: Path, own_init: str | None = None) -> Path:
    """A minimal itk-biocell wheel, optionally shipping its own module init."""
    dist.mkdir(parents=True, exist_ok=True)
    wheel = dist / "itk_biocell-1.0.0-cp311-abi3-win_amd64.whl"
    info = "itk_biocell-1.0.0.dist-info"
    members = {
        "itk/_BioCellPython.pyd": "binary",
        f"{info}/METADATA": "Metadata-Version: 2.1\nName: itk-biocell\nVersion: 1.0.0\n",
    }
    if own_init is not None:
        members["itk/__init_biocell__.py"] = own_init
    members[f"{info}/RECORD"] = "".join(f"{n},sha256=x,1\n" for n in members) + (
        f"{info}/RECORD,,\n"
    )
    with zipfile.ZipFile(wheel, "w") as zf:
        for name, text in members.items():
            zf.writestr(name, text)
    return wheel


def _fake_module_delvewheel() -> tuple[Callable[..., int], list[Path]]:
    """delvewheel's effect on a module wheel: its DLL setup goes into itk/__init__.py."""
    out_dirs: list[Path] = []

    def fake_repair(cmd: Sequence[object], *args: object, **kwargs: object) -> int:
        rendered = [str(c) for c in cmd]
        out_dir = Path(rendered[rendered.index("-w") + 1])
        out_dirs.append(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        source = Path(rendered[-1])
        with zipfile.ZipFile(source) as zf:
            members = {n: zf.read(n) for n in zf.namelist()}
        patched = members.get("itk/__init__.py", b"") + b"# delvewheel DLL setup\n"
        members["itk/__init__.py"] = patched
        with zipfile.ZipFile(out_dir / source.name, "w") as zf:
            for name, data in members.items():
                zf.writestr(name, data)
        return 0

    return fake_repair, out_dirs


@pytest.mark.parametrize("own_init", [None, "print('biocell')\n"])
def test_a_module_wheel_never_ships_itk_init(
    tmp_path: Path, windows_builder: WindowsBuildPythonInstance, own_init: str | None
) -> None:
    """Installing it would replace itk-core's itk/__init__.py."""
    windows_builder.module_source_dir = tmp_path / "BioCell"
    wheel = _module_wheel(windows_builder.build_dir_root / "dist", own_init)
    fake_repair, _ = _fake_module_delvewheel()
    with patch.object(windows_builder, "echo_check_call", side_effect=fake_repair):
        windows_builder.fixup_wheel(str(wheel), remote_module_wheel=True)

    repaired = windows_builder.module_source_dir / "dist" / wheel.name
    with zipfile.ZipFile(repaired) as zf:
        names = zf.namelist()
        init = zf.read("itk/__init_biocell__.py").decode()
        record = zf.read("itk_biocell-1.0.0.dist-info/RECORD").decode()
    assert "itk/__init__.py" not in names
    assert init.endswith("# delvewheel DLL setup\n")
    assert init.startswith(own_init or "#")
    if own_init is not None:
        assert "itk/__init_biocell__.py," in record


def test_a_module_wheel_is_repaired_with_lib_paths_and_onetbb(
    windows_builder: WindowsBuildPythonInstance,
) -> None:
    """delvewheel looks for a module's DLLs where it looks for itk-core's."""
    windows_builder.windows_extra_lib_paths = ["C:/CUDA/bin"]
    with patch.object(windows_builder, "fixup_wheel") as fixup:
        windows_builder.fixup_module_wheel("module.whl")
    tbb_bin = str(windows_builder.build_dir_root / "build" / "oneTBB-prefix" / "bin")
    assert fixup.call_args.args[1] == f"C:/CUDA/bin;{tbb_bin}"


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


@pytest.mark.parametrize("excludes", [["nvcuda.dll"], "nvcuda.dll;"])
def test_excluded_dlls_go_to_delvewheel_no_dll(
    windows_builder: WindowsBuildPythonInstance, excludes: list[str] | str
) -> None:
    """``--exclude-libs nvcuda.dll`` keeps the CUDA driver out of RTK's wheel."""
    main_dist = windows_builder.build_dir_root / "dist"
    main_dist.mkdir(parents=True, exist_ok=True)
    wheel = main_dist / "itk_rtk-2.7.0-cp311-abi3-win_amd64.whl"
    wheel.touch()
    windows_builder.windows_exclude_libs = excludes
    fake_repair, _ = _fake_delvewheel(wheel)
    with patch.object(
        windows_builder, "echo_check_call", side_effect=fake_repair
    ) as called:
        windows_builder.fixup_wheel(str(wheel))
    cmd = called.call_args.args[0]
    assert cmd[cmd.index("--no-dll") + 1] == "nvcuda.dll"


def test_no_dll_is_omitted_without_exclude_libs(
    windows_builder: WindowsBuildPythonInstance,
) -> None:
    assert windows_builder._no_dll_arguments() == []


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


def test_seven_zip_starts_a_new_archive(
    tmp_path: Path, windows_builder: WindowsBuildPythonInstance
) -> None:
    stale = windows_builder.build_dir_root / "ITKPythonBuilds-windows.zip"
    stale.write_text("an archive from an earlier build")
    _run_build_tarball(windows_builder, tmp_path)
    assert not stale.exists()


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
        patch("windows_build_python_instance.SEVEN_ZIP_CANDIDATES", ()),
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
