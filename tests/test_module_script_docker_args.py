"""What the Linux module script hands to the container runtime."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.bash import BASH

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

pytestmark = pytest.mark.skipif(not BASH, reason="needs bash")

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
    for name in ("CONTAINER_DNS", "LD_LIBRARY_PATH"):
        if name in os.environ:
            env[name] = os.environ[name]
    result = subprocess.run(
        [BASH, str(ipp / "scripts" / "dockcross-manylinux-build-module-wheels.sh")],
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


@pytest.mark.parametrize("arch", ["x64", "aarch64"])
def test_container_dns_replaces_host_networking(
    tmp_path: Path, arch: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CONTAINER_DNS", "10.0.0.1,10.0.0.2")
    args = " ".join(_run(tmp_path, arch, ""))
    assert "--dns 10.0.0.1" in args
    assert "--dns 10.0.0.2" in args
    assert "--network=host" not in args


@pytest.mark.parametrize("arch", ["x64", "aarch64"])
def test_host_networking_without_container_dns(tmp_path: Path, arch: str) -> None:
    args = " ".join(_run(tmp_path, arch, ""))
    assert "--network=host" in args
    assert "--dns" not in args


@pytest.mark.skipif(os.name == "nt", reason="a drive letter's colon splits the path")
@pytest.mark.parametrize("arch", ["x64", "aarch64"])
def test_ld_library_path_reaches_the_container(
    tmp_path: Path, arch: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    cuda = tmp_path / "cuda-lib64"
    cudnn = tmp_path / "cudnn-lib"
    cuda.mkdir()
    cudnn.mkdir()
    monkeypatch.setenv("LD_LIBRARY_PATH", f"{cuda}:{cudnn}:")
    args = " ".join(_run(tmp_path, arch, ""))
    passed = re.search(r"-e LD_LIBRARY_PATH=(\S+)", args)
    assert passed is not None
    assert passed[1] == "/usr/lib64/cuda-lib64:/usr/lib64/cudnn-lib"
