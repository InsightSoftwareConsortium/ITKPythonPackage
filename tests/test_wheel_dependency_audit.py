import zipfile
from pathlib import Path

import pytest
from wheel_dependency_audit import audit, check, main, read_wheel


def make_wheel(
    dist: Path, name: str, requires: list[str], modules: dict[str, tuple[str, ...]]
) -> Path:
    path = dist / f"{name.replace('-', '_')}-6.0-cp311-abi3-linux_x86_64.whl"
    metadata = ["Metadata-Version: 2.1", f"Name: {name}", "Version: 6.0"]
    metadata += [f"Requires-Dist: {r}" for r in requires]
    with zipfile.ZipFile(path, "w") as whl:
        whl.writestr(f"{name}-6.0.dist-info/METADATA", "\n".join(metadata) + "\n")
        for module, depends in modules.items():
            whl.writestr(
                f"itk/Configuration/{module}Config.py",
                f"depends = {depends!r}\ntemplates = ()\n",
            )
    return path


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    make_wheel(
        tmp_path, "itk-core", ["numpy"], {"ITKCommon": ("ITKPyBase",), "ITKPyBase": ()}
    )
    make_wheel(
        tmp_path,
        "itk-numerics",
        ["itk-core==6.0"],
        {"ITKDisplacementField": ("ITKCommon",)},
    )
    return tmp_path


def test_reads_name_requirements_and_module_depends(dist: Path) -> None:
    wheel = read_wheel(next(dist.glob("itk_numerics*.whl")))
    assert wheel.name == "itk-numerics"
    assert wheel.requires == {"itk-core"}
    assert wheel.modules == {"ITKDisplacementField": ("ITKCommon",)}


def test_a_missing_requirement_is_reported_with_the_module_edge(dist: Path) -> None:
    make_wheel(
        dist,
        "itk-io",
        ["itk-core==6.0"],
        {"ITKIOTransformBase": ("ITKDisplacementField", "ITKCommon")},
    )
    with pytest.raises(
        RuntimeError,
        match="itk-io must require itk-numerics: ITKIOTransformBase -> ITKDisplacementField",
    ):
        check([dist])
    assert main([str(dist)]) == 1


def test_a_requirement_reached_through_another_wheel_passes(dist: Path) -> None:
    make_wheel(
        dist,
        "itk-filtering",
        ["itk-numerics==6.0"],
        {"ITKSmoothing": ("ITKCommon", "ITKDisplacementField")},
    )
    check([dist])
    assert main([str(dist)]) == 0


def test_a_module_in_two_wheels_or_in_none_is_reported(dist: Path) -> None:
    make_wheel(
        dist,
        "itk-io",
        ["itk-numerics==6.0"],
        {"ITKCommon": (), "ITKIOGDCM": ("ITKGDCM",)},
    )
    problems = audit([read_wheel(w) for w in sorted(dist.glob("*.whl"))])
    assert any("ITKCommon is in both" in p for p in problems)
    assert any(
        "ITKIOGDCM depends on ITKGDCM, which no wheel provides" in p for p in problems
    )


def test_wheels_outside_the_named_set_are_ignored(dist: Path) -> None:
    make_wheel(
        dist, "itk-mymodule", ["itk-core==6.0"], {"MyModule": ("ITKDisplacementField",)}
    )
    check([dist], ["itk-core", "itk-numerics"])
    with pytest.raises(RuntimeError, match="itk-mymodule must require itk-numerics"):
        check([dist])
