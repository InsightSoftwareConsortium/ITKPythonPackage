"""Regression tests for the Windows wheel builder's fragile details.

Each test here pins a defect that shipped once: a repaired remote-module
wheel written to the wrong ``dist/``, and a 7-Zip invocation whose ``-r``
turned every archive argument into a recursive pattern.
"""

from pathlib import Path
from unittest.mock import patch


def test_remote_module_repaired_wheel_lands_in_the_module_dist(
    tmp_path, windows_builder
):
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

    captured = {}

    def fake_repair(cmd, *args, **kwargs) -> int:
        rendered = [str(c) for c in cmd]
        out_dir = Path(rendered[rendered.index("-w") + 1])
        captured["out_dir"] = out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / wheel.name).touch()
        return 0

    with patch.object(windows_builder, "echo_check_call", side_effect=fake_repair):
        windows_builder.fixup_wheel(
            str(wheel), lib_paths="C:/tbb/bin", remote_module_wheel=True
        )

    assert captured["out_dir"] == expected_dir
    assert (expected_dir / wheel.name).exists()


def test_non_remote_repaired_wheel_lands_in_the_build_dist(tmp_path, windows_builder):
    """Without ``remote_module_wheel`` the main build ``dist/`` is still used."""
    windows_builder.module_source_dir = tmp_path / "BioCell"
    main_dist = windows_builder.build_dir_root / "dist"
    main_dist.mkdir(parents=True, exist_ok=True)
    wheel = main_dist / "itk_core-6.0.0-cp311-abi3-win_amd64.whl"
    wheel.touch()

    captured = {}

    def fake_repair(cmd, *args, **kwargs) -> int:
        rendered = [str(c) for c in cmd]
        out_dir = Path(rendered[rendered.index("-w") + 1])
        captured["out_dir"] = out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / wheel.name).touch()
        return 0

    with patch.object(windows_builder, "echo_check_call", side_effect=fake_repair):
        windows_builder.fixup_wheel(str(wheel), lib_paths="C:/tbb/bin")

    assert captured["out_dir"] == main_dist
    assert not (windows_builder.module_source_dir / "dist").exists()


def _run_build_tarball(windows_builder, tmp_path):
    """Drive ``build_tarball`` down the 7-Zip branch and return the command."""
    windows_builder.ipp_dir = tmp_path / "IPP"
    windows_builder.ipp_dir.mkdir(parents=True, exist_ok=True)
    captured = {}

    def fake_call(cmd, *args, **kwargs) -> int:
        captured["cmd"] = [str(c) for c in cmd]
        return 0

    with (
        patch("windows_build_python_instance.shutil.which", return_value="/fake/7z"),
        patch.object(windows_builder, "echo_check_call", side_effect=fake_call),
    ):
        windows_builder.build_tarball()
    return captured["cmd"]


def test_seven_zip_command_carries_no_recursive_flag(tmp_path, windows_builder):
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


def test_seven_zip_archives_absolute_roots_not_bare_names(tmp_path, windows_builder):
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
