"""CMAKE_OPTIONS reaches the module build container as one intact value."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")

# Records each argument on its own line. Asked for the dockcross runner
# (``run --rm <image>``), it prints a runner that records its arguments too.
FAKE_DOCKER = """#!/bin/bash
if [ "$#" -eq 3 ] && [ "$1" = run ]; then
  printf '#!/bin/bash\\nprintf "%%s\\\\n" "$@" >>"%s"\\n' "$RECORD"
  exit 0
fi
printf '%s\\n' "$@" >>"$RECORD"
"""


def _run(tmp_path: Path, arch: str, cmake_options: str) -> list[str]:
    ipp = tmp_path / "ITKPythonPackage"
    shutil.copytree(SCRIPTS, ipp / "scripts")
    module = tmp_path / "ITKModule"
    module.mkdir()
    docker = tmp_path / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    record = tmp_path / "record.txt"
    env = {
        "PATH": os.environ["PATH"],
        "OCI_EXE": str(docker),
        "RECORD": str(record),
        "NO_SUDO": "1",
        "TARGET_ARCH": arch,
        "ITK_PACKAGE_VERSION": "v6.0b03",
        "MODULE_SRC_DIRECTORY": str(module),
        "MODULE_DEPS_DIR": str(tmp_path / "deps"),
        "CMAKE_OPTIONS": cmake_options,
    }
    result = subprocess.run(
        ["bash", str(ipp / "scripts" / "dockcross-manylinux-build-module-wheels.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return record.read_text().splitlines()


@pytest.mark.parametrize("arch", ["x64", "aarch64"])
@pytest.mark.parametrize(
    "cmake_options", ["", "-DBUILD_TESTING:BOOL=OFF -DRTK_USE_CUDA:BOOL=OFF"]
)
def test_cmake_options_arrive_unquoted_and_unsplit(
    tmp_path: Path, arch: str, cmake_options: str
) -> None:
    args = _run(tmp_path, arch, cmake_options)
    assert f"CMAKE_OPTIONS={cmake_options}" in args
    assert not any("CMAKE_OPTIONS='" in a for a in args)
