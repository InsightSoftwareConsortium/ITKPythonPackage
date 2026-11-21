import json
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any


class BuildManager:
    """Manage a JSON build report for multistep runs.

    Persists status and timing for each named step to a JSON file.
    Steps already marked ``"done"`` are skipped on subsequent runs,
    enabling resumable builds. When *inputs* are given and differ from
    the ones recorded in the report, every step starts again as pending.

    Parameters
    ----------
    report_path : Path
        Path to the JSON report file (created if absent).
    step_names : list[str]
        Ordered names of build steps to track.
    inputs : Mapping[str, str], optional
        What the build's outputs depend on, such as the ITK commit and the
        package version. Recorded in the report under ``inputs``.

    Attributes
    ----------
    report : dict
        In-memory report structure with ``created_at``, ``updated_at``,
        ``steps``, and (when *inputs* are given) ``inputs`` keys.
    changed_inputs : list[str]
        Names of the inputs that differ from the recorded report, or are
        missing from it; empty when the recorded steps were kept.
    """

    def __init__(
        self,
        report_path: Path,
        step_names: list[str],
        inputs: Mapping[str, str] | None = None,
    ):
        self.report_path = Path(report_path)
        self.inputs = dict(inputs) if inputs is not None else None
        self.changed_inputs: list[str] = []
        self._init_structure(step_names)
        self._load_if_exists()

    # ---- Public API ----
    def run_step(self, step_name: str, func, force_rerun=False) -> None:
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
        entry = self.report["steps"].setdefault(step_name, self._new_step_entry())
        if entry.get("status") == "done" and not force_rerun:
            # Already completed in a previous run; skip
            return

        # Mark start
        entry["status"] = "running"
        entry["started_at"] = self._now()
        self.report["updated_at"] = entry["started_at"]
        self.save()

        start = time.perf_counter()
        try:
            func()
        except Exception as e:
            # Record failure and re-raise
            entry["status"] = "failed"
            entry["finished_at"] = self._now()
            entry["duration_sec"] = round(time.perf_counter() - start, 3)
            entry["error"] = f"{type(e).__name__}: {e}"
            self.report["updated_at"] = entry["finished_at"]
            self.save()
            raise
        else:
            # Record success
            entry["status"] = "done"
            entry["finished_at"] = self._now()
            entry["duration_sec"] = round(time.perf_counter() - start, 3)
            self.report["updated_at"] = entry["finished_at"]
            self.save()

    def save(self) -> None:
        """Write the current report to disk atomically."""
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.report_path.with_suffix(self.report_path.suffix + ".tmp")
        with Path(tmp).open("w", encoding="utf-8") as f:
            json.dump(self.report, f, indent=2, sort_keys=True)
        tmp.replace(self.report_path)

    # ---- Internal helpers ----
    def _init_structure(self, step_names: list[str]) -> None:
        steps = {name: self._new_step_entry() for name in step_names}
        now = self._now()
        self.report: dict[str, Any] = {
            "created_at": now,
            "updated_at": now,
            "steps": steps,
        }
        if self.inputs is not None:
            self.report["inputs"] = dict(self.inputs)

    def _load_if_exists(self) -> None:
        if not self.report_path.exists():
            return
        try:
            with Path(self.report_path).open(encoding="utf-8") as f:
                existing = json.load(f)
            if self.inputs is not None:
                recorded = existing.get("inputs") or {}
                self.changed_inputs = sorted(
                    name
                    for name in self.inputs.keys() | recorded.keys()
                    if self.inputs.get(name) != recorded.get(name)
                )
                if self.changed_inputs:
                    return
            # Merge existing with current set of steps, preserving statuses
            existing_steps = existing.get("steps", {})
            for name in self.report["steps"]:
                if name in existing_steps:
                    self.report["steps"][name] = existing_steps[name]
            # Bring over timestamps
            self.report["created_at"] = existing.get(
                "created_at", self.report["created_at"]
            )
            self.report["updated_at"] = existing.get(
                "updated_at", self.report["updated_at"]
            )
        except Exception as e:
            # Guessing the step states of a damaged report could skip real work.
            msg = (
                f"Failed to load build report {self.report_path}: {e}. "
                f"Fix or delete it to continue."
            )
            raise RuntimeError(msg) from e

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _new_step_entry() -> dict[str, Any]:
        return {
            "status": "pending",
            "started_at": None,
            "finished_at": None,
            "duration_sec": None,
        }
