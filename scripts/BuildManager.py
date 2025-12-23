from __future__ import (
    annotations,
)  # Needed for python 3.9 to support python 3.10 style typehints

import json
import time
from datetime import datetime
from pathlib import Path


class BuildManager:
    """Manage a JSON build report for multi-step runs.

    - Persists status and timing for each named step.
    - Skips steps that are already marked as completed on subsequent runs.
    - Saves after each step and on demand.
    """

    def __init__(self, report_path: Path, step_names: list[str]):
        self.report_path = Path(report_path)
        self._init_structure(step_names)
        self._load_if_exists()

    # ---- Public API ----
    def run_step(self, step_name: str, func) -> None:
        entry = self.report["steps"].setdefault(step_name, self._new_step_entry())
        if entry.get("status") == "done":
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
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.report_path.with_suffix(self.report_path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.report, f, indent=2, sort_keys=True)
        tmp.replace(self.report_path)

    # ---- Internal helpers ----
    def _init_structure(self, step_names: list[str]) -> None:
        steps = {name: self._new_step_entry() for name in step_names}
        now = self._now()
        self.report = {
            "created_at": now,
            "updated_at": now,
            "steps": steps,
        }

    def _load_if_exists(self) -> None:
        if not self.report_path.exists():
            return
        try:
            with open(self.report_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            # Merge existing with current set of steps, preserving statuses
            existing_steps = existing.get("steps", {})
            for name in self.report["steps"].keys():
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
            # Corrupt or unreadable file; keep freshly initialized structure
            raise RuntimeError(f"Failed to load build report: {e}") from e

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _new_step_entry() -> dict:
        return {
            "status": "pending",
            "started_at": None,
            "finished_at": None,
            "duration_sec": None,
        }
