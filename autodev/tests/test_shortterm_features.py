"""Tests for short-term autoresearch features: advisory gate, config validation, time budget, experiment log API."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

from autodev.config import _validate_run_autonomous_quality_gate_policy, _validate_run_section


# ---------------------------------------------------------------------------
# Feature 1: Composite gate config validation
# ---------------------------------------------------------------------------


class TestCompositeGateConfigValidation:
    """Tests for composite gate config validation in config.py."""

    def test_composite_section_accepted(self):
        policy: Dict[str, Any] = {
            "composite": {"min_composite_score": 70.0},
        }
        errors: List[str] = []
        _validate_run_autonomous_quality_gate_policy(policy, errors)
        assert not errors

    def test_composite_min_score_must_be_0_to_100(self):
        policy: Dict[str, Any] = {
            "composite": {"min_composite_score": 150.0},
        }
        errors: List[str] = []
        _validate_run_autonomous_quality_gate_policy(policy, errors)
        assert any("between 0 and 100" in e for e in errors)

    def test_composite_negative_score_rejected(self):
        policy: Dict[str, Any] = {
            "composite": {"min_composite_score": -5.0},
        }
        errors: List[str] = []
        _validate_run_autonomous_quality_gate_policy(policy, errors)
        assert any("between 0 and 100" in e for e in errors)

    def test_composite_unknown_key_rejected(self):
        policy: Dict[str, Any] = {
            "composite": {"min_composite_score": 70.0, "bogus": True},
        }
        errors: List[str] = []
        _validate_run_autonomous_quality_gate_policy(policy, errors)
        assert any("unknown key" in e for e in errors)

    def test_composite_section_not_required(self):
        policy: Dict[str, Any] = {
            "tests": {"min_pass_rate": 0.8},
        }
        errors: List[str] = []
        _validate_run_autonomous_quality_gate_policy(policy, errors)
        assert not errors


# ---------------------------------------------------------------------------
# Feature 1: Advisory gate dataclass & evaluation
# ---------------------------------------------------------------------------


class TestCompositeGateThresholds:
    """Tests for AutonomousCompositeGateThresholds and policy parsing."""

    def test_dataclass_defaults(self):
        from autodev.autonomous_mode import AutonomousCompositeGateThresholds
        t = AutonomousCompositeGateThresholds()
        assert t.min_composite_score is None

    def test_dataclass_with_value(self):
        from autodev.autonomous_mode import AutonomousCompositeGateThresholds
        t = AutonomousCompositeGateThresholds(min_composite_score=70.0)
        assert t.min_composite_score == 70.0

    def test_policy_accepts_composite(self):
        from autodev.autonomous_mode import (
            AutonomousCompositeGateThresholds,
            AutonomousQualityGatePolicy,
        )
        policy = AutonomousQualityGatePolicy(
            composite=AutonomousCompositeGateThresholds(min_composite_score=65.0),
        )
        assert policy.composite is not None
        assert policy.composite.min_composite_score == 65.0

    def test_policy_composite_defaults_none(self):
        from autodev.autonomous_mode import AutonomousQualityGatePolicy
        policy = AutonomousQualityGatePolicy()
        assert policy.composite is None


# ---------------------------------------------------------------------------
# Feature 3: Per-task time budget config validation
# ---------------------------------------------------------------------------


class TestTimeBudgetConfigValidation:
    """Tests for max_fix_time_per_task_sec config validation."""

    def test_valid_time_budget(self):
        run: Dict[str, Any] = {"max_fix_time_per_task_sec": 300}
        errors: List[str] = []
        _validate_run_section(run, errors)
        assert not errors
        assert run["max_fix_time_per_task_sec"] == 300

    def test_negative_time_budget_rejected(self):
        run: Dict[str, Any] = {"max_fix_time_per_task_sec": -10}
        errors: List[str] = []
        _validate_run_section(run, errors)
        assert any("positive integer" in e for e in errors)

    def test_zero_time_budget_rejected(self):
        run: Dict[str, Any] = {"max_fix_time_per_task_sec": 0}
        errors: List[str] = []
        _validate_run_section(run, errors)
        assert any("positive integer" in e for e in errors)

    def test_time_budget_not_required(self):
        run: Dict[str, Any] = {}
        errors: List[str] = []
        _validate_run_section(run, errors)
        assert not errors


# ---------------------------------------------------------------------------
# Feature 3: run_trace EventType
# ---------------------------------------------------------------------------


class TestTimeBudgetEventType:
    def test_event_type_exists(self):
        from autodev.run_trace import EventType
        assert EventType.TASK_TIME_BUDGET_EXCEEDED == "task.time_budget_exceeded"


# ---------------------------------------------------------------------------
# Feature 3: failure_analyzer category
# ---------------------------------------------------------------------------


class TestTimeBudgetFailureCategory:
    def test_failure_category_exists(self):
        from autodev.failure_analyzer import FailureCategory
        assert FailureCategory.TASK_TIME_BUDGET_EXCEEDED == "task_time_budget_exceeded"


# ---------------------------------------------------------------------------
# Feature 4: Experiment log API helper
# ---------------------------------------------------------------------------


class TestExperimentLogApi:
    """Tests for _read_experiment_log and _experiment_log_for_latest_or_run."""

    def _write_log(self, run_dir: Path, entries: list[dict]) -> None:
        log_dir = run_dir / ".autodev"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "experiment_log.jsonl"
        with open(log_path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    def test_read_empty_run(self, tmp_path):
        from autodev.gui_mvp_server import _read_experiment_log
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        result = _read_experiment_log(run_dir)
        assert result["entries"] == []
        assert result["summary"]["entry_count"] == 0

    def test_read_with_entries(self, tmp_path):
        from autodev.gui_mvp_server import _read_experiment_log
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        entries = [
            {"task_id": "t1", "iteration": 1, "attempt": 1, "composite_score": 80.0, "decision": {"decision": "accepted", "reason_code": "initial_attempt", "score_delta": 0.0, "hard_blockers": []}},
            {"task_id": "t1", "iteration": 1, "attempt": 2, "composite_score": 85.0, "decision": {"decision": "accepted", "reason_code": "score_improved", "score_delta": 5.0, "hard_blockers": []}},
        ]
        self._write_log(run_dir, entries)
        result = _read_experiment_log(run_dir)
        assert result["summary"]["entry_count"] == 2
        assert len(result["entries"]) == 2
        assert result["summary"]["tasks"]["t1"]["best_score"] == 85.0

    def test_filter_by_task_id(self, tmp_path):
        from autodev.gui_mvp_server import _read_experiment_log
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        entries = [
            {"task_id": "t1", "composite_score": 80.0, "decision": {"decision": "accepted"}},
            {"task_id": "t2", "composite_score": 70.0, "decision": {"decision": "reverted"}},
        ]
        self._write_log(run_dir, entries)
        result = _read_experiment_log(run_dir, task_id="t1")
        assert len(result["entries"]) == 1
        assert result["entries"][0]["task_id"] == "t1"

    def test_latest_or_run_finds_latest(self, tmp_path):
        from autodev.gui_mvp_server import _experiment_log_for_latest_or_run
        from http import HTTPStatus
        # Create two run dirs with different timestamps
        (tmp_path / "run_old").mkdir()
        run_new = tmp_path / "run_new"
        run_new.mkdir()
        self._write_log(run_new, [
            {"task_id": "t1", "composite_score": 90.0, "decision": {"decision": "accepted"}},
        ])
        # Touch run_new to make it latest
        os.utime(run_new, None)
        result, status = _experiment_log_for_latest_or_run(tmp_path)
        assert status == HTTPStatus.OK
        assert result["summary"]["entry_count"] == 1

    def test_latest_or_run_specific_run(self, tmp_path):
        from autodev.gui_mvp_server import _experiment_log_for_latest_or_run
        from http import HTTPStatus
        run_dir = tmp_path / "run_abc"
        run_dir.mkdir()
        self._write_log(run_dir, [
            {"task_id": "t1", "composite_score": 75.0, "decision": {"decision": "neutral"}},
        ])
        result, status = _experiment_log_for_latest_or_run(tmp_path, run_id="run_abc")
        assert status == HTTPStatus.OK
        assert result["run_id"] == "run_abc"

    def test_latest_or_run_missing_run(self, tmp_path):
        from autodev.gui_mvp_server import _experiment_log_for_latest_or_run
        from http import HTTPStatus
        result, status = _experiment_log_for_latest_or_run(tmp_path, run_id="nonexistent")
        assert status == HTTPStatus.NOT_FOUND
