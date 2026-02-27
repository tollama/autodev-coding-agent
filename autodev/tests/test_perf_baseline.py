"""Tests for autodev.perf_baseline module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from autodev.perf_baseline import (
    DEFAULT_THRESHOLDS,
    SCHEMA_VERSION,
    RunMetricsSnapshot,
    _append_snapshot,
    _compute_baseline_averages,
    _compute_task_metrics,
    _read_baseline,
    _resolve_thresholds,
    _safe_int,
    collect_run_metrics,
    detect_regression,
    record_and_check,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trace_dict(
    total_elapsed_ms: int = 50000,
    phases: list | None = None,
    llm_metrics: dict | None = None,
) -> dict:
    """Build a realistic trace_dict (mimics RunTrace.to_dict())."""
    return {
        "run_id": "test-run",
        "request_id": "test-req",
        "profile": "balanced",
        "total_elapsed_ms": total_elapsed_ms,
        "event_count": 0,
        "events": [],
        "phases": phases
        or [
            {"phase": "planning", "start_ms": 0, "end_ms": 5000, "duration_ms": 5000, "status": "completed"},
            {"phase": "implementation", "start_ms": 5000, "end_ms": 40000, "duration_ms": 35000, "status": "completed"},
            {"phase": "final_validation", "start_ms": 40000, "end_ms": 50000, "duration_ms": 10000, "status": "completed"},
        ],
        "llm_metrics": llm_metrics
        or {
            "planner": {
                "call_count": 5,
                "total_prompt_tokens": 10000,
                "total_completion_tokens": 4000,
                "total_duration_ms": 3000,
                "retry_count": 0,
            },
            "implementer": {
                "call_count": 10,
                "total_prompt_tokens": 30000,
                "total_completion_tokens": 15000,
                "total_duration_ms": 8000,
                "retry_count": 1,
            },
        },
    }


def _make_quality_summary(
    tasks: list | None = None,
    totals: dict | None = None,
) -> dict:
    """Build a realistic quality_summary dict."""
    return {
        "tasks": tasks
        or [
            {
                "task_id": "T-001",
                "status": "passed",
                "attempts": 1,
                "hard_failures": 0,
                "soft_failures": 0,
                "attempt_trend": [{"attempt": 1, "status": "passed", "duration_ms": 2000}],
            },
            {
                "task_id": "T-002",
                "status": "passed",
                "attempts": 2,
                "hard_failures": 0,
                "soft_failures": 0,
                "attempt_trend": [
                    {"attempt": 1, "status": "failed", "duration_ms": 1500},
                    {"attempt": 2, "status": "passed", "duration_ms": 3000},
                ],
            },
            {
                "task_id": "T-003",
                "status": "failed",
                "attempts": 1,
                "hard_failures": 1,
                "soft_failures": 0,
                "attempt_trend": [{"attempt": 1, "status": "failed", "duration_ms": 1000}],
            },
        ],
        "totals": totals or {"total_task_attempts": 4, "repair_passes": 1},
    }


def _make_snapshot(
    run_id: str = "run-1",
    total_elapsed_ms: int = 50000,
    total_validation_ms: int = 6000,
    total_llm_tokens: int = 59000,
    max_task_ms: int = 3000,
) -> RunMetricsSnapshot:
    return RunMetricsSnapshot(
        run_id=run_id,
        timestamp="2026-01-01T00:00:00.000Z",
        profile="balanced",
        total_elapsed_ms=total_elapsed_ms,
        phase_durations_ms={"planning": 5000, "implementation": 35000},
        total_llm_prompt_tokens=40000,
        total_llm_completion_tokens=19000,
        total_llm_tokens=total_llm_tokens,
        total_llm_calls=15,
        total_llm_retries=1,
        total_validation_ms=total_validation_ms,
        max_task_ms=max_task_ms,
        p95_task_ms=2800,
        median_task_ms=2000,
        task_count=3,
        passed_tasks=2,
        failed_tasks=1,
        total_task_attempts=4,
        repair_passes=1,
    )


# ---------------------------------------------------------------------------
# Test 1: _safe_int
# ---------------------------------------------------------------------------


def test_safe_int_coercion():
    assert _safe_int(42) == 42
    assert _safe_int(3.7) == 3
    assert _safe_int("100") == 100
    assert _safe_int(None) == 0
    assert _safe_int("abc") == 0
    assert _safe_int([]) == 0


# ---------------------------------------------------------------------------
# Test 2-3: _compute_task_metrics
# ---------------------------------------------------------------------------


def test_compute_task_metrics_from_quality_summary():
    qs = _make_quality_summary()
    metrics = _compute_task_metrics(qs)
    # Tasks: T-001=2000ms, T-002=3000ms (last attempt), T-003=1000ms
    assert metrics["total_validation_ms"] == 6000
    assert metrics["max_task_ms"] == 3000
    assert metrics["task_count"] == 3
    assert metrics["passed_tasks"] == 2
    assert metrics["failed_tasks"] == 1
    # Sorted durations: [1000, 2000, 3000]. median=2000
    # p95 index = int((3-1)*0.95) = int(1.9) = 1 → sorted[1] = 2000
    assert metrics["median_task_ms"] == 2000
    assert metrics["p95_task_ms"] == 2000


def test_compute_task_metrics_empty():
    metrics = _compute_task_metrics({})
    assert metrics["total_validation_ms"] == 0
    assert metrics["max_task_ms"] == 0
    assert metrics["task_count"] == 0
    assert metrics["passed_tasks"] == 0
    assert metrics["failed_tasks"] == 0


# ---------------------------------------------------------------------------
# Test 4: collect_run_metrics
# ---------------------------------------------------------------------------


def test_collect_run_metrics_full():
    trace = _make_trace_dict()
    qs = _make_quality_summary()
    snapshot = collect_run_metrics("r-1", "balanced", trace, qs)

    assert snapshot.run_id == "r-1"
    assert snapshot.profile == "balanced"
    assert snapshot.total_elapsed_ms == 50000

    # Phase durations
    assert snapshot.phase_durations_ms["planning"] == 5000
    assert snapshot.phase_durations_ms["implementation"] == 35000

    # LLM: planner(10000+4000) + implementer(30000+15000)
    assert snapshot.total_llm_prompt_tokens == 40000
    assert snapshot.total_llm_completion_tokens == 19000
    assert snapshot.total_llm_tokens == 59000
    assert snapshot.total_llm_calls == 15
    assert snapshot.total_llm_retries == 1

    # Task validation
    assert snapshot.total_validation_ms == 6000
    assert snapshot.max_task_ms == 3000
    assert snapshot.task_count == 3
    assert snapshot.passed_tasks == 2
    assert snapshot.failed_tasks == 1

    # Fix loop
    assert snapshot.total_task_attempts == 4
    assert snapshot.repair_passes == 1

    # Timestamp should be ISO format
    assert snapshot.timestamp.endswith("Z") or "+" in snapshot.timestamp


# ---------------------------------------------------------------------------
# Test 5: RunMetricsSnapshot.to_dict roundtrip
# ---------------------------------------------------------------------------


def test_snapshot_to_dict_roundtrip():
    snapshot = _make_snapshot()
    d = snapshot.to_dict()

    # Should be JSON-serializable
    serialized = json.dumps(d)
    assert isinstance(serialized, str)

    # Key fields should be present
    assert d["run_id"] == "run-1"
    assert d["total_elapsed_ms"] == 50000
    assert d["total_llm_tokens"] == 59000
    assert d["phase_durations_ms"]["planning"] == 5000


# ---------------------------------------------------------------------------
# Test 6-8: _read_baseline edge cases
# ---------------------------------------------------------------------------


def test_read_baseline_missing_file():
    result = _read_baseline("/nonexistent/path/perf_baseline.json")
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["runs"] == []


def test_read_baseline_corrupted(tmp_path: Path):
    path = tmp_path / "perf_baseline.json"
    path.write_text("not valid json {{{{", encoding="utf-8")
    result = _read_baseline(str(path))
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["runs"] == []


def test_read_baseline_schema_mismatch(tmp_path: Path):
    path = tmp_path / "perf_baseline.json"
    path.write_text(json.dumps({"schema_version": 999, "runs": [{"run_id": "old"}]}), encoding="utf-8")
    result = _read_baseline(str(path))
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["runs"] == []


# ---------------------------------------------------------------------------
# Test 9: _append_snapshot rolling window
# ---------------------------------------------------------------------------


def test_append_snapshot_rolling_window():
    baseline = {"schema_version": SCHEMA_VERSION, "runs": []}

    # Add 4 snapshots with window_size=3
    for i in range(4):
        s = _make_snapshot(run_id=f"run-{i}")
        baseline = _append_snapshot(baseline, s, window_size=3)

    # Should keep only last 3
    assert len(baseline["runs"]) == 3
    assert baseline["runs"][0]["run_id"] == "run-1"
    assert baseline["runs"][2]["run_id"] == "run-3"


# ---------------------------------------------------------------------------
# Test 10: _compute_baseline_averages
# ---------------------------------------------------------------------------


def test_compute_baseline_averages():
    runs = [
        {"total_elapsed_ms": 30000, "total_validation_ms": 4000, "total_llm_tokens": 50000, "max_task_ms": 2000},
        {"total_elapsed_ms": 40000, "total_validation_ms": 6000, "total_llm_tokens": 60000, "max_task_ms": 3000},
        {"total_elapsed_ms": 50000, "total_validation_ms": 8000, "total_llm_tokens": 70000, "max_task_ms": 4000},
    ]
    avgs = _compute_baseline_averages(runs)

    assert avgs["total_elapsed_ms"] == pytest.approx(40000.0)
    assert avgs["total_validation_ms"] == pytest.approx(6000.0)
    assert avgs["total_llm_tokens"] == pytest.approx(60000.0)
    assert avgs["max_task_ms"] == pytest.approx(3000.0)


# ---------------------------------------------------------------------------
# Test 11-12: _resolve_thresholds
# ---------------------------------------------------------------------------


def test_resolve_thresholds_defaults():
    result = _resolve_thresholds(None)
    assert result == DEFAULT_THRESHOLDS

    result2 = _resolve_thresholds({})
    assert result2 == DEFAULT_THRESHOLDS


def test_resolve_thresholds_override():
    profile = {
        "perf_baseline": {
            "thresholds": {
                "total_elapsed_ms": {"max_ratio": 0.30, "max_abs_ms": 20000},
            }
        }
    }
    result = _resolve_thresholds(profile)

    # Overridden
    assert result["total_elapsed_ms"]["max_ratio"] == 0.30
    assert result["total_elapsed_ms"]["max_abs_ms"] == 20000

    # Others remain default
    assert result["total_validation_ms"] == DEFAULT_THRESHOLDS["total_validation_ms"]
    assert result["total_llm_tokens"] == DEFAULT_THRESHOLDS["total_llm_tokens"]


# ---------------------------------------------------------------------------
# Test 13-14: detect_regression
# ---------------------------------------------------------------------------


def test_detect_regression_no_baseline():
    snapshot = _make_snapshot()
    baseline = {"schema_version": SCHEMA_VERSION, "runs": []}

    result = detect_regression(snapshot, baseline)
    assert result.has_baseline is False
    assert result.ok is True
    assert result.verdicts == []
    assert result.baseline_run_count == 0


def test_detect_regression_pass_and_fail():
    # Baseline: 3 runs averaging total_elapsed_ms=40000
    baseline_runs = [
        {"total_elapsed_ms": 35000, "total_validation_ms": 5000, "total_llm_tokens": 55000, "max_task_ms": 2500},
        {"total_elapsed_ms": 40000, "total_validation_ms": 6000, "total_llm_tokens": 60000, "max_task_ms": 3000},
        {"total_elapsed_ms": 45000, "total_validation_ms": 7000, "total_llm_tokens": 65000, "max_task_ms": 3500},
    ]
    baseline = {"schema_version": SCHEMA_VERSION, "runs": baseline_runs}

    # Case 1: 12.5% over avg — within 50% threshold → PASS
    snapshot_ok = _make_snapshot(total_elapsed_ms=45000, total_validation_ms=6500, total_llm_tokens=62000, max_task_ms=3200)
    result_ok = detect_regression(snapshot_ok, baseline)
    assert result_ok.has_baseline is True
    assert result_ok.ok is True
    assert result_ok.baseline_run_count == 3
    for v in result_ok.verdicts:
        assert v.ok is True

    # Case 2: 100% over avg (80000 vs 40000) → FAIL
    snapshot_bad = _make_snapshot(total_elapsed_ms=80000, total_validation_ms=6000, total_llm_tokens=60000, max_task_ms=3000)
    result_bad = detect_regression(snapshot_bad, baseline)
    assert result_bad.ok is False
    # total_elapsed_ms should fail
    elapsed_verdict = next(v for v in result_bad.verdicts if v.metric_name == "total_elapsed_ms")
    assert elapsed_verdict.ok is False
    assert elapsed_verdict.ratio_ok is False
    assert elapsed_verdict.ratio > 0.5


# ---------------------------------------------------------------------------
# Test 15: record_and_check end-to-end
# ---------------------------------------------------------------------------


def test_record_and_check_e2e(tmp_path: Path):
    ws_root = str(tmp_path)
    autodev_dir = tmp_path / ".autodev"
    autodev_dir.mkdir()

    trace = _make_trace_dict()
    qs = _make_quality_summary()

    # First run: no baseline
    result1 = record_and_check(ws_root, "run-1", "balanced", trace, qs)
    assert result1.has_baseline is False
    assert result1.ok is True

    # File should be written
    baseline_path = autodev_dir / "perf_baseline.json"
    assert baseline_path.exists()

    data1 = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert len(data1["runs"]) == 1
    assert data1["runs"][0]["run_id"] == "run-1"
    assert "last_check_result" in data1

    # Second run: has baseline from first run
    result2 = record_and_check(ws_root, "run-2", "balanced", trace, qs)
    assert result2.has_baseline is True
    assert result2.baseline_run_count == 1
    assert result2.ok is True

    data2 = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert len(data2["runs"]) == 2
    assert data2["runs"][1]["run_id"] == "run-2"


def test_record_and_check_disabled_profile(tmp_path: Path):
    """When perf_baseline.enabled is False, should skip and return no baseline."""
    ws_root = str(tmp_path)
    (tmp_path / ".autodev").mkdir()

    trace = _make_trace_dict()
    qs = _make_quality_summary()
    profile = {"perf_baseline": {"enabled": False}}

    result = record_and_check(ws_root, "run-1", "balanced", trace, qs, quality_profile=profile)
    assert result.has_baseline is False
    assert result.ok is True

    # No file should be written
    assert not (tmp_path / ".autodev" / "perf_baseline.json").exists()
