"""The Linux cache script extracts a local archive, including a symlinked one."""

import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "dockcross-manylinux-download-cache.sh"
)
TARBALL = "ITKPythonBuilds-manylinux_2_28-x64.tar"

# Stands in for the clone that refreshes the build scripts.
FAKE_GIT = """#!/bin/bash
if [ "$1" = clone ]; then
  mkdir -p "$3/scripts"
  touch "$3/scripts/dockcross-manylinux-build-module-wheels.sh"
fi
"""

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None
    or shutil.which("zstd") is None
    or shutil.which("unzstd") is None
    or shutil.which("rsync") is None,
    reason="needs bash, zstd, and rsync",
)


@pytest.mark.parametrize("symlinked", [False, True])
def test_a_local_archive_is_extracted(tmp_path: Path, symlinked: bool) -> None:
    content = tmp_path / "content" / "ITKPythonPackage-build" / "marker.txt"
    content.parent.mkdir(parents=True)
    content.write_text("cache")
    tar_path = tmp_path / TARBALL
    with tarfile.open(tar_path, "w") as tar:
        tar.add(content.parent, arcname="ITKPythonPackage-build")
    archive = tmp_path / f"{TARBALL}.zst"
    subprocess.run(["zstd", "-q", str(tar_path), "-o", str(archive)], check=True)

    work = tmp_path / "work"
    work.mkdir()
    if symlinked:
        (work / archive.name).symlink_to(archive)
    else:
        shutil.copy(archive, work / archive.name)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "git").write_text(FAKE_GIT)
    (fake_bin / "git").chmod(0o755)
    env = {
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "ITK_GIT_TAG": "v6.0b03",
        "ITK_PACKAGE_VERSION": "v6.0b03",
        "ITKPYTHONPACKAGE_ORG": "InsightSoftwareConsortium",
        "ITKPYTHONPACKAGE_TAG": "main",
        "MANYLINUX_VERSION": "_2_28",
        "TARGET_ARCH": "x64",
    }
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (work / "ITKPythonPackage-build" / "marker.txt").read_text() == "cache"
