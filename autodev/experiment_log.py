"""Structured experiment log inspired by autoresearch's TSV results pattern.

Appends one row per fix-loop iteration, enabling at-a-glance comparison of
attempt quality and explicit decision records (accepted/reverted/neutral).

Persisted to ``.autodev/experiment_log.jsonl`` (append-only, one JSON object
per line) for easy post-hoc analysis and debugging.

Design principles (from user review):
- Each row includes a decision record: accepted|reverted|neutral
- Includes reason_code, score_delta, and hard_blockers[]
- Read-only in Phase 1 (no control effect on pipeline flow).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .quality_score import QualityScore


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPERIMENT_LOG_FILE = ".autodev/experiment_log.jsonl"


# ---------------------------------------------------------------------------
# Decision record
# ---------------------------------------------------------------------------

@dataclass
class DecisionRecord:
    """Per-iteration decision record for debugging and policy tuning."""

    decision: str  # "accepted" | "reverted" | "neutral"
    reason_code: str  # e.g. "score_improved", "hard_blocked", "regression", "within_tolerance"
    score_delta: float  # composite score change vs previous iteration
    hard_blockers: List[str]  # active hard blockers at decision time

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision,
            "reason_code": self.reason_code,
            "score_delta": round(self.score_delta, 2),
            "hard_blockers": self.hard_blockers,
        }


# ---------------------------------------------------------------------------
# Experiment log entry
# ---------------------------------------------------------------------------

@dataclass
class ExperimentEntry:
    """Single row in the experiment log."""

    task_id: str
    iteration: int
    attempt: int
    quality_score: QualityScore
    decision: DecisionRecord
    timestamp: str = ""
    validators_passed: List[str] = field(default_factory=list)
    validators_failed: List[str] = field(default_factory=list)
    fix_strategy: str = ""  # e.g. "tests-focused", "security-focused"
    wall_clock_ms: int = 0

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "iteration": self.iteration,
            "attempt": self.attempt,
            "timestamp": self.timestamp,
            "composite_score": round(self.quality_score.composite, 2),
            "hard_blocked": self.quality_score.hard_blocked,
            "decision": self.decision.to_dict(),
            "components": {
                "tests": round(self.quality_score.tests_score, 2),
                "lint": round(self.quality_score.lint_score, 2),
                "type_health": round(self.quality_score.type_health_score, 2),
                "security": round(self.quality_score.security_score, 2),
                "simplicity": round(self.quality_score.simplicity_score, 2),
            },
            "validators_passed": self.validators_passed,
            "validators_failed": self.validators_failed,
            "fix_strategy": self.fix_strategy,
            "wall_clock_ms": self.wall_clock_ms,
        }


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------

def make_decision(
    current: QualityScore,
    previous: Optional[QualityScore],
    *,
    tolerance: float = 1.0,
) -> DecisionRecord:
    """Determine accept/revert/neutral decision for a fix-loop iteration.

    Parameters
    ----------
    current:
        Quality score after this iteration's changes.
    previous:
        Quality score from the previous iteration (None for first attempt).
    tolerance:
        Score delta threshold. Regression must exceed this to trigger revert.
        |delta| <= tolerance => neutral.

    Returns
    -------
    DecisionRecord with decision and reason_code.
    """
    # Hard blocked => always revert
    if current.hard_blocked:
        delta = (current.composite - previous.composite) if previous else 0.0
        return DecisionRecord(
            decision="reverted",
            reason_code="hard_blocked",
            score_delta=delta,
            hard_blockers=current.hard_blockers,
        )

    # First attempt (no previous) => accept
    if previous is None:
        return DecisionRecord(
            decision="accepted",
            reason_code="initial_attempt",
            score_delta=0.0,
            hard_blockers=[],
        )

    delta = current.composite - previous.composite

    if delta > tolerance:
        return DecisionRecord(
            decision="accepted",
            reason_code="score_improved",
            score_delta=delta,
            hard_blockers=[],
        )
    elif delta < -tolerance:
        return DecisionRecord(
            decision="reverted",
            reason_code="regression",
            score_delta=delta,
            hard_blockers=[],
        )
    else:
        # Within tolerance band => neutral (accept but flag as marginal)
        return DecisionRecord(
            decision="neutral",
            reason_code="within_tolerance",
            score_delta=delta,
            hard_blockers=[],
        )


# ---------------------------------------------------------------------------
# Log writer
# ---------------------------------------------------------------------------

class ExperimentLog:
    """Append-only experiment log writer.

    Writes to ``.autodev/experiment_log.jsonl`` under the workspace root.
    """

    def __init__(self, workspace_root: str) -> None:
        self._root = workspace_root
        self._path = os.path.join(workspace_root, EXPERIMENT_LOG_FILE)
        self._entries: List[ExperimentEntry] = []

    @property
    def entries(self) -> List[ExperimentEntry]:
        return list(self._entries)

    def append(self, entry: ExperimentEntry) -> None:
        """Append an entry to the in-memory log and flush to disk."""
        self._entries.append(entry)
        self._flush_entry(entry)

    def _flush_entry(self, entry: ExperimentEntry) -> None:
        """Append a single JSONL line to the log file (compact, one JSON object per line)."""
        log_dir = os.path.dirname(self._path)
        os.makedirs(log_dir, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")

    def last_score_for_task(self, task_id: str) -> Optional[QualityScore]:
        """Return the most recent quality score for a given task, or None."""
        for entry in reversed(self._entries):
            if entry.task_id == task_id:
                return entry.quality_score
        return None

    def summary(self) -> Dict[str, Any]:
        """Generate a summary of the experiment log for reporting."""
        if not self._entries:
            return {"entry_count": 0, "tasks": {}}

        tasks: Dict[str, Dict[str, Any]] = {}
        for entry in self._entries:
            tid = entry.task_id
            if tid not in tasks:
                tasks[tid] = {
                    "attempts": 0,
                    "decisions": {"accepted": 0, "reverted": 0, "neutral": 0},
                    "best_score": 0.0,
                    "final_score": 0.0,
                }
            t = tasks[tid]
            t["attempts"] += 1
            t["decisions"][entry.decision.decision] += 1
            t["best_score"] = max(t["best_score"], entry.quality_score.composite)
            t["final_score"] = entry.quality_score.composite

        return {
            "entry_count": len(self._entries),
            "tasks": tasks,
        }
