"""Unit tests for :mod:`autodev.progress`."""

from __future__ import annotations

from typing import Any, Dict, List

from autodev.progress import PHASE_ORDER, PHASE_WEIGHTS, ProgressEmitter


# -- helpers ------------------------------------------------------------------


def _collect(emitter: ProgressEmitter) -> List[Dict[str, Any]]:
    """Return the collected events list wired to *emitter*."""
    # Access the list via the closure used in _make_emitter.
    raise NotImplementedError("use _make_emitter instead")


def _make_emitter(**kwargs: Any) -> tuple[ProgressEmitter, List[Dict[str, Any]]]:
    """Create a ProgressEmitter with a collecting callback."""
    events: List[Dict[str, Any]] = []
    emitter = ProgressEmitter(callback=events.append, **kwargs)
    return emitter, events


# -- null callback (no-op) ---------------------------------------------------


def test_null_callback_does_not_raise():
    """ProgressEmitter with no callback must be a silent no-op."""
    em = ProgressEmitter()
    em.run_start("r1")
    em.phase_start("planning")
    em.task_start("t1", "Task 1")
    em.task_end("t1", "Task 1", ok=True)
    em.phase_end("planning")
    em.run_end("r1", ok=True)


# -- emit basics --------------------------------------------------------------


def test_emit_produces_event_dict():
    em, events = _make_emitter()
    em.emit("custom.event", foo="bar")
    assert len(events) == 1
    evt = events[0]
    assert evt["event"] == "custom.event"
    assert "progress_pct" in evt
    assert evt["data"]["foo"] == "bar"


def test_emit_includes_current_phase():
    em, events = _make_emitter()
    em.phase_start("planning")
    em.emit("something")
    assert events[-1]["phase"] == "planning"


def test_emit_phase_none_outside_phase():
    em, events = _make_emitter()
    em.emit("something")
    assert events[-1]["phase"] is None


# -- run start / end ----------------------------------------------------------


def test_run_start_emits_event():
    em, events = _make_emitter()
    em.run_start("run-abc")
    assert events[-1]["event"] == "run.start"
    assert events[-1]["data"]["run_id"] == "run-abc"
    assert events[-1]["progress_pct"] == 0.0


def test_run_end_emits_100_percent():
    em, events = _make_emitter()
    em.run_end("run-abc", ok=True)
    assert events[-1]["event"] == "run.end"
    assert events[-1]["progress_pct"] == 100.0
    assert events[-1]["data"]["ok"] is True


def test_run_end_failed():
    em, events = _make_emitter()
    em.run_end("run-abc", ok=False)
    assert events[-1]["data"]["ok"] is False
    assert events[-1]["progress_pct"] == 100.0


# -- phase start / end --------------------------------------------------------


def test_phase_start_sets_current_phase():
    em, events = _make_emitter()
    em.phase_start("architecture")
    assert events[-1]["event"] == "phase.start"
    assert events[-1]["data"]["phase"] == "architecture"


def test_phase_end_clears_current_phase():
    em, events = _make_emitter()
    em.phase_start("planning")
    em.phase_end("planning")
    # After phase_end, current phase is cleared
    em.emit("probe")
    assert events[-1]["phase"] is None


def test_phase_end_adds_to_complete_set():
    em, events = _make_emitter()
    em.phase_start("prd_analysis")
    em.phase_end("prd_analysis")
    assert "prd_analysis" in em._phases_complete


# -- task start / end ----------------------------------------------------------


def test_task_start_emits():
    em, events = _make_emitter()
    em.task_start("t1", "First Task")
    assert events[-1]["event"] == "task.start"
    assert events[-1]["data"]["task_id"] == "t1"
    assert events[-1]["data"]["task_title"] == "First Task"


def test_task_end_ok_increments_completed():
    em, events = _make_emitter(total_tasks=3)
    assert em._completed_tasks == 0
    em.task_end("t1", "First Task", ok=True)
    assert em._completed_tasks == 1
    assert events[-1]["event"] == "task.end"
    assert events[-1]["data"]["ok"] is True


def test_task_end_failed_does_not_increment():
    em, events = _make_emitter(total_tasks=3)
    em.task_end("t1", "First Task", ok=False)
    assert em._completed_tasks == 0
    assert events[-1]["data"]["ok"] is False


# -- validation start / end ---------------------------------------------------


def test_validation_start_emits():
    em, events = _make_emitter()
    em.validation_start("t1", ["pytest", "ruff"])
    assert events[-1]["event"] == "validation.start"
    assert events[-1]["data"]["task_id"] == "t1"
    assert events[-1]["data"]["validators"] == ["pytest", "ruff"]


def test_validation_end_emits():
    em, events = _make_emitter()
    em.validation_end("t1", ok=True)
    assert events[-1]["event"] == "validation.end"
    assert events[-1]["data"]["ok"] is True


# -- repair -------------------------------------------------------------------


def test_repair_start_emits():
    em, events = _make_emitter()
    em.repair_start("t1", attempt=2)
    assert events[-1]["event"] == "repair.start"
    assert events[-1]["data"]["task_id"] == "t1"
    assert events[-1]["data"]["attempt"] == 2


# -- set_total_tasks ----------------------------------------------------------


def test_set_total_tasks_updates_count():
    em, _ = _make_emitter()
    em.set_total_tasks(5)
    assert em._total_tasks == 5


def test_set_total_tasks_negative_clamped():
    em, _ = _make_emitter()
    em.set_total_tasks(-3)
    assert em._total_tasks == 0


# -- progress_pct calculation -------------------------------------------------


def test_progress_starts_at_zero():
    em, events = _make_emitter()
    em.emit("probe")
    assert events[-1]["progress_pct"] == 0.0


def test_progress_after_completing_first_phase():
    em, events = _make_emitter()
    em.phase_start("prd_analysis")
    em.phase_end("prd_analysis")
    em.emit("probe")
    expected = PHASE_WEIGHTS["prd_analysis"] * 100.0
    assert events[-1]["progress_pct"] == round(expected, 1)


def test_progress_during_implementation_phase():
    em, events = _make_emitter(total_tasks=4)
    # Complete first three phases
    for phase in ["prd_analysis", "architecture", "planning"]:
        em.phase_start(phase)
        em.phase_end(phase)

    em.phase_start("implementation")
    em.set_total_tasks(4)

    # Complete 2 out of 4 tasks
    em._completed_tasks = 2
    em.emit("probe")

    pre_impl = sum(PHASE_WEIGHTS[p] for p in ["prd_analysis", "architecture", "planning"]) * 100.0
    impl_sub = PHASE_WEIGHTS["implementation"] * 100.0 * (2 / 4)
    expected = round(pre_impl + impl_sub, 1)
    assert events[-1]["progress_pct"] == expected


def test_progress_monotonically_increasing():
    em, events = _make_emitter(total_tasks=2)
    em.run_start("r1")
    em.phase_start("prd_analysis")
    em.phase_end("prd_analysis")
    em.phase_start("architecture")
    em.phase_end("architecture")
    em.phase_start("planning")
    em.phase_end("planning")
    em.phase_start("implementation")
    em.task_start("t1", "T1")
    em.task_end("t1", "T1", ok=True)
    em.task_start("t2", "T2")
    em.task_end("t2", "T2", ok=True)
    em.phase_end("implementation")
    em.phase_start("final_validation")
    em.phase_end("final_validation")
    em.run_end("r1", ok=True)

    pcts = [e["progress_pct"] for e in events]
    for i in range(1, len(pcts)):
        assert pcts[i] >= pcts[i - 1], f"progress_pct decreased at index {i}: {pcts[i-1]} -> {pcts[i]}"


def test_progress_all_phases_complete_equals_100():
    em, events = _make_emitter(total_tasks=1)
    for phase in PHASE_ORDER:
        em.phase_start(phase)
        if phase == "implementation":
            em._completed_tasks = 1
        em.phase_end(phase)
    em.emit("probe")
    assert events[-1]["progress_pct"] == 100.0


# -- phase weights ------------------------------------------------------------


def test_phase_weights_sum_to_one():
    total = sum(PHASE_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9, f"Phase weights sum to {total}, expected 1.0"


def test_phase_order_covers_all_weights():
    assert set(PHASE_ORDER) == set(PHASE_WEIGHTS.keys())


# -- error handling -----------------------------------------------------------


def test_callback_exception_does_not_propagate():
    """If the callback raises, the emitter must swallow it."""

    def _bad_callback(event: Dict[str, Any]) -> None:
        raise RuntimeError("boom")

    em = ProgressEmitter(callback=_bad_callback)
    # Should not raise
    em.run_start("r1")
    em.phase_start("planning")
    em.emit("test")


# -- in-progress non-implementation phase gives 50% credit -------------------


def test_non_implementation_phase_in_progress_gives_half_weight():
    em, events = _make_emitter()
    em.phase_start("prd_analysis")
    em.emit("probe")
    expected = PHASE_WEIGHTS["prd_analysis"] * 100.0 * 0.5
    assert events[-1]["progress_pct"] == round(expected, 1)
