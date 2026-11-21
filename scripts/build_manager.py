from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

#: A report without a version field is read as version 1.
REPORT_VERSION = 1


class BuildReportError(ValueError):
    """A build report field is missing or holds a value of the wrong kind."""


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


def _object(where: str, value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        msg = f"{where}: expected a JSON object, got {value!r}"
        raise BuildReportError(msg)
    return value


def _optional_text(where: str, data: Mapping[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        msg = f"{where}.{key}: expected a string or null, got {value!r}"
        raise BuildReportError(msg)
    return value


def _required_text(where: str, data: Mapping[str, object], key: str) -> str:
    value = _optional_text(where, data, key)
    if value is None:
        msg = f"{where}: missing {key!r}"
        raise BuildReportError(msg)
    return value


@dataclass
class StepRecord:
    """The recorded state of one build step."""

    status: StepStatus = StepStatus.PENDING
    started_at: str | None = None
    finished_at: str | None = None
    duration_sec: float | None = None
    error: str | None = None

    def to_json(self) -> dict[str, object]:
        data: dict[str, object] = {
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_sec": self.duration_sec,
        }
        if self.error is not None:
            data["error"] = self.error
        return data

    @classmethod
    def from_json(cls, name: str, value: object) -> StepRecord:
        where = f"steps.{name}"
        data = _object(where, value)
        status = _required_text(where, data, "status")
        try:
            step_status = StepStatus(status)
        except ValueError:
            allowed = ", ".join(s.value for s in StepStatus)
            msg = f"{where}.status: {status!r} is not one of {allowed}"
            raise BuildReportError(msg) from None
        duration = data.get("duration_sec")
        if duration is not None and (
            isinstance(duration, bool) or not isinstance(duration, int | float)
        ):
            msg = f"{where}.duration_sec: expected a number or null, got {duration!r}"
            raise BuildReportError(msg)
        return cls(
            status=step_status,
            started_at=_optional_text(where, data, "started_at"),
            finished_at=_optional_text(where, data, "finished_at"),
            duration_sec=None if duration is None else float(duration),
            error=_optional_text(where, data, "error"),
        )


@dataclass
class BuildReport:
    """The JSON build report: step states and timestamps."""

    created_at: str
    updated_at: str
    steps: dict[str, StepRecord] = field(default_factory=dict)
    version: int = REPORT_VERSION

    def to_json(self) -> dict[str, object]:
        return {
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "steps": {name: step.to_json() for name, step in self.steps.items()},
        }

    @classmethod
    def from_json(cls, value: object) -> BuildReport:
        """Read a report; one without a ``version`` field is version 1.

        Raises
        ------
        BuildReportError
            Naming the first field that is missing or has the wrong kind.
        """
        data = _object("report", value)
        version = data.get("version", 1)
        if isinstance(version, bool) or not isinstance(version, int):
            msg = f"report.version: expected an integer, got {version!r}"
            raise BuildReportError(msg)
        if version != REPORT_VERSION:
            msg = (
                f"report.version: {version} is not supported "
                f"(this build reads version {REPORT_VERSION})"
            )
            raise BuildReportError(msg)
        if "steps" not in data:
            msg = "report: missing 'steps'"
            raise BuildReportError(msg)
        steps = {
            name: StepRecord.from_json(name, step)
            for name, step in _object("report.steps", data["steps"]).items()
        }
        return cls(
            created_at=_required_text("report", data, "created_at"),
            updated_at=_required_text("report", data, "updated_at"),
            steps=steps,
            version=version,
        )


class BuildManager:
    """Manage a JSON build report for multistep runs.

    Persists status and timing for each named step to a JSON file.
    Steps already marked ``"done"`` are skipped on subsequent runs,
    enabling resumable builds.

    Parameters
    ----------
    report_path : Path
        Path to the JSON report file (created if absent).
    step_names : list[str]
        Ordered names of build steps to track.

    Attributes
    ----------
    report : BuildReport
        In-memory report, written to *report_path* by ``save``.
    """

    def __init__(self, report_path: Path, step_names: list[str]):
        self.report_path = Path(report_path)
        self._init_structure(step_names)
        self._load_if_exists()

    def run_step(
        self, step_name: str, func: Callable[[], object], force_rerun: bool = False
    ) -> None:
        """Execute a build step, recording timing and status.

        Parameters
        ----------
        step_name : str
            Key identifying the step in the report.
        func : callable
            Zero-argument callable that performs the step's work.
        force_rerun : bool, optional
            If True, re-execute even when the step is already ``"done"``.

        Raises
        ------
        Exception
            Re-raises any exception thrown by *func* after recording
            the failure in the report.
        """
        entry = self.report.steps.setdefault(step_name, StepRecord())
        if entry.status is StepStatus.DONE and not force_rerun:
            return

        entry.status = StepStatus.RUNNING
        entry.started_at = self._now()
        self.report.updated_at = entry.started_at
        self.save()

        start = time.perf_counter()
        try:
            func()
        except Exception as e:
            entry.error = f"{type(e).__name__}: {e}"
            self._finish(entry, StepStatus.FAILED, start)
            raise
        self._finish(entry, StepStatus.DONE, start)

    def _finish(self, entry: StepRecord, status: StepStatus, start: float) -> None:
        entry.status = status
        entry.finished_at = self._now()
        entry.duration_sec = round(time.perf_counter() - start, 3)
        self.report.updated_at = entry.finished_at
        self.save()

    def save(self) -> None:
        """Write the current report to disk atomically."""
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.report_path.with_suffix(self.report_path.suffix + ".tmp")
        with Path(tmp).open("w", encoding="utf-8") as f:
            json.dump(self.report.to_json(), f, indent=2, sort_keys=True)
        tmp.replace(self.report_path)

    # ---- Internal helpers ----
    def _init_structure(self, step_names: list[str]) -> None:
        now = self._now()
        self.report = BuildReport(
            created_at=now,
            updated_at=now,
            steps={name: StepRecord() for name in step_names},
        )

    def _load_if_exists(self) -> None:
        if not self.report_path.exists():
            return
        try:
            with Path(self.report_path).open(encoding="utf-8") as f:
                existing = BuildReport.from_json(json.load(f))
        except Exception as e:
            # Guessing the step states of a damaged report could skip real work.
            msg = (
                f"Failed to load build report {self.report_path}: {e}. "
                f"Fix or delete it to continue."
            )
            raise RuntimeError(msg) from e
        # Merge existing with current set of steps, preserving statuses
        for name in self.report.steps:
            if name in existing.steps:
                self.report.steps[name] = existing.steps[name]
        self.report.created_at = existing.created_at
        self.report.updated_at = existing.updated_at

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")
