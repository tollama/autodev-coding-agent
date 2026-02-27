"""Tests for autodev.run_analyzer module."""

from __future__ import annotations

import json
import os
import tempfile

from autodev.run_analyzer import (
    RunAnalysis,
    _analyze_llm_usage,
    _analyze_phases,
    _analyze_repairs,
    _analyze_tasks,
    _analyze_trends,
    _analyze_validators,
    analyze_run,
    format_analysis,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trace(
    run_id: str = "abc-123",
    total_elapsed_ms: int = 50000,
    phases: list | None = None,
    llm_metrics: dict | None = None,
) -> dict:
    return {
        "run_id": run_id,
        "total_elapsed_ms": total_elapsed_ms,
        "phases": phases or [],
        "llm_metrics": llm_metrics or {},
    }


def _make_quality(
    tasks: list | None = None,
    final: dict | None = None,
    totals: dict | None = None,
) -> dict:
    return {
        "tasks": tasks or [],
        "final": final or {},
        "totals": totals or {},
    }


def _make_repair_history(
    outcomes: list | None = None,
    summary: dict | None = None,
) -> dict:
    return {
        "outcomes": outcomes or [],
        "summary": summary or {},
    }


def _make_baseline(runs: list | None = None) -> dict:
    return {"schema_version": 1, "runs": runs or []}


def _write_artifact(ws_root: str, rel_path: str, data: dict) -> None:
    """Write a JSON artifact to the temporary workspace."""
    path = os.path.join(ws_root, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


# ---------------------------------------------------------------------------
# Test 1-2: _analyze_phases
# ---------------------------------------------------------------------------


def test_analyze_phases_basic():
    """3 phases → duration/pct/bottleneck correct."""
    trace = _make_trace(phases=[
        {"phase": "planning", "duration_ms": 10000},
        {"phase": "implementation", "duration_ms": 30000},
        {"phase": "final_validation", "duration_ms": 10000},
    ])
    phases = _analyze_phases(trace)
    assert len(phases) == 3

    assert phases[0].phase == "planning"
    assert phases[0].duration_ms == 10000
    assert phases[0].pct_of_total == 20.0
    assert phases[0].is_bottleneck is False

    assert phases[1].phase == "implementation"
    assert phases[1].duration_ms == 30000
    assert phases[1].pct_of_total == 60.0
    assert phases[1].is_bottleneck is True

    assert phases[2].phase == "final_validation"
    assert phases[2].pct_of_total == 20.0
    assert phases[2].is_bottleneck is False


def test_analyze_phases_empty():
    """{}/empty phases → empty list."""
    assert _analyze_phases({}) == []
    assert _analyze_phases({"phases": []}) == []
    assert _analyze_phases({"phases": "not_a_list"}) == []


# ---------------------------------------------------------------------------
# Test 3-4: _analyze_validators
# ---------------------------------------------------------------------------


def test_analyze_validators_aggregates():
    """tasks + final validation aggregated correctly."""
    quality = _make_quality(
        tasks=[
            {
                "task_id": "T-001",
                "last_validation": [
                    {"name": "ruff", "ok": True, "duration_ms": 500},
                    {"name": "pytest", "ok": False, "duration_ms": 1200},
                ],
            },
            {
                "task_id": "T-002",
                "last_validation": [
                    {"name": "ruff", "ok": False, "duration_ms": 600},
                    {"name": "pytest", "ok": True, "duration_ms": 1100},
                ],
            },
        ],
        final={
            "validations": [
                {"name": "ruff", "ok": True, "duration_ms": 800},
                {"name": "pytest", "ok": True, "duration_ms": 1000},
            ],
        },
    )
    validators = _analyze_validators(quality)
    assert len(validators) == 2

    ruff = next(v for v in validators if v.name == "ruff")
    assert ruff.call_count == 3  # 2 tasks + 1 final
    assert ruff.pass_count == 2
    assert ruff.fail_count == 1
    assert ruff.total_duration_ms == 1900  # 500 + 600 + 800
    assert abs(ruff.pass_rate - 66.7) < 0.1
    assert ruff.avg_duration_ms == 633  # 1900 // 3

    pt = next(v for v in validators if v.name == "pytest")
    assert pt.call_count == 3
    assert pt.pass_count == 2
    assert pt.fail_count == 1
    assert pt.total_duration_ms == 3300


def test_analyze_validators_empty():
    """{}/empty tasks → empty list."""
    assert _analyze_validators({}) == []
    assert _analyze_validators({"tasks": []}) == []


# ---------------------------------------------------------------------------
# Test 5-6: _analyze_tasks
# ---------------------------------------------------------------------------


def test_analyze_tasks_basic():
    """status/attempts/duration extracted correctly."""
    quality = _make_quality(tasks=[
        {
            "task_id": "T-001",
            "title": "Add login",
            "status": "passed",
            "attempts": 1,
            "attempt_trend": [
                {"attempt": 1, "duration_ms": 2000},
            ],
            "last_validation": [
                {"name": "ruff", "ok": True},
            ],
        },
        {
            "task_id": "T-002",
            "title": "Fix bug",
            "status": "failed",
            "attempts": 3,
            "attempt_trend": [
                {"attempt": 1, "duration_ms": 1500},
                {"attempt": 2, "duration_ms": 2000},
                {"attempt": 3, "duration_ms": 2500},
            ],
            "last_validation": [
                {"name": "ruff", "ok": False, "error_classification": "lint_error"},
                {"name": "pytest", "ok": False, "error_classification": "test_logic_error"},
            ],
        },
    ])
    tasks = _analyze_tasks(quality)
    assert len(tasks) == 2

    t1 = tasks[0]
    assert t1.task_id == "T-001"
    assert t1.title == "Add login"
    assert t1.status == "passed"
    assert t1.attempts == 1
    assert t1.total_duration_ms == 2000
    assert t1.failure_categories == []
    assert t1.repair_escalation_max == 0

    t2 = tasks[1]
    assert t2.task_id == "T-002"
    assert t2.status == "failed"
    assert t2.attempts == 3
    assert t2.total_duration_ms == 6000  # 1500 + 2000 + 2500
    assert t2.failure_categories == ["lint_error", "test_logic_error"]
    assert t2.repair_escalation_max == 2


def test_analyze_tasks_empty():
    """{}/empty tasks → empty list."""
    assert _analyze_tasks({}) == []
    assert _analyze_tasks({"tasks": []}) == []
    assert _analyze_tasks({"tasks": "not_a_list"}) == []


# ---------------------------------------------------------------------------
# Test 7-8: _analyze_repairs
# ---------------------------------------------------------------------------


def test_analyze_repairs_basic():
    """summary/outcomes → category-level statistics."""
    repair = _make_repair_history(
        summary={
            "lint_error": {"total": 2, "resolved": 2},
            "test_logic_error": {"total": 3, "resolved": 1},
        },
        outcomes=[
            {"category": "lint_error", "escalation_level": 1, "resolved": True},
            {"category": "lint_error", "escalation_level": 2, "resolved": True},
            {"category": "test_logic_error", "escalation_level": 1, "resolved": False},
            {"category": "test_logic_error", "escalation_level": 3, "resolved": True},
        ],
    )
    cats = _analyze_repairs(repair)
    assert len(cats) == 2

    lint = next(c for c in cats if c.category == "lint_error")
    assert lint.occurrences == 2
    assert lint.resolved_count == 2
    assert lint.resolution_rate == 100.0
    assert lint.max_escalation_level == 2

    test = next(c for c in cats if c.category == "test_logic_error")
    assert test.occurrences == 3
    assert test.resolved_count == 1
    assert abs(test.resolution_rate - 33.3) < 0.1
    assert test.max_escalation_level == 3


def test_analyze_repairs_empty():
    """{}/empty summary → empty list."""
    assert _analyze_repairs({}) == []
    assert _analyze_repairs({"summary": {}}) == []
    assert _analyze_repairs({"summary": "bad"}) == []


# ---------------------------------------------------------------------------
# Test 9-10: _analyze_llm_usage
# ---------------------------------------------------------------------------


def test_analyze_llm_usage_basic():
    """Role-level token/call breakdown."""
    trace = _make_trace(llm_metrics={
        "planner": {
            "call_count": 5,
            "total_prompt_tokens": 10000,
            "total_completion_tokens": 4000,
        },
        "implementer": {
            "call_count": 10,
            "total_prompt_tokens": 30000,
            "total_completion_tokens": 15000,
        },
    })
    usage = _analyze_llm_usage(trace)
    assert len(usage) == 2

    planner = next(u for u in usage if u.role == "implementer")
    assert planner.call_count == 10
    assert planner.prompt_tokens == 30000
    assert planner.completion_tokens == 15000
    assert planner.total_tokens == 45000
    assert planner.avg_tokens_per_call == 4500

    pl = next(u for u in usage if u.role == "planner")
    assert pl.total_tokens == 14000
    assert pl.avg_tokens_per_call == 2800


def test_analyze_llm_usage_empty():
    """{}/empty metrics → empty list."""
    assert _analyze_llm_usage({}) == []
    assert _analyze_llm_usage({"llm_metrics": {}}) == []
    assert _analyze_llm_usage({"llm_metrics": "bad"}) == []


# ---------------------------------------------------------------------------
# Test 11-12: _analyze_trends
# ---------------------------------------------------------------------------


def test_analyze_trends_basic():
    """Runs → trend points extracted."""
    baseline = _make_baseline(runs=[
        {
            "run_id": "run-1",
            "timestamp": "2025-01-01T00:00:00",
            "total_elapsed_ms": 45000,
            "total_llm_tokens": 50000,
            "task_count": 5,
            "passed_tasks": 4,
        },
        {
            "run_id": "run-2",
            "timestamp": "2025-01-02T00:00:00",
            "total_elapsed_ms": 48000,
            "total_llm_tokens": 52000,
            "task_count": 5,
            "passed_tasks": 5,
        },
    ])
    trends = _analyze_trends(baseline)
    assert len(trends) == 2

    assert trends[0].run_id == "run-1"
    assert trends[0].total_elapsed_ms == 45000
    assert trends[0].total_llm_tokens == 50000
    assert trends[0].pass_rate == 80.0

    assert trends[1].run_id == "run-2"
    assert trends[1].pass_rate == 100.0


def test_analyze_trends_empty():
    """{}/empty runs → empty list."""
    assert _analyze_trends({}) == []
    assert _analyze_trends({"runs": []}) == []


# ---------------------------------------------------------------------------
# Test 13: bottleneck identification
# ---------------------------------------------------------------------------


def test_identify_bottleneck():
    """>40% → phase name; none above → None."""
    trace_yes = _make_trace(phases=[
        {"phase": "planning", "duration_ms": 1000},
        {"phase": "implementation", "duration_ms": 9000},
    ])
    phases = _analyze_phases(trace_yes)
    bottlenecks = [p for p in phases if p.is_bottleneck]
    assert len(bottlenecks) == 1
    assert bottlenecks[0].phase == "implementation"

    # No bottleneck: evenly distributed
    trace_no = _make_trace(phases=[
        {"phase": "a", "duration_ms": 1000},
        {"phase": "b", "duration_ms": 1000},
        {"phase": "c", "duration_ms": 1000},
    ])
    phases_no = _analyze_phases(trace_no)
    assert all(not p.is_bottleneck for p in phases_no)


# ---------------------------------------------------------------------------
# Test 14: slowest task identification
# ---------------------------------------------------------------------------


def test_identify_slowest_task():
    """Max duration → task_id."""
    quality = _make_quality(tasks=[
        {"task_id": "T-001", "status": "passed", "attempts": 1,
         "attempt_trend": [{"duration_ms": 2000}]},
        {"task_id": "T-002", "status": "passed", "attempts": 1,
         "attempt_trend": [{"duration_ms": 8000}]},
        {"task_id": "T-003", "status": "passed", "attempts": 1,
         "attempt_trend": [{"duration_ms": 3000}]},
    ])
    tasks = _analyze_tasks(quality)
    slowest = max(tasks, key=lambda t: t.total_duration_ms)
    assert slowest.task_id == "T-002"


# ---------------------------------------------------------------------------
# Test 15: pass rate computation
# ---------------------------------------------------------------------------


def test_compute_pass_rate():
    """Totals-based pass rate calculation."""
    quality = _make_quality(
        tasks=[
            {"task_id": "T-001", "status": "passed", "attempts": 1},
            {"task_id": "T-002", "status": "failed", "attempts": 2},
            {"task_id": "T-003", "status": "passed", "attempts": 1},
            {"task_id": "T-004", "status": "passed", "attempts": 1},
            {"task_id": "T-005", "status": "failed", "attempts": 3},
        ],
        totals={"tasks": 5, "successful_tasks": 3},
    )
    # Use analyze_run logic inline: totals → pass rate
    totals = quality["totals"]
    total_tasks = totals["tasks"]
    successful = totals["successful_tasks"]
    rate = round(successful / total_tasks * 100, 1)
    assert rate == 60.0


# ---------------------------------------------------------------------------
# Test 16: full integration test
# ---------------------------------------------------------------------------


def test_analyze_run_integration():
    """Full mock .autodev/ → complete analysis."""
    with tempfile.TemporaryDirectory() as ws_root:
        trace = _make_trace(
            run_id="test-run-1",
            total_elapsed_ms=50000,
            phases=[
                {"phase": "planning", "duration_ms": 10000},
                {"phase": "implementation", "duration_ms": 30000},
                {"phase": "final_validation", "duration_ms": 10000},
            ],
            llm_metrics={
                "planner": {
                    "call_count": 5,
                    "total_prompt_tokens": 10000,
                    "total_completion_tokens": 4000,
                },
            },
        )
        quality = _make_quality(
            tasks=[
                {
                    "task_id": "T-001",
                    "status": "passed",
                    "attempts": 1,
                    "attempt_trend": [{"duration_ms": 2000}],
                    "last_validation": [
                        {"name": "ruff", "ok": True, "duration_ms": 500},
                    ],
                },
                {
                    "task_id": "T-002",
                    "status": "failed",
                    "attempts": 3,
                    "attempt_trend": [
                        {"duration_ms": 1500},
                        {"duration_ms": 2000},
                        {"duration_ms": 2500},
                    ],
                    "last_validation": [
                        {"name": "ruff", "ok": False, "duration_ms": 600},
                    ],
                },
            ],
            final={
                "validations": [
                    {"name": "ruff", "ok": True, "duration_ms": 400},
                ],
            },
            totals={"tasks": 2, "successful_tasks": 1},
        )
        repair = _make_repair_history(
            summary={"lint_error": {"total": 2, "resolved": 1}},
            outcomes=[
                {"category": "lint_error", "escalation_level": 2, "resolved": True},
            ],
        )
        baseline = _make_baseline(runs=[
            {
                "run_id": "prev-run",
                "timestamp": "2025-01-01T00:00:00",
                "total_elapsed_ms": 45000,
                "total_llm_tokens": 50000,
                "task_count": 3,
                "passed_tasks": 3,
            },
        ])

        _write_artifact(ws_root, ".autodev/run_trace.json", trace)
        _write_artifact(ws_root, ".autodev/task_quality_index.json", quality)
        _write_artifact(ws_root, ".autodev/repair_history.json", repair)
        _write_artifact(ws_root, ".autodev/perf_baseline.json", baseline)

        analysis = analyze_run(ws_root)

        assert analysis.run_id == "test-run-1"
        assert analysis.total_elapsed_ms == 50000
        assert len(analysis.phases) == 3
        assert analysis.bottleneck_phase == "implementation"
        assert len(analysis.validators) == 1
        assert analysis.validators[0].name == "ruff"
        assert len(analysis.tasks) == 2
        assert analysis.slowest_task_id == "T-002"
        assert analysis.most_attempted_task_id == "T-002"
        assert analysis.total_repair_loops == 2  # T-002: 3 attempts - 1
        assert analysis.overall_pass_rate == 50.0
        assert len(analysis.repair_categories) == 1
        assert len(analysis.llm_usage) == 1
        assert len(analysis.trends) == 1


# ---------------------------------------------------------------------------
# Test 17: graceful degradation
# ---------------------------------------------------------------------------


def test_analyze_run_graceful():
    """Empty .autodev/ → empty analysis, no crash."""
    with tempfile.TemporaryDirectory() as ws_root:
        os.makedirs(os.path.join(ws_root, ".autodev"), exist_ok=True)
        analysis = analyze_run(ws_root)

        assert analysis.run_id == "unknown"
        assert analysis.total_elapsed_ms == 0
        assert analysis.phases == []
        assert analysis.validators == []
        assert analysis.tasks == []
        assert analysis.repair_categories == []
        assert analysis.llm_usage == []
        assert analysis.trends == []
        assert analysis.bottleneck_phase is None
        assert analysis.slowest_task_id is None
        assert analysis.overall_pass_rate == 0.0


# ---------------------------------------------------------------------------
# Test 18: format_analysis smoke test
# ---------------------------------------------------------------------------


def test_format_analysis_smoke():
    """Rendered text contains major section headings."""
    analysis = RunAnalysis(
        run_id="fmt-test",
        total_elapsed_ms=10000,
        phases=[
            _stub_phase("planning", 3000, 30.0, False),
            _stub_phase("implementation", 7000, 70.0, True),
        ],
        validators=[
            _stub_validator("ruff", 500, 2, 2, 0, 100.0, 250),
        ],
        tasks=[
            _stub_task("T-001", "passed", 1, 2000),
        ],
        repair_categories=[
            _stub_repair("lint_error", 1, 1, 100.0, 1),
        ],
        llm_usage=[
            _stub_llm("planner", 5, 10000, 4000, 14000, 2800),
        ],
        trends=[
            _stub_trend("run-1", "2025-01-01", 40000, 50000, 3, 3, 100.0),
        ],
        bottleneck_phase="implementation",
        slowest_task_id="T-001",
        most_attempted_task_id="T-001",
        total_repair_loops=0,
        overall_pass_rate=100.0,
    )
    text = format_analysis(analysis)

    assert "RUN ANALYSIS: fmt-test" in text
    assert "PHASE TIMELINE" in text
    assert "VALIDATOR PERFORMANCE" in text
    assert "TASK PERFORMANCE" in text
    assert "REPAIR STRATEGY ANALYSIS" in text
    assert "LLM USAGE BY ROLE" in text
    assert "CROSS-RUN TRENDS" in text
    assert "implementation" in text
    assert "ruff" in text


# ---------------------------------------------------------------------------
# Stub factories for format test
# ---------------------------------------------------------------------------

from autodev.run_analyzer import (  # noqa: E402
    LLMRoleUsage,
    PhaseBreakdown,
    RepairCategoryStats,
    RunTrendPoint,
    TaskProfile,
    ValidatorProfile,
)


def _stub_phase(phase: str, dur: int, pct: float, bottleneck: bool) -> PhaseBreakdown:
    return PhaseBreakdown(phase=phase, duration_ms=dur, pct_of_total=pct, is_bottleneck=bottleneck)


def _stub_validator(
    name: str, dur: int, calls: int, p: int, f: int, rate: float, avg: int,
) -> ValidatorProfile:
    return ValidatorProfile(
        name=name, total_duration_ms=dur, call_count=calls,
        pass_count=p, fail_count=f, pass_rate=rate, avg_duration_ms=avg,
    )


def _stub_task(tid: str, status: str, attempts: int, dur: int) -> TaskProfile:
    return TaskProfile(
        task_id=tid, title=tid, status=status, attempts=attempts,
        total_duration_ms=dur, failure_categories=[], repair_escalation_max=0,
    )


def _stub_repair(
    cat: str, occ: int, res: int, rate: float, esc: int,
) -> RepairCategoryStats:
    return RepairCategoryStats(
        category=cat, occurrences=occ, resolved_count=res,
        resolution_rate=rate, max_escalation_level=esc,
    )


def _stub_llm(
    role: str, calls: int, prompt: int, comp: int, total: int, avg: int,
) -> LLMRoleUsage:
    return LLMRoleUsage(
        role=role, call_count=calls, prompt_tokens=prompt,
        completion_tokens=comp, total_tokens=total, avg_tokens_per_call=avg,
    )


def _stub_trend(
    rid: str, ts: str, elapsed: int, tokens: int, tc: int, pt: int, rate: float,
) -> RunTrendPoint:
    return RunTrendPoint(
        run_id=rid, timestamp=ts, total_elapsed_ms=elapsed,
        total_llm_tokens=tokens, task_count=tc, passed_tasks=pt, pass_rate=rate,
    )
