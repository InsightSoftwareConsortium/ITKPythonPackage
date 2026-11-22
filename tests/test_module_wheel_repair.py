"""A remote module build repairs only the wheels it produced (issue #247)."""

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from cmake_argument_builder import CMakeArgumentBuilder
from linux_build_python_instance import LinuxBuildPythonInstance
from pyproject_configure import STABLE_ABI_TAG

NEW_WHEEL = f"itk_foo-1.0-{STABLE_ABI_TAG}-abi3-linux_x86_64.whl"


def _module(builder: LinuxBuildPythonInstance, tmp_path: Path) -> Path:
    builder.cmake_cmdline_definitions = CMakeArgumentBuilder()
    (tmp_path / "inc").mkdir()
    builder.python_env = replace(builder.python_env, include_dir=tmp_path / "inc")
    module = tmp_path / "ITKFoo"
    (module / "dist").mkdir(parents=True)
    builder.module_source_dir = module
    return module


def _build(
    builder: LinuxBuildPythonInstance, produced: Sequence[str]
) -> tuple[list[str], list[Path]]:
    """Run the module build with a fake wheel build; return repaired paths and outdirs."""
    outdirs: list[Path] = []
    repaired: list[str] = []

    def fake_build(cmd: Sequence[str | Path], *args: object, **kwargs: object) -> int:
        args_list = [str(c) for c in cmd]
        outdir = Path(args_list[args_list.index("--outdir") + 1])
        outdirs.append(outdir)
        for name in produced:
            (outdir / name).write_bytes(b"new")
        return 0

    with (
        patch.object(builder, "echo_check_call", side_effect=fake_build),
        patch.object(builder, "fixup_module_wheel", side_effect=repaired.append),
    ):
        builder.build_external_module_python_wheel()
    return repaired, outdirs


def test_leftover_wheels_are_not_repaired(
    tmp_path: Path, linux_builder: LinuxBuildPythonInstance
) -> None:
    dist = _module(linux_builder, tmp_path) / "dist"
    old = dist / f"itk_foo-0.9-{STABLE_ABI_TAG}-abi3-manylinux_2_28_x86_64.whl"
    old.write_bytes(b"old")
    # A non-abi3 leftover would fail verification if it were looked at.
    (dist / "itk_foo-0.9-cp310-cp310-linux_x86_64.whl").write_bytes(b"old")

    repaired, _ = _build(linux_builder, [NEW_WHEEL])

    assert repaired == [str(dist / NEW_WHEEL)]
    assert (dist / NEW_WHEEL).read_bytes() == b"new"
    assert old.read_bytes() == b"old"


def test_a_rebuilt_wheel_replaces_its_leftover(
    tmp_path: Path, linux_builder: LinuxBuildPythonInstance
) -> None:
    dist = _module(linux_builder, tmp_path) / "dist"
    (dist / NEW_WHEEL).write_bytes(b"old")

    repaired, _ = _build(linux_builder, [NEW_WHEEL])

    assert repaired == [str(dist / NEW_WHEEL)]
    assert (dist / NEW_WHEEL).read_bytes() == b"new"


def test_the_build_directory_is_removed(
    tmp_path: Path, linux_builder: LinuxBuildPythonInstance
) -> None:
    dist = _module(linux_builder, tmp_path) / "dist"

    _, outdirs = _build(linux_builder, [NEW_WHEEL])

    assert outdirs[0] != dist
    assert not outdirs[0].exists()
    assert sorted(p.name for p in dist.iterdir()) == [NEW_WHEEL]


def test_a_build_without_a_wheel_fails_despite_leftovers(
    tmp_path: Path, linux_builder: LinuxBuildPythonInstance
) -> None:
    dist = _module(linux_builder, tmp_path) / "dist"
    (dist / NEW_WHEEL).write_bytes(b"old")

    with pytest.raises(RuntimeError, match="No wheel was produced"):
        _build(linux_builder, [])
    assert sorted(p.name for p in dist.iterdir()) == [NEW_WHEEL]
