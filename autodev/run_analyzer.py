"""Run replay & analyzer — structured diagnostics from .autodev/ artifacts.

Reads the four main artifacts produced by each AutoDev run and generates a
comprehensive analysis covering phase timeline, validator performance, task
profiling, repair strategy effectiveness, LLM usage breakdown, and cross-run
trends.

Pure read-only module with **no side effects** — never writes files, never
modifies state.  Gracefully degrades when artifacts are missing or malformed.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PhaseBreakdown:
    """Timing breakdown for a single pipeline phase."""

    phase: str
    duration_ms: int
    pct_of_total: float
    is_bottleneck: bool  # >40 % of total


@dataclass
class ValidatorProfile:
    """Aggregated performance profile for a single validator."""

    name: str
    total_duration_ms: int
    call_count: int
    pass_count: int
    fail_count: int
    pass_rate: float  # 0.0–100.0
    avg_duration_ms: int


@dataclass
class TaskProfile:
    """Execution profile for a single task."""

    task_id: str
    title: str
    status: str  # "passed" | "failed" | "skipped"
    attempts: int
    total_duration_ms: int
    failure_categories: List[str]
    repair_escalation_max: int


@dataclass
class RepairCategoryStats:
    """Category-level repair statistics."""

    category: str
    occurrences: int
    resolved_count: int
    resolution_rate: float  # 0.0–100.0
    max_escalation_level: int


@dataclass
class LLMRoleUsage:
    """Per-role LLM usage statistics."""

    role: str
    call_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    avg_tokens_per_call: int


@dataclass
class RunTrendPoint:
    """A single data point in cross-run trend analysis."""

    run_id: str
    timestamp: str
    total_elapsed_ms: int
    total_llm_tokens: int
    task_count: int
    passed_tasks: int
    pass_rate: float  # 0.0–100.0


@dataclass
class RunAnalysis:
    """Complete analysis result for a single run."""

    run_id: str
    total_elapsed_ms: int
    phases: List[PhaseBreakdown] = field(default_factory=list)
    validators: List[ValidatorProfile] = field(default_factory=list)
    tasks: List[TaskProfile] = field(default_factory=list)
    repair_categories: List[RepairCategoryStats] = field(default_factory=list)
    llm_usage: List[LLMRoleUsage] = field(default_factory=list)
    trends: List[RunTrendPoint] = field(default_factory=list)
    # Summary fields
    bottleneck_phase: str | None = None
    slowest_task_id: str | None = None
    most_attempted_task_id: str | None = None
    total_repair_loops: int = 0
    overall_pass_rate: float = 0.0


# ---------------------------------------------------------------------------
# JSON loader
# ---------------------------------------------------------------------------


def _load_json(ws_root: str, rel_path: str) -> Dict[str, Any] | None:
    """Load a JSON file relative to *ws_root*.  Returns ``None`` on failure."""
    path = os.path.join(ws_root, rel_path)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Phase analysis
# ---------------------------------------------------------------------------


def _analyze_phases(trace: Dict[str, Any]) -> List[PhaseBreakdown]:
    """Extract phase timeline from *trace["phases"]*."""
    phases_raw = trace.get("phases")
    if not isinstance(phases_raw, list) or not phases_raw:
        return []

    total_ms = max(
        sum(_safe_int(p.get("duration_ms", 0)) for p in phases_raw if isinstance(p, dict)),
        1,
    )

    result: List[PhaseBreakdown] = []
    for entry in phases_raw:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("phase", ""))
        dur = _safe_int(entry.get("duration_ms", 0))
        pct = round(dur / total_ms * 100, 1)
        result.append(PhaseBreakdown(
            phase=name,
            duration_ms=dur,
            pct_of_total=pct,
            is_bottleneck=pct > 40.0,
        ))
    return result


# ---------------------------------------------------------------------------
# Validator analysis
# ---------------------------------------------------------------------------


def _analyze_validators(quality: Dict[str, Any]) -> List[ValidatorProfile]:
    """Aggregate validator stats from tasks[].last_validation + final.validations."""
    acc: Dict[str, Dict[str, int]] = {}  # name → {dur, calls, pass, fail}

    def _process_rows(rows: object) -> None:
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name", ""))
            if not name:
                continue
            if name not in acc:
                acc[name] = {"dur": 0, "calls": 0, "pass": 0, "fail": 0}
            acc[name]["calls"] += 1
            acc[name]["dur"] += _safe_int(row.get("duration_ms", 0))
            if row.get("ok", False) is True:
                acc[name]["pass"] += 1
            else:
                acc[name]["fail"] += 1

    # Per-task last_validation
    tasks = quality.get("tasks")
    if isinstance(tasks, list):
        for task in tasks:
            if isinstance(task, dict):
                _process_rows(task.get("last_validation"))

    # Final validation
    final = quality.get("final")
    if isinstance(final, dict):
        _process_rows(final.get("validations"))

    result: List[ValidatorProfile] = []
    for name, data in sorted(acc.items()):
        calls = data["calls"]
        passes = data["pass"]
        total = passes + data["fail"]
        rate = round(passes / total * 100, 1) if total > 0 else 0.0
        avg_dur = int(data["dur"] / calls) if calls > 0 else 0
        result.append(ValidatorProfile(
            name=name,
            total_duration_ms=data["dur"],
            call_count=calls,
            pass_count=passes,
            fail_count=data["fail"],
            pass_rate=rate,
            avg_duration_ms=avg_dur,
        ))
    return result


# ---------------------------------------------------------------------------
# Task analysis
# ---------------------------------------------------------------------------


def _analyze_tasks(quality: Dict[str, Any]) -> List[TaskProfile]:
    """Extract per-task profiles from quality["tasks"]."""
    tasks_raw = quality.get("tasks")
    if not isinstance(tasks_raw, list) or not tasks_raw:
        return []

    result: List[TaskProfile] = []
    for task in tasks_raw:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("task_id", ""))
        title = str(task.get("title", task_id))
        status = str(task.get("status", "unknown"))
        attempts = _safe_int(task.get("attempts", 1))

        # Total duration from attempt_trend
        total_dur = 0
        trend = task.get("attempt_trend")
        if isinstance(trend, list):
            for entry in trend:
                if isinstance(entry, dict):
                    total_dur += _safe_int(entry.get("duration_ms", 0))

        # Failure categories from last_validation
        fail_cats: List[str] = []
        last_val = task.get("last_validation")
        if isinstance(last_val, list):
            for row in last_val:
                if isinstance(row, dict) and row.get("ok") is not True:
                    ec = row.get("error_classification")
                    if ec:
                        fail_cats.append(str(ec))

        # Repair escalation: max attempt number
        escalation = max(attempts - 1, 0)

        result.append(TaskProfile(
            task_id=task_id,
            title=title,
            status=status,
            attempts=attempts,
            total_duration_ms=total_dur,
            failure_categories=fail_cats,
            repair_escalation_max=escalation,
        ))
    return result


# ---------------------------------------------------------------------------
# Repair analysis
# ---------------------------------------------------------------------------


def _analyze_repairs(repair_history: Dict[str, Any]) -> List[RepairCategoryStats]:
    """Extract category-level repair stats from repair_history."""
    summary = repair_history.get("summary")
    outcomes = repair_history.get("outcomes")

    if not isinstance(summary, dict) or not summary:
        return []

    # Find max escalation per category from outcomes
    max_esc: Dict[str, int] = {}
    if isinstance(outcomes, list):
        for outcome in outcomes:
            if not isinstance(outcome, dict):
                continue
            cat = str(outcome.get("category", ""))
            esc = _safe_int(outcome.get("escalation_level", 0))
            if cat:
                max_esc[cat] = max(max_esc.get(cat, 0), esc)

    result: List[RepairCategoryStats] = []
    for cat, data in sorted(summary.items()):
        if not isinstance(data, dict):
            continue
        total = _safe_int(data.get("total", 0))
        resolved = _safe_int(data.get("resolved", 0))
        rate = round(resolved / total * 100, 1) if total > 0 else 0.0
        result.append(RepairCategoryStats(
            category=cat,
            occurrences=total,
            resolved_count=resolved,
            resolution_rate=rate,
            max_escalation_level=max_esc.get(cat, 0),
        ))
    return result


# ---------------------------------------------------------------------------
# LLM usage analysis
# ---------------------------------------------------------------------------


def _analyze_llm_usage(trace: Dict[str, Any]) -> List[LLMRoleUsage]:
    """Extract per-role LLM usage from trace["llm_metrics"]."""
    metrics = trace.get("llm_metrics")
    if not isinstance(metrics, dict) or not metrics:
        return []

    result: List[LLMRoleUsage] = []
    for role, data in sorted(metrics.items()):
        if not isinstance(data, dict):
            continue
        calls = _safe_int(data.get("call_count", 0))
        prompt = _safe_int(data.get("total_prompt_tokens", 0))
        completion = _safe_int(data.get("total_completion_tokens", 0))
        total = prompt + completion
        avg = int(total / calls) if calls > 0 else 0
        result.append(LLMRoleUsage(
            role=role,
            call_count=calls,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=total,
            avg_tokens_per_call=avg,
        ))
    return result


# ---------------------------------------------------------------------------
# Cross-run trend analysis
# ---------------------------------------------------------------------------

_MAX_TREND_POINTS = 10


def _analyze_trends(baseline: Dict[str, Any]) -> List[RunTrendPoint]:
    """Extract cross-run trend data from perf_baseline["runs"] (last 10)."""
    runs = baseline.get("runs")
    if not isinstance(runs, list) or not runs:
        return []

    recent = runs[-_MAX_TREND_POINTS:] if len(runs) > _MAX_TREND_POINTS else runs

    result: List[RunTrendPoint] = []
    for run in recent:
        if not isinstance(run, dict):
            continue
        task_count = _safe_int(run.get("task_count", 0))
        passed = _safe_int(run.get("passed_tasks", 0))
        rate = round(passed / task_count * 100, 1) if task_count > 0 else 0.0
        result.append(RunTrendPoint(
            run_id=str(run.get("run_id", "")),
            timestamp=str(run.get("timestamp", "")),
            total_elapsed_ms=_safe_int(run.get("total_elapsed_ms", 0)),
            total_llm_tokens=_safe_int(run.get("total_llm_tokens", 0)),
            task_count=task_count,
            passed_tasks=passed,
            pass_rate=rate,
        ))
    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def analyze_run(ws_root: str) -> RunAnalysis:
    """Analyse a single run from ``.autodev/`` artifacts.

    Reads ``run_trace.json``, ``task_quality_index.json``,
    ``repair_history.json``, and ``perf_baseline.json``.  Missing or
    malformed files result in empty sections — never raises.
    """
    trace = _load_json(ws_root, ".autodev/run_trace.json") or {}
    quality = _load_json(ws_root, ".autodev/task_quality_index.json") or {}
    repair = _load_json(ws_root, ".autodev/repair_history.json") or {}
    baseline = _load_json(ws_root, ".autodev/perf_baseline.json") or {}

    run_id = str(trace.get("run_id", "unknown"))
    total_elapsed = _safe_int(trace.get("total_elapsed_ms", 0))

    phases = _analyze_phases(trace)
    validators = _analyze_validators(quality)
    tasks = _analyze_tasks(quality)
    repair_categories = _analyze_repairs(repair)
    llm_usage = _analyze_llm_usage(trace)
    trends = _analyze_trends(baseline)

    # Summary derivations
    bottleneck = None
    for p in phases:
        if p.is_bottleneck:
            bottleneck = p.phase
            break

    slowest_id = None
    most_attempted_id = None
    if tasks:
        slowest = max(tasks, key=lambda t: t.total_duration_ms)
        slowest_id = slowest.task_id
        most_attempted = max(tasks, key=lambda t: t.attempts)
        most_attempted_id = most_attempted.task_id

    total_repair = sum(max(t.attempts - 1, 0) for t in tasks)

    # Overall pass rate from quality totals
    totals = quality.get("totals")
    if isinstance(totals, dict):
        total_tasks = _safe_int(totals.get("tasks", 0))
        successful = _safe_int(totals.get("successful_tasks", 0))
        pass_rate = round(successful / total_tasks * 100, 1) if total_tasks > 0 else 0.0
    else:
        passed_count = sum(1 for t in tasks if t.status == "passed")
        pass_rate = round(passed_count / len(tasks) * 100, 1) if tasks else 0.0

    return RunAnalysis(
        run_id=run_id,
        total_elapsed_ms=total_elapsed,
        phases=phases,
        validators=validators,
        tasks=tasks,
        repair_categories=repair_categories,
        llm_usage=llm_usage,
        trends=trends,
        bottleneck_phase=bottleneck,
        slowest_task_id=slowest_id,
        most_attempted_task_id=most_attempted_id,
        total_repair_loops=total_repair,
        overall_pass_rate=pass_rate,
    )


# ---------------------------------------------------------------------------
# Text formatter
# ---------------------------------------------------------------------------

_SEP = "=" * 80
_LINE = "-" * 80


def _fmt_ms(ms: int) -> str:
    """Format milliseconds as a human-readable duration."""
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms}ms"


def _fmt_tokens(n: int) -> str:
    """Format token count with thousands separator."""
    return f"{n:,}"


def format_analysis(analysis: RunAnalysis) -> str:
    """Render a :class:`RunAnalysis` as a human-readable ASCII report."""
    lines: List[str] = []

    # Header
    lines.append(_SEP)
    lines.append(
        f"RUN ANALYSIS: {analysis.run_id}"
    )
    lines.append(
        f"Total Elapsed: {_fmt_ms(analysis.total_elapsed_ms)} | "
        f"Pass Rate: {analysis.overall_pass_rate}% | "
        f"Bottleneck: {analysis.bottleneck_phase or 'none'}"
    )
    lines.append(_SEP)

    # Phase timeline
    if analysis.phases:
        lines.append("")
        lines.append("PHASE TIMELINE")
        lines.append(_LINE)
        lines.append(f"{'Phase':<25} {'Duration':>12} {'% Total':>10}    Bottleneck")
        lines.append(_LINE)
        for p in analysis.phases:
            mark = "■■■" if p.is_bottleneck else ""
            lines.append(
                f"{p.phase:<25} {_fmt_ms(p.duration_ms):>12} {p.pct_of_total:>9.1f}%    {mark}"
            )

    # Validator performance
    if analysis.validators:
        lines.append("")
        lines.append("VALIDATOR PERFORMANCE")
        lines.append(_LINE)
        lines.append(
            f"{'Validator':<20} {'Calls':>8} {'Pass Rate':>12} {'Total Time':>14} {'Avg Time':>12}"
        )
        lines.append(_LINE)
        for v in analysis.validators:
            lines.append(
                f"{v.name:<20} {v.call_count:>8} {v.pass_rate:>11.1f}% "
                f"{_fmt_ms(v.total_duration_ms):>14} {_fmt_ms(v.avg_duration_ms):>12}"
            )

    # Task performance
    if analysis.tasks:
        lines.append("")
        lines.append("TASK PERFORMANCE")
        lines.append(_LINE)
        lines.append(
            f"{'Task ID':<30} {'Status':<10} {'Attempts':>10} {'Duration':>12}"
        )
        lines.append(_LINE)
        for t in analysis.tasks:
            lines.append(
                f"{t.task_id:<30} {t.status:<10} {t.attempts:>10} "
                f"{_fmt_ms(t.total_duration_ms):>12}"
            )
        lines.append(
            f"Slowest: {analysis.slowest_task_id} | "
            f"Most Attempts: {analysis.most_attempted_task_id} | "
            f"Repair Loops: {analysis.total_repair_loops}"
        )

    # Repair strategy analysis
    if analysis.repair_categories:
        lines.append("")
        lines.append("REPAIR STRATEGY ANALYSIS")
        lines.append(_LINE)
        lines.append(
            f"{'Category':<30} {'Count':>8} {'Resolved':>10} {'Rate':>10} {'Max Esc':>10}"
        )
        lines.append(_LINE)
        for r in analysis.repair_categories:
            lines.append(
                f"{r.category:<30} {r.occurrences:>8} {r.resolved_count:>10} "
                f"{r.resolution_rate:>9.1f}% {r.max_escalation_level:>10}"
            )

    # LLM usage
    if analysis.llm_usage:
        lines.append("")
        lines.append("LLM USAGE BY ROLE")
        lines.append(_LINE)
        lines.append(
            f"{'Role':<20} {'Calls':>8} {'Prompt':>12} {'Completion':>12} "
            f"{'Total':>12} {'Avg/Call':>12}"
        )
        lines.append(_LINE)
        for u in analysis.llm_usage:
            lines.append(
                f"{u.role:<20} {u.call_count:>8} {_fmt_tokens(u.prompt_tokens):>12} "
                f"{_fmt_tokens(u.completion_tokens):>12} {_fmt_tokens(u.total_tokens):>12} "
                f"{_fmt_tokens(u.avg_tokens_per_call):>12}"
            )

    # Cross-run trends
    if analysis.trends:
        lines.append("")
        lines.append("CROSS-RUN TRENDS")
        lines.append(_LINE)
        lines.append(
            f"{'Run ID':<16} {'Time':>10} {'Tokens':>12} {'Tasks':>10} {'Pass Rate':>12}"
        )
        lines.append(_LINE)
        for t in analysis.trends:
            lines.append(
                f"{t.run_id:<16} {_fmt_ms(t.total_elapsed_ms):>10} "
                f"{_fmt_tokens(t.total_llm_tokens):>12} "
                f"{t.passed_tasks}/{t.task_count:>8} {t.pass_rate:>11.1f}%"
            )

    lines.append(_SEP)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_int(value: object) -> int:
    """Coerce to int, returning 0 on failure."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
