"""How the Windows module script splits -setup_options and -cmake_options."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "windows-download-cache-and-build-module-wheels.ps1"
)
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")

pytestmark = pytest.mark.skipif(not POWERSHELL, reason="needs PowerShell")


def _split(tmp_path: Path, text: str) -> list[str]:
    function = re.search(
        r"^function Split-Options.*?^}", SCRIPT.read_text(), re.MULTILINE | re.DOTALL
    )
    assert function is not None
    probe = tmp_path / "probe.ps1"
    probe.write_text(
        "Set-StrictMode -Version Latest\n"
        f"{function[0]}\n"
        "ConvertTo-Json -InputObject @(Split-Options $env:SPLIT_OPTIONS_TEXT) -Compress\n"
    )
    result = subprocess.run(
        [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-File", str(probe)],
        env={**os.environ, "SPLIT_OPTIONS_TEXT": text},
        capture_output=True,
        text=True,
        check=True,
    )
    tokens: list[str] = json.loads(result.stdout)
    return tokens


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('"-DA=1" "-DB=2"', ["-DA=1", "-DB=2"]),
        ("-DA=1 -DB=2", ["-DA=1", "-DB=2"]),
        ('"-DX=a b" -DZ=1', ["-DX=a b", "-DZ=1"]),
        (
            r'-DP="C:\Program Files\x" -DQ=C:\a\b',
            [r"-DP=C:\Program Files\x", r"-DQ=C:\a\b"],
        ),
        (r"'-DS=C:\s'", [r"-DS=C:\s"]),
        (
            r'--lib-paths "C:\CUDA\bin" --exclude-libs nvcuda.dll',
            ["--lib-paths", r"C:\CUDA\bin", "--exclude-libs", "nvcuda.dll"],
        ),
        ("   ", []),
    ],
)
def test_options_split_on_unquoted_spaces_only(
    tmp_path: Path, text: str, expected: list[str]
) -> None:
    assert _split(tmp_path, text) == expected
