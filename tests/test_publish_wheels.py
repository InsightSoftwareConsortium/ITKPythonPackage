import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parent.parent / "Utilities" / "scripts" / "publish_wheels.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("publish_wheels", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


publish_wheels = _load()
WHEELS = [Path("dist/itk_core-6.0-cp311-abi3-win_amd64.whl")]


def _args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "test": False,
        "repository": None,
        "repository_url": None,
        "skip_existing": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_repository_names_a_pypirc_section() -> None:
    cmd = publish_wheels.upload_command(_args(repository="testpypi"), WHEELS)
    assert cmd == ["twine", "upload", "--repository", "testpypi", str(WHEELS[0])]
    assert "testpypi" in publish_wheels.upload_target(_args(repository="testpypi"))


def test_test_uploads_to_the_testpypi_url() -> None:
    cmd = publish_wheels.upload_command(_args(test=True, skip_existing=True), WHEELS)
    assert cmd == [
        "twine",
        "upload",
        "--repository-url",
        publish_wheels.TESTPYPI_URL,
        "--skip-existing",
        str(WHEELS[0]),
    ]


def test_no_destination_uploads_to_pypi() -> None:
    assert publish_wheels.upload_command(_args(), WHEELS) == [
        "twine",
        "upload",
        str(WHEELS[0]),
    ]
    assert publish_wheels.upload_target(_args()) == "PyPI"


@pytest.mark.parametrize(
    "flags",
    [
        ["--test", "--repository", "testpypi"],
        ["--repository", "testpypi", "--repository-url", "https://example.org/"],
        ["--test", "--repository-url", "https://example.org/"],
    ],
)
def test_destinations_are_mutually_exclusive(
    flags: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        publish_wheels.main(["--dist-directory", str(sys.prefix), *flags])
    assert "not allowed with argument" in capsys.readouterr().err
