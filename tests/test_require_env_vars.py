import shutil
import subprocess
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parent.parent / "scripts" / "require_env_vars.sh"


def _run(env: dict[str, str], *names: str) -> subprocess.CompletedProcess[str]:
    script = f'source "{HELPER}"; require_env_vars {" ".join(names)}; echo reached'
    return subprocess.run(
        ["bash", "-c", script],
        env={"PATH": "/usr/bin:/bin", **env},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_every_missing_variable_is_reported_before_exiting() -> None:
    result = _run({"SET": "1", "EMPTY": ""}, "SET", "EMPTY", "UNSET")
    assert result.returncode == 1
    assert "reached" not in result.stdout
    assert result.stdout.splitlines() == [
        "ERROR: Required environment variable 'EMPTY' is not set or empty.",
        "ERROR: Required environment variable 'UNSET' is not set or empty.",
    ]


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_set_variables_pass() -> None:
    result = _run({"A": "1", "B": "2"}, "A", "B")
    assert result.returncode == 0
    assert result.stdout.strip() == "reached"
