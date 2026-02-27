"""Unit tests for :mod:`autodev.cli_progress`."""

from __future__ import annotations

import io
from typing import Any, Dict

from autodev.cli_progress import _format_bar, _phase_label, make_cli_progress_callback


# -- _format_bar --------------------------------------------------------------


def test_format_bar_zero():
    bar = _format_bar(0.0, width=10)
    assert "0.0%" in bar


def test_format_bar_fifty():
    bar = _format_bar(50.0, width=10)
    assert "50.0%" in bar
    # Should have 5 filled characters
    assert "\u2593" * 5 in bar


def test_format_bar_hundred():
    bar = _format_bar(100.0, width=10)
    assert "100.0%" in bar
    assert "\u2593" * 10 in bar


# -- _phase_label --------------------------------------------------------------


def test_phase_label_known():
    assert _phase_label("planning") == "Planning"
    assert _phase_label("implementation") == "Implementing"
    assert _phase_label("final_validation") == "Final Validation"


def test_phase_label_unknown():
    assert _phase_label("custom_phase") == "custom_phase"


def test_phase_label_none():
    assert _phase_label(None) == ""


# -- make_cli_progress_callback -----------------------------------------------


def _make_event(event_type: str, pct: float = 50.0, phase: str | None = None, **data: Any) -> Dict[str, Any]:
    """Build a minimal progress event dict.

    Note: ``phase`` goes to the top-level event field.  To include
    ``phase`` in the *data* dict (as the real ProgressEmitter does for
    ``phase.start`` / ``phase.end``), pass it explicitly in **data**.
    """
    return {"event": event_type, "progress_pct": pct, "phase": phase, "data": data}


def test_callback_run_start_prints():
    buf = io.StringIO()
    cb = make_cli_progress_callback(stream=buf, color=False)
    cb(_make_event("run.start", pct=0.0, run_id="r1"))
    output = buf.getvalue()
    assert "Pipeline Started" in output


def test_callback_run_end_passed():
    buf = io.StringIO()
    cb = make_cli_progress_callback(stream=buf, color=False)
    cb(_make_event("run.end", pct=100.0, ok=True))
    output = buf.getvalue()
    assert "PASSED" in output


def test_callback_run_end_failed():
    buf = io.StringIO()
    cb = make_cli_progress_callback(stream=buf, color=False)
    cb(_make_event("run.end", pct=100.0, ok=False))
    output = buf.getvalue()
    assert "FAILED" in output


def test_callback_phase_start():
    buf = io.StringIO()
    cb = make_cli_progress_callback(stream=buf, color=False)
    # The real ProgressEmitter puts phase in data via emit("phase.start", phase=name)
    evt = {"event": "phase.start", "progress_pct": 10.0, "phase": "planning", "data": {"phase": "planning"}}
    cb(evt)
    output = buf.getvalue()
    assert "Planning" in output


def test_callback_phase_end():
    buf = io.StringIO()
    cb = make_cli_progress_callback(stream=buf, color=False)
    evt = {"event": "phase.end", "progress_pct": 20.0, "phase": "planning", "data": {"phase": "planning"}}
    cb(evt)
    output = buf.getvalue()
    assert "Planning" in output
    assert "\u2713" in output


def test_callback_task_start():
    buf = io.StringIO()
    cb = make_cli_progress_callback(stream=buf, color=False)
    cb(_make_event("task.start", pct=40.0, task_id="t1", task_title="Build models"))
    output = buf.getvalue()
    assert "t1" in output
    assert "Build models" in output


def test_callback_task_end_ok():
    buf = io.StringIO()
    cb = make_cli_progress_callback(stream=buf, color=False)
    cb(_make_event("task.end", pct=50.0, task_id="t1", ok=True))
    output = buf.getvalue()
    assert "t1" in output
    assert "\u2713" in output


def test_callback_task_end_failed():
    buf = io.StringIO()
    cb = make_cli_progress_callback(stream=buf, color=False)
    cb(_make_event("task.end", pct=50.0, task_id="t1", ok=False))
    output = buf.getvalue()
    assert "t1" in output
    assert "\u2717" in output


def test_callback_repair_start():
    buf = io.StringIO()
    cb = make_cli_progress_callback(stream=buf, color=False)
    cb(_make_event("repair.start", pct=55.0, task_id="t1", attempt=2))
    output = buf.getvalue()
    assert "Repair" in output
    assert "t1" in output
    assert "2" in output


def test_callback_validation_start():
    buf = io.StringIO()
    cb = make_cli_progress_callback(stream=buf, color=False)
    cb(_make_event("validation.start", pct=60.0, task_id="t1"))
    output = buf.getvalue()
    assert "Validating" in output
    assert "t1" in output


def test_callback_validation_end():
    buf = io.StringIO()
    cb = make_cli_progress_callback(stream=buf, color=False)
    cb(_make_event("validation.end", pct=60.0, task_id="t1", ok=True))
    output = buf.getvalue()
    assert "Validation" in output
    assert "\u2713" in output


def test_callback_with_color():
    buf = io.StringIO()
    cb = make_cli_progress_callback(stream=buf, color=True)
    cb(_make_event("run.start", pct=0.0, run_id="r1"))
    output = buf.getvalue()
    # Should contain ANSI escape codes
    assert "\033[" in output


def test_callback_unknown_event_type_silent():
    """Unknown event types should not crash."""
    buf = io.StringIO()
    cb = make_cli_progress_callback(stream=buf, color=False)
    cb(_make_event("unknown.event", pct=50.0))
    # Should produce no output but not crash
    assert True
