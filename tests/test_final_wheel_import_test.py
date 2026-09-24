from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _wire_final_import_test_config(linux_builder, tmp_path):
    linux_builder.package_env_config.update(
        {
            "PYTHON_EXECUTABLE": "python3",
            "IPP_SOURCE_DIR": Path(tmp_path),
        }
    )


@pytest.fixture(autouse=True)
def _no_itk_packages_installed():
    """Default `pip list` to empty so the uninstall step is a no-op.

    Without this, `_pip_uninstall_itk_wildcard` would run the real `pip
    list` on whatever interpreter the test happens to resolve, which is
    both slow and liable to enumerate unrelated real packages.
    """
    with patch(
        "build_python_instance_base.subprocess.run",
        return_value=CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
    ):
        yield


def test_final_wheel_import_test_raises_on_failed_install(tmp_path, linux_builder):
    """A failed pip install must fail the step, not just print a warning."""
    with patch.object(linux_builder, "echo_check_call", return_value=1):
        with pytest.raises(RuntimeError):
            linux_builder.final_wheel_import_test(tmp_path)


def test_final_wheel_import_test_raises_on_failed_import(tmp_path, linux_builder):
    """Install succeeds but a later import check fails: step must fail."""
    statuses = iter([0, 1])
    with patch.object(
        linux_builder, "echo_check_call", side_effect=lambda *a, **k: next(statuses)
    ):
        with pytest.raises(RuntimeError):
            linux_builder.final_wheel_import_test(tmp_path)


def test_final_wheel_import_test_passes_when_every_check_succeeds(
    tmp_path, linux_builder
):
    with patch.object(linux_builder, "echo_check_call", return_value=0) as called:
        linux_builder.final_wheel_import_test(tmp_path)
    assert called.call_count == 5


def test_final_wheel_import_test_uninstalls_before_installing(tmp_path, linux_builder):
    """The stale-install bug: uninstall must run BEFORE `pip install itk`.

    Checking only that both calls happened would still pass if the
    uninstall ran last, which would fix nothing.
    """
    with patch(
        "build_python_instance_base.subprocess.run",
        return_value=CompletedProcess(
            args=[], returncode=0, stdout="itk-core==6.0rc01\n", stderr=""
        ),
    ):
        with patch.object(linux_builder, "echo_check_call", return_value=0) as called:
            linux_builder.final_wheel_import_test(tmp_path)

    commands = [call.args[0] for call in called.call_args_list]
    uninstall_index = next(i for i, cmd in enumerate(commands) if "uninstall" in cmd)
    install_index = next(i for i, cmd in enumerate(commands) if "install" in cmd)
    assert uninstall_index < install_index


def test_final_wheel_import_test_raises_when_uninstall_fails(tmp_path, linux_builder):
    """A failed uninstall must fail the step, not silently proceed to install."""
    with patch(
        "build_python_instance_base.subprocess.run",
        return_value=CompletedProcess(
            args=[], returncode=0, stdout="itk-core==6.0rc01\n", stderr=""
        ),
    ):
        with patch.object(linux_builder, "echo_check_call", return_value=1) as called:
            with pytest.raises(RuntimeError):
                linux_builder.final_wheel_import_test(tmp_path)

    commands = [call.args[0] for call in called.call_args_list]
    assert len(commands) == 1
    assert "uninstall" in commands[0]
