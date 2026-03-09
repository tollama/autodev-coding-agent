"""Tests for autodev.experiment_log — experiment tracking and decision records."""

from __future__ import annotations

import json
import os

import pytest

from autodev.experiment_log import (
    DecisionRecord,
    ExperimentEntry,
    ExperimentLog,
    make_decision,
)
from autodev.quality_score import QualityScore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_qs(composite: float, hard_blocked: bool = False, **kwargs) -> QualityScore:
    """Quick quality score factory."""
    return QualityScore(
        composite=composite,
        hard_blocked=hard_blocked,
        hard_blockers=kwargs.pop("hard_blockers", []),
        tests_score=kwargs.pop("tests_score", composite),
        lint_score=kwargs.pop("lint_score", composite),
        type_health_score=kwargs.pop("type_health_score", composite),
        security_score=kwargs.pop("security_score", composite),
        simplicity_score=kwargs.pop("simplicity_score", 100.0),
    )


# ---------------------------------------------------------------------------
# make_decision tests
# ---------------------------------------------------------------------------


class TestMakeDecision:
    def test_initial_attempt_accepted(self):
        qs = _make_qs(80.0)
        d = make_decision(qs, None)
        assert d.decision == "accepted"
        assert d.reason_code == "initial_attempt"
        assert d.score_delta == 0.0

    def test_improvement_accepted(self):
        prev = _make_qs(70.0)
        curr = _make_qs(85.0)
        d = make_decision(curr, prev)
        assert d.decision == "accepted"
        assert d.reason_code == "score_improved"
        assert d.score_delta == pytest.approx(15.0)

    def test_regression_reverted(self):
        prev = _make_qs(85.0)
        curr = _make_qs(70.0)
        d = make_decision(curr, prev)
        assert d.decision == "reverted"
        assert d.reason_code == "regression"
        assert d.score_delta == pytest.approx(-15.0)

    def test_within_tolerance_neutral(self):
        prev = _make_qs(80.0)
        curr = _make_qs(79.5)
        d = make_decision(curr, prev, tolerance=1.0)
        assert d.decision == "neutral"
        assert d.reason_code == "within_tolerance"

    def test_hard_blocked_always_reverted(self):
        prev = _make_qs(80.0)
        curr = _make_qs(90.0, hard_blocked=True, hard_blockers=["pytest: hard failure"])
        d = make_decision(curr, prev)
        assert d.decision == "reverted"
        assert d.reason_code == "hard_blocked"
        assert len(d.hard_blockers) == 1

    def test_custom_tolerance(self):
        prev = _make_qs(80.0)
        curr = _make_qs(77.0)  # delta = -3
        # With default tolerance (1.0), this is a regression
        d1 = make_decision(curr, prev, tolerance=1.0)
        assert d1.decision == "reverted"
        # With higher tolerance (5.0), this is neutral
        d2 = make_decision(curr, prev, tolerance=5.0)
        assert d2.decision == "neutral"

    def test_decision_to_dict(self):
        d = DecisionRecord(
            decision="accepted",
            reason_code="score_improved",
            score_delta=5.0,
            hard_blockers=[],
        )
        dd = d.to_dict()
        assert dd["decision"] == "accepted"
        assert dd["score_delta"] == 5.0
        assert dd["hard_blockers"] == []


# ---------------------------------------------------------------------------
# ExperimentEntry tests
# ---------------------------------------------------------------------------


class TestExperimentEntry:
    def test_to_dict(self):
        qs = _make_qs(85.0)
        d = DecisionRecord("accepted", "score_improved", 5.0, [])
        entry = ExperimentEntry(
            task_id="task_1",
            iteration=1,
            attempt=2,
            quality_score=qs,
            decision=d,
            validators_passed=["ruff", "pytest"],
            validators_failed=["mypy"],
            wall_clock_ms=1234,
        )
        dd = entry.to_dict()
        assert dd["task_id"] == "task_1"
        assert dd["attempt"] == 2
        assert dd["composite_score"] == 85.0
        assert "timestamp" in dd
        assert dd["validators_passed"] == ["ruff", "pytest"]
        assert dd["decision"]["decision"] == "accepted"

    def test_auto_timestamp(self):
        entry = ExperimentEntry(
            task_id="t",
            iteration=1,
            attempt=1,
            quality_score=_make_qs(50.0),
            decision=DecisionRecord("neutral", "initial_attempt", 0.0, []),
        )
        assert entry.timestamp.endswith("Z")


# ---------------------------------------------------------------------------
# ExperimentLog tests
# ---------------------------------------------------------------------------


class TestExperimentLog:
    def test_append_and_read(self, tmp_path):
        log = ExperimentLog(str(tmp_path))
        qs = _make_qs(80.0)
        entry = ExperimentEntry(
            task_id="t1",
            iteration=1,
            attempt=1,
            quality_score=qs,
            decision=DecisionRecord("accepted", "initial_attempt", 0.0, []),
        )
        log.append(entry)
        assert len(log.entries) == 1
        assert log.entries[0].task_id == "t1"

    def test_jsonl_file_written(self, tmp_path):
        log = ExperimentLog(str(tmp_path))
        qs = _make_qs(80.0)
        entry = ExperimentEntry(
            task_id="t1",
            iteration=1,
            attempt=1,
            quality_score=qs,
            decision=DecisionRecord("accepted", "initial_attempt", 0.0, []),
        )
        log.append(entry)

        log_path = os.path.join(str(tmp_path), ".autodev", "experiment_log.jsonl")
        assert os.path.exists(log_path)
        with open(log_path) as f:
            lines = f.readlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["task_id"] == "t1"

    def test_multiple_entries_appended(self, tmp_path):
        log = ExperimentLog(str(tmp_path))
        for i in range(3):
            log.append(ExperimentEntry(
                task_id="t1",
                iteration=1,
                attempt=i + 1,
                quality_score=_make_qs(70.0 + i * 5),
                decision=DecisionRecord("accepted", "score_improved", 5.0, []),
            ))

        log_path = os.path.join(str(tmp_path), ".autodev", "experiment_log.jsonl")
        with open(log_path) as f:
            lines = f.readlines()
        assert len(lines) == 3

    def test_last_score_for_task(self, tmp_path):
        log = ExperimentLog(str(tmp_path))
        log.append(ExperimentEntry(
            task_id="t1", iteration=1, attempt=1,
            quality_score=_make_qs(70.0),
            decision=DecisionRecord("accepted", "initial_attempt", 0.0, []),
        ))
        log.append(ExperimentEntry(
            task_id="t1", iteration=1, attempt=2,
            quality_score=_make_qs(85.0),
            decision=DecisionRecord("accepted", "score_improved", 15.0, []),
        ))
        log.append(ExperimentEntry(
            task_id="t2", iteration=1, attempt=1,
            quality_score=_make_qs(60.0),
            decision=DecisionRecord("accepted", "initial_attempt", 0.0, []),
        ))

        last_t1 = log.last_score_for_task("t1")
        assert last_t1 is not None
        assert last_t1.composite == pytest.approx(85.0)

        last_t2 = log.last_score_for_task("t2")
        assert last_t2 is not None
        assert last_t2.composite == pytest.approx(60.0)

        assert log.last_score_for_task("t3") is None

    def test_summary(self, tmp_path):
        log = ExperimentLog(str(tmp_path))
        log.append(ExperimentEntry(
            task_id="t1", iteration=1, attempt=1,
            quality_score=_make_qs(70.0),
            decision=DecisionRecord("accepted", "initial_attempt", 0.0, []),
        ))
        log.append(ExperimentEntry(
            task_id="t1", iteration=1, attempt=2,
            quality_score=_make_qs(60.0),
            decision=DecisionRecord("reverted", "regression", -10.0, []),
        ))
        log.append(ExperimentEntry(
            task_id="t1", iteration=1, attempt=3,
            quality_score=_make_qs(80.0),
            decision=DecisionRecord("accepted", "score_improved", 10.0, []),
        ))

        s = log.summary()
        assert s["entry_count"] == 3
        assert s["tasks"]["t1"]["attempts"] == 3
        assert s["tasks"]["t1"]["decisions"]["accepted"] == 2
        assert s["tasks"]["t1"]["decisions"]["reverted"] == 1
        assert s["tasks"]["t1"]["best_score"] == pytest.approx(80.0)

    def test_empty_summary(self, tmp_path):
        log = ExperimentLog(str(tmp_path))
        s = log.summary()
        assert s["entry_count"] == 0
        assert s["tasks"] == {}
