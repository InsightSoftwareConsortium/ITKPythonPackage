"""BuildManager resumes a run only when the build's inputs are unchanged."""

import functools
import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from build_manager import BuildManager

STEPS = ["01_superbuild", "02_build_itk", "03_build_wheels"]
INPUTS = {"itk_commit": "a" * 40, "package_version": "6.0b3", "fingerprint": "f1"}


def _finish_every_step(report: Path, inputs: Mapping[str, str] | None) -> None:
    manager = BuildManager(report, STEPS, inputs)
    for step in STEPS:
        manager.run_step(step, lambda: None)


def _steps_run(
    report: Path, inputs: Mapping[str, str] | None
) -> tuple[BuildManager, list[str]]:
    manager = BuildManager(report, STEPS, inputs)
    ran: list[str] = []
    for step in STEPS:
        manager.run_step(step, functools.partial(ran.append, step))
    return manager, ran


def test_identical_inputs_skip_the_steps_already_done(tmp_path):
    report = tmp_path / "build_log.json"
    _finish_every_step(report, INPUTS)
    manager, ran = _steps_run(report, dict(INPUTS))
    assert ran == []
    assert manager.changed_inputs == []


def test_identical_inputs_resume_after_the_failed_step(tmp_path):
    report = tmp_path / "build_log.json"
    manager = BuildManager(report, STEPS, INPUTS)
    manager.run_step(STEPS[0], lambda: None)
    with pytest.raises(RuntimeError):
        manager.run_step(STEPS[1], _fail)
    _, ran = _steps_run(report, INPUTS)
    assert ran == STEPS[1:]


def _fail():
    raise RuntimeError


@pytest.mark.parametrize("changed", sorted(INPUTS))
def test_a_changed_input_runs_every_step_again(tmp_path, changed):
    report = tmp_path / "build_log.json"
    _finish_every_step(report, INPUTS)
    manager, ran = _steps_run(report, {**INPUTS, changed: "something else"})
    assert ran == STEPS
    assert manager.changed_inputs == [changed]


def test_a_report_without_inputs_runs_every_step_again(tmp_path):
    """A report written before inputs were recorded cannot vouch for them."""
    report = tmp_path / "build_log.json"
    _finish_every_step(report, None)
    _, ran = _steps_run(report, INPUTS)
    assert ran == STEPS


def test_the_report_records_the_inputs_of_the_run(tmp_path):
    report = tmp_path / "build_log.json"
    _finish_every_step(report, INPUTS)
    _steps_run(report, {**INPUTS, "itk_commit": "b" * 40})
    assert json.loads(report.read_text())["inputs"]["itk_commit"] == "b" * 40


def test_a_corrupt_report_stops_the_build_and_names_the_file(tmp_path):
    report = tmp_path / "build_log.json"
    report.write_text("{not json")
    with pytest.raises(RuntimeError, match=r"build_log\.json"):
        BuildManager(report, STEPS, INPUTS)
