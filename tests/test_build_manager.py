"""BuildManager records each step and resumes a run after the failed step."""

import functools
import json
from pathlib import Path

import pytest
from build_manager import (
    REPORT_VERSION,
    BuildManager,
    BuildReport,
    BuildReportError,
    StepRecord,
    StepStatus,
)

STEPS = ["01_superbuild", "02_build_itk", "03_build_wheels"]


def _finish_every_step(report: Path) -> None:
    manager = BuildManager(report, STEPS)
    for step in STEPS:
        manager.run_step(step, lambda: None)


def _steps_run(report: Path) -> list[str]:
    manager = BuildManager(report, STEPS)
    ran: list[str] = []
    for step in STEPS:
        manager.run_step(step, functools.partial(ran.append, step))
    return ran


def test_a_finished_run_skips_the_steps_already_done(tmp_path: Path) -> None:
    report = tmp_path / "build_log.json"
    _finish_every_step(report)
    assert _steps_run(report) == []


def test_a_run_resumes_after_the_failed_step(tmp_path: Path) -> None:
    report = tmp_path / "build_log.json"
    manager = BuildManager(report, STEPS)
    manager.run_step(STEPS[0], lambda: None)
    with pytest.raises(RuntimeError):
        manager.run_step(STEPS[1], _fail)
    assert _steps_run(report) == STEPS[1:]


def _fail() -> None:
    raise RuntimeError


def test_a_corrupt_report_stops_the_build_and_names_the_file(tmp_path: Path) -> None:
    report = tmp_path / "build_log.json"
    report.write_text("{not json")
    with pytest.raises(RuntimeError, match=r"build_log\.json"):
        BuildManager(report, STEPS)


NO_VERSION = Path(__file__).parent / "data" / "build_log_without_version.json"
NO_VERSION_STEPS = [
    "01_superbuild_support_components",
    "02_build_wrapped_itk_cplusplus",
    "03_build_wheels",
]


def test_a_report_without_a_version_is_read_as_version_1() -> None:
    """A report with no version field loads as version 1 and saves with one."""
    original = json.loads(NO_VERSION.read_text())
    assert "version" not in original
    report = BuildReport.from_json(original)
    assert report.version == 1
    assert report.steps["03_build_wheels"] == StepRecord(
        status=StepStatus.FAILED,
        started_at="2026-11-21T15:31:46",
        finished_at="2026-11-21T15:31:46",
        duration_sec=0.0,
        error="RuntimeError: ninja failed",
    )
    assert report.to_json() == {**original, "version": REPORT_VERSION}


def test_a_build_tree_whose_report_has_no_version_is_reused(tmp_path: Path) -> None:
    report = tmp_path / "build_log.json"
    report.write_text(NO_VERSION.read_text())
    manager = BuildManager(report, NO_VERSION_STEPS)
    ran: list[str] = []
    for step in NO_VERSION_STEPS:
        manager.run_step(step, functools.partial(ran.append, step))
    assert ran == ["03_build_wheels"]
    saved = json.loads(report.read_text())
    assert saved["version"] == REPORT_VERSION
    assert saved["created_at"] == "2026-11-21T15:31:46"


def test_a_report_round_trips(tmp_path: Path) -> None:
    report = tmp_path / "build_log.json"
    _finish_every_step(report)
    loaded = BuildReport.from_json(json.loads(report.read_text()))
    assert BuildReport.from_json(loaded.to_json()) == loaded
    assert [s.status for s in loaded.steps.values()] == [StepStatus.DONE] * 3


def _valid() -> dict[str, object]:
    return {
        "created_at": "t0",
        "updated_at": "t1",
        "steps": {"01_superbuild": {"status": "pending"}},
    }


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"created_at": None}, r"report: missing 'created_at'"),
        ({"steps": None}, r"report: missing 'steps'"),
        ({"version": 2}, r"report\.version: 2 is not supported"),
        ({"version": "1"}, r"report\.version: expected an integer"),
        (
            {"steps": {"01_superbuild": {"status": "redo"}}},
            r"steps\.01_superbuild\.status: 'redo' is not one of",
        ),
        (
            {"steps": {"01_superbuild": {}}},
            r"steps\.01_superbuild: missing 'status'",
        ),
        (
            {"steps": {"01_superbuild": {"status": "done", "duration_sec": "1"}}},
            r"steps\.01_superbuild\.duration_sec: expected a number",
        ),
    ],
)
def test_an_invalid_report_names_the_field(
    change: dict[str, object], message: str
) -> None:
    data = _valid()
    for key, value in change.items():
        if value is None:
            del data[key]
        else:
            data[key] = value
    with pytest.raises(BuildReportError, match=message):
        BuildReport.from_json(data)


def test_an_invalid_report_stops_the_build_and_names_the_field(
    tmp_path: Path,
) -> None:
    report = tmp_path / "build_log.json"
    report.write_text("{}")
    with pytest.raises(RuntimeError, match=r"build_log\.json.*missing 'steps'"):
        BuildManager(report, STEPS)
