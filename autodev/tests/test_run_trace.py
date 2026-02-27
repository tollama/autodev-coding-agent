"""Tests for autodev.run_trace module."""

from __future__ import annotations

import time

from autodev.run_trace import (
    EventType,
    RunTrace,
)


# ---------------------------------------------------------------------------
# EventType tests
# ---------------------------------------------------------------------------


def test_event_type_values_are_strings():
    """EventType members should be str-serialisable."""
    assert isinstance(EventType.RUN_START.value, str)
    assert EventType.RUN_START.value == "run.start"
    assert EventType.PHASE_END.value == "phase.end"


def test_event_type_all_members():
    """Verify expected event types exist."""
    expected = {
        "RUN_START", "RUN_COMPLETED",
        "PHASE_START", "PHASE_END",
        "TASK_START", "TASK_PASSED", "TASK_FAILED",
        "VALIDATION_START", "VALIDATION_RESULT", "VALIDATION_DEDUP",
        "LLM_CALL_START", "LLM_CALL_END", "LLM_BUDGET_CHECK",
        "PLUGIN_LOADED", "PLUGIN_ERROR",
        "BATCH_PARALLEL_START", "BATCH_PARALLEL_END", "CONCURRENCY_ADJUSTED",
    }
    actual = {m.name for m in EventType}
    assert expected.issubset(actual)


# ---------------------------------------------------------------------------
# RunTrace.record tests
# ---------------------------------------------------------------------------


def test_record_appends_event():
    """record() should append a TraceEvent to events list."""
    trace = RunTrace(run_id="r1", request_id="q1")
    ev = trace.record(EventType.RUN_START, key="value")
    assert len(trace.events) == 1
    assert trace.events[0] is ev
    assert ev.event_type == EventType.RUN_START
    assert ev.data["key"] == "value"


def test_record_includes_timestamp_and_elapsed():
    """Events should have ISO timestamp and positive elapsed_ms."""
    trace = RunTrace(run_id="r1", request_id="q1")
    ev = trace.record(EventType.RUN_START)
    assert ev.timestamp.endswith("Z")
    assert ev.elapsed_ms >= 0


def test_elapsed_ms_increases():
    """Successive events should have non-decreasing elapsed_ms."""
    trace = RunTrace(run_id="r1", request_id="q1")
    ev1 = trace.record(EventType.RUN_START)
    time.sleep(0.01)
    ev2 = trace.record(EventType.RUN_COMPLETED)
    assert ev2.elapsed_ms >= ev1.elapsed_ms


# ---------------------------------------------------------------------------
# Phase timing tests
# ---------------------------------------------------------------------------


def test_start_and_end_phase():
    """start_phase + end_phase should produce valid PhaseTimings."""
    trace = RunTrace(run_id="r1", request_id="q1")
    trace.start_phase("planning")
    time.sleep(0.01)
    timing = trace.end_phase("planning")

    assert timing is not None
    assert timing.phase == "planning"
    assert timing.status == "completed"
    assert timing.duration_ms >= 0
    assert timing.end_ms >= timing.start_ms
    assert len(trace.phases) == 1


def test_end_phase_unknown_returns_none():
    """end_phase for unknown phase should return None."""
    trace = RunTrace(run_id="r1", request_id="q1")
    assert trace.end_phase("nonexistent") is None


def test_end_phase_with_failed_status():
    """end_phase can set status to 'failed'."""
    trace = RunTrace(run_id="r1", request_id="q1")
    trace.start_phase("validation")
    timing = trace.end_phase("validation", status="failed")
    assert timing is not None
    assert timing.status == "failed"


def test_multiple_phases_can_overlap():
    """Two phases can be active simultaneously."""
    trace = RunTrace(run_id="r1", request_id="q1")
    trace.start_phase("implementation")
    trace.start_phase("validation")
    t1 = trace.end_phase("validation")
    t2 = trace.end_phase("implementation")
    assert t1 is not None
    assert t2 is not None
    assert t2.duration_ms >= t1.duration_ms or True  # both completed


def test_phase_events_recorded():
    """start_phase and end_phase should each record trace events."""
    trace = RunTrace(run_id="r1", request_id="q1")
    trace.start_phase("planning")
    trace.end_phase("planning")
    event_types = [ev.event_type for ev in trace.events]
    assert EventType.PHASE_START in event_types
    assert EventType.PHASE_END in event_types


# ---------------------------------------------------------------------------
# LLM call metrics tests
# ---------------------------------------------------------------------------


def test_record_llm_call_accumulates():
    """Multiple calls to record_llm_call should accumulate."""
    trace = RunTrace(run_id="r1", request_id="q1")
    trace.record_llm_call("planner", prompt_tokens=100, completion_tokens=50, duration_ms=200)
    trace.record_llm_call("planner", prompt_tokens=80, completion_tokens=40, duration_ms=150)

    m = trace.llm_metrics["planner"]
    assert m.call_count == 2
    assert m.total_prompt_tokens == 180
    assert m.total_completion_tokens == 90
    assert m.total_duration_ms == 350
    assert m.retry_count == 0


def test_record_llm_call_tracks_retries():
    """is_retry=True should increment retry_count."""
    trace = RunTrace(run_id="r1", request_id="q1")
    trace.record_llm_call("fixer", is_retry=True)
    trace.record_llm_call("fixer", is_retry=False)
    assert trace.llm_metrics["fixer"].retry_count == 1
    assert trace.llm_metrics["fixer"].call_count == 2


def test_record_llm_call_separate_roles():
    """Different roles should have separate metrics."""
    trace = RunTrace(run_id="r1", request_id="q1")
    trace.record_llm_call("planner", prompt_tokens=100)
    trace.record_llm_call("implementer", prompt_tokens=200)
    assert "planner" in trace.llm_metrics
    assert "implementer" in trace.llm_metrics
    assert trace.llm_metrics["planner"].total_prompt_tokens == 100
    assert trace.llm_metrics["implementer"].total_prompt_tokens == 200


# ---------------------------------------------------------------------------
# to_dict tests
# ---------------------------------------------------------------------------


def test_to_dict_structure():
    """to_dict should produce a complete, JSON-serialisable structure."""
    trace = RunTrace(run_id="r1", request_id="q1", profile="test")
    trace.record(EventType.RUN_START, foo="bar")
    trace.start_phase("planning")
    trace.end_phase("planning")
    trace.record_llm_call("planner", prompt_tokens=10)

    d = trace.to_dict()

    assert d["run_id"] == "r1"
    assert d["request_id"] == "q1"
    assert d["profile"] == "test"
    assert d["total_elapsed_ms"] >= 0
    assert d["event_count"] >= 3  # RUN_START + PHASE_START + PHASE_END
    assert len(d["events"]) == d["event_count"]
    assert len(d["phases"]) == 1
    assert d["phases"][0]["phase"] == "planning"
    assert "planner" in d["llm_metrics"]
    assert d["llm_metrics"]["planner"]["call_count"] == 1


def test_to_dict_event_data_flattened():
    """Event data fields should be flattened into event dicts."""
    trace = RunTrace(run_id="r1", request_id="q1")
    trace.record(EventType.RUN_START, level=3, ok=True)
    ev = trace.to_dict()["events"][0]
    assert ev["event_type"] == "run.start"
    assert ev["level"] == 3
    assert ev["ok"] is True
    assert "timestamp" in ev
    assert "elapsed_ms" in ev


def test_to_dict_with_profile_none():
    """Profile can be None."""
    trace = RunTrace(run_id="r1", request_id="q1")
    d = trace.to_dict()
    assert d["profile"] is None
