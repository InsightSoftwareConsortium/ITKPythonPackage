"""Choosing the wheel layout from the major version of the ITK source."""

import tomllib
from pathlib import Path

import pytest
from linux_build_python_instance import LinuxBuildPythonInstance
from pyproject_configure import (
    PyprojectInputs,
    configure_one_pyproject_file,
    get_wheel_dependencies,
)
from wheel_profile import (
    ITK5_PROFILE,
    ITK6_PROFILE,
    WheelProfile,
    itk_version_major,
    wheel_profile,
    wheel_profile_for_major,
)

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def itk_source(root: Path, major: str) -> Path:
    """A directory holding just the ``CMake/itkVersion.cmake`` of ITK *major*."""
    source = root / f"ITK{major}"
    (source / "CMake").mkdir(parents=True)
    (source / "CMake" / "itkVersion.cmake").write_text(
        "# ITK version number components.\n"
        f'set(ITK_VERSION_MAJOR "{major}")\n'
        'set(ITK_VERSION_MINOR "4")\n'
    )
    return source


@pytest.mark.parametrize(
    ("major", "profile"), [("5", ITK5_PROFILE), ("6", ITK6_PROFILE)]
)
def test_the_profile_follows_the_itk_major_version(
    tmp_path: Path, major: str, profile: WheelProfile
) -> None:
    source = itk_source(tmp_path, major)
    assert itk_version_major(source) == int(major)
    assert wheel_profile(source) == profile


def test_a_later_major_version_uses_the_newest_profile() -> None:
    assert wheel_profile_for_major(7) == ITK6_PROFILE


def test_itk_4_is_refused() -> None:
    with pytest.raises(ValueError, match="ITK 4"):
        wheel_profile_for_major(4)


def test_a_tree_without_a_version_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match=r"itkVersion\.cmake"):
        wheel_profile(tmp_path)


def test_itk5_has_the_wheels_published_for_itk_5_4() -> None:
    assert ITK5_PROFILE.wheel_names() == [
        "itk-core",
        "itk-numerics",
        "itk-io",
        "itk-filtering",
        "itk-registration",
        "itk-segmentation",
        "itk-meta",
    ]


def test_itk6_adds_filtering_extra() -> None:
    names = ITK6_PROFILE.wheel_names()
    assert len(names) == 8
    assert names[4] == "itk-filtering-extra"


def test_only_itk6_turns_on_ingested_remote_modules() -> None:
    assert ITK5_PROFILE.ingested_remote_modules == ()
    assert "Montage" in ITK6_PROFILE.ingested_remote_modules


@pytest.mark.parametrize(
    ("profile", "io_depends"),
    [(ITK5_PROFILE, ["itk-core==5.4.8"]), (ITK6_PROFILE, ["itk-numerics==5.4.8"])],
)
def test_io_depends_on_the_group_the_profile_names(
    profile: WheelProfile, io_depends: list[str]
) -> None:
    names = profile.wheel_names()
    depends = get_wheel_dependencies(profile.wheel_groups_file, "5.4.8", names)
    assert depends["itk-io"] == io_depends
    for name in names:
        assert name in depends


def test_an_itk5_builder_enables_no_ingested_modules(
    linux_builder: LinuxBuildPythonInstance,
) -> None:
    linux_builder.wheel_profile = ITK5_PROFILE
    linux_builder.enable_ingested_remote_modules()
    assert not any(
        key.startswith("Module_")
        for key in linux_builder.cmake_itk_source_build_configurations
    )


def test_the_itk5_meta_wheel_requires_the_itk5_wheels(tmp_path: Path) -> None:
    source = itk_source(tmp_path, "5")
    out = tmp_path / "out"
    out.mkdir()
    configure_one_pyproject_file(
        SCRIPTS_DIR, PyprojectInputs(source, "v5.4.8", "5.4.8"), out, "itk-meta"
    )
    pyproject = tomllib.loads((out / "pyproject.toml").read_text())
    assert pyproject["project"]["dependencies"] == [
        "itk-core==5.4.8",
        "itk-numerics==5.4.8",
        "itk-io==5.4.8",
        "itk-filtering==5.4.8",
        "itk-registration==5.4.8",
        "itk-segmentation==5.4.8",
        "numpy",
    ]
    assert (
        "-DITKPythonPackage_WHEEL_PROFILE:STRING=itk5"
        in pyproject["tool"]["scikit-build"]["cmake"]["args"]
    )
