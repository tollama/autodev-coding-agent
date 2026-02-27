from __future__ import annotations

import json
import os
from datetime import datetime
from html import escape as _esc
from typing import Any, Dict, List

from .json_utils import json_dumps


def _write(repo_root: str, rel_path: str, content: str) -> None:
    p = os.path.join(repo_root, rel_path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)


def _load_quality_summary(repo_root: str) -> Dict[str, Any] | None:
    path = os.path.join(repo_root, ".autodev", "task_quality_index.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_quality_profile(repo_root: str) -> Dict[str, Any] | None:
    path = os.path.join(repo_root, ".autodev", "quality_profile.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_change_summary(repo_root: str) -> Dict[str, Any] | None:
    path = os.path.join(repo_root, ".autodev", "change_summary.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_run_trace(repo_root: str) -> Dict[str, Any] | None:
    """Load ``.autodev/run_trace.json`` for phase timeline data."""
    path = os.path.join(repo_root, ".autodev", "run_trace.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_repair_history(repo_root: str) -> Dict[str, Any] | None:
    """Load ``.autodev/repair_history.json``."""
    path = os.path.join(repo_root, ".autodev", "repair_history.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_perf_baseline(repo_root: str) -> Dict[str, Any] | None:
    """Load ``.autodev/perf_baseline.json`` for performance summary."""
    path = os.path.join(repo_root, ".autodev", "perf_baseline.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _derive_scorecard(quality_summary: Dict[str, Any]) -> Dict[str, Any]:
    tasks = quality_summary.get("tasks", [])
    final = quality_summary.get("final", {})
    totals = quality_summary.get("totals", {})

    passed = sum(1 for t in tasks if t.get("status") == "passed")
    total = len(tasks)
    pass_rate = (passed / total * 100) if total else 0.0

    return {
        "task_pass_rate_percent": round(pass_rate, 1),
        "task_pass_count": passed,
        "task_total": total,
        "final_status": final.get("status", "unknown"),
        "total_task_attempts": totals.get("total_task_attempts", 0),
        "hard_failures": totals.get("hard_failures", 0),
        "soft_failures": totals.get("soft_failures", 0),
        "repair_passes": totals.get("repair_passes", 0),
    }


# ---------------------------------------------------------------------------
# HTML report builder
# ---------------------------------------------------------------------------

_HTML_CSS = """\
<style>
  :root { --pass: #22c55e; --fail: #ef4444; --warn: #f59e0b; --bg: #f8fafc;
          --card-bg: #fff; --border: #e2e8f0; --text: #1e293b; --text-muted: #64748b; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: var(--bg); color: var(--text); line-height: 1.6; padding: 2rem; max-width: 960px; margin: 0 auto; }
  h1 { font-size: 1.75rem; margin-bottom: .25rem; }
  h2 { font-size: 1.25rem; margin-top: 2rem; margin-bottom: .75rem; border-bottom: 2px solid var(--border); padding-bottom: .25rem; }
  .meta { color: var(--text-muted); font-size: .875rem; margin-bottom: 1.5rem; }
  .badge { display: inline-block; padding: .15rem .6rem; border-radius: .25rem; font-weight: 700; font-size: .875rem; }
  .badge-pass { background: var(--pass); color: #fff; }
  .badge-fail { background: var(--fail); color: #fff; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: .75rem; margin-bottom: 1.5rem; }
  .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: .5rem; padding: 1rem; text-align: center; }
  .card .value { font-size: 1.5rem; font-weight: 700; }
  .card .label { font-size: .75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 1rem; background: var(--card-bg); border-radius: .5rem; overflow: hidden; }
  th, td { padding: .5rem .75rem; text-align: left; border-bottom: 1px solid var(--border); font-size: .875rem; }
  th { background: #f1f5f9; font-weight: 600; font-size: .75rem; text-transform: uppercase; letter-spacing: .05em; color: var(--text-muted); }
  tr:last-child td { border-bottom: none; }
  .status-pass { color: var(--pass); font-weight: 600; }
  .status-fail { color: var(--fail); font-weight: 600; }
  .timeline { display: flex; height: 2rem; border-radius: .375rem; overflow: hidden; margin-bottom: 1.5rem; border: 1px solid var(--border); }
  .timeline-seg { display: flex; align-items: center; justify-content: center; font-size: .7rem; font-weight: 600; color: #fff; min-width: 2rem; }
  .file-list { list-style: none; padding: 0; }
  .file-list li { font-size: .8rem; font-family: monospace; padding: .15rem 0; color: var(--text-muted); }
  .file-list li::before { content: '+ '; color: var(--pass); font-weight: 700; }
</style>
"""

_PHASE_COLORS = {
    "prd_analysis": "#8b5cf6",
    "architecture": "#6366f1",
    "planning": "#3b82f6",
    "implementation": "#0ea5e9",
    "final_validation": "#14b8a6",
}

_PHASE_LABELS = {
    "prd_analysis": "PRD",
    "architecture": "Arch",
    "planning": "Plan",
    "implementation": "Impl",
    "final_validation": "Final",
}


def _build_phase_timeline(phases: List[Dict[str, Any]]) -> str:
    """Build a proportional phase timeline bar from run_trace phases."""
    total_ms = sum(p.get("duration_ms", 0) for p in phases)
    if total_ms <= 0:
        return ""

    segments: List[str] = []
    for p in phases:
        name = p.get("phase", "")
        dur = p.get("duration_ms", 0)
        pct = max(dur / total_ms * 100, 3)  # min 3% for visibility
        color = _PHASE_COLORS.get(name, "#94a3b8")
        label = _PHASE_LABELS.get(name, name[:4])
        dur_s = f"{dur / 1000:.1f}s" if dur >= 1000 else f"{dur}ms"
        segments.append(
            f'<div class="timeline-seg" style="width:{pct:.1f}%;background:{color}" '
            f'title="{_esc(name)}: {dur_s}">{_esc(label)}</div>'
        )

    return '<div class="timeline">' + "".join(segments) + "</div>"


def _build_scorecard_cards(scorecard: Dict[str, Any]) -> str:
    """Build a card grid from scorecard metrics."""
    items = [
        ("Pass Rate", f"{scorecard['task_pass_rate_percent']}%"),
        ("Tasks", f"{scorecard['task_pass_count']}/{scorecard['task_total']}"),
        ("Attempts", str(scorecard["total_task_attempts"])),
        ("Repairs", str(scorecard["repair_passes"])),
        ("Hard Fails", str(scorecard["hard_failures"])),
        ("Soft Fails", str(scorecard["soft_failures"])),
    ]
    cards = []
    for label, value in items:
        cards.append(
            f'<div class="card"><div class="value">{_esc(value)}</div>'
            f'<div class="label">{_esc(label)}</div></div>'
        )
    return '<div class="cards">' + "".join(cards) + "</div>"


def _build_task_trend_table(trend: List[Dict[str, Any]]) -> str:
    """Build a table of per-task quality trends."""
    if not trend:
        return ""
    rows: List[str] = []
    for row in trend:
        status = row.get("status", "unknown")
        cls = "status-pass" if status == "passed" else "status-fail"
        icon = "\u2713" if status == "passed" else "\u2717"
        rows.append(
            f"<tr>"
            f'<td>{_esc(str(row.get("task_id", "")))}</td>'
            f'<td class="{cls}">{icon} {_esc(status)}</td>'
            f'<td>{row.get("attempts", 0)}</td>'
            f'<td>{row.get("hard_failures", 0)}</td>'
            f'<td>{row.get("soft_failures", 0)}</td>'
            f"</tr>"
        )
    return (
        "<table>"
        "<thead><tr><th>Task</th><th>Status</th><th>Attempts</th><th>Hard</th><th>Soft</th></tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody></table>"
    )


def _build_validation_table(validation: List[Dict[str, Any]]) -> str:
    """Build a table of final validation results."""
    if not validation:
        return "<p>No validation results.</p>"
    rows: List[str] = []
    for v in validation:
        ok = v.get("ok", False)
        status = v.get("status", "failed")
        cls = "status-pass" if ok else "status-fail"
        icon = "\u2713" if ok else "\u2717"
        dur = v.get("duration_ms", 0)
        dur_str = f"{dur / 1000:.1f}s" if dur >= 1000 else f"{dur}ms"
        rows.append(
            f"<tr>"
            f'<td>{_esc(str(v.get("name", "")))}</td>'
            f'<td class="{cls}">{icon} {_esc(status)}</td>'
            f'<td>{v.get("returncode", "")}</td>'
            f"<td>{dur_str}</td>"
            f"</tr>"
        )
    return (
        "<table>"
        "<thead><tr><th>Validator</th><th>Status</th><th>Code</th><th>Duration</th></tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody></table>"
    )


def _build_repair_table(repair_data: Dict[str, Any]) -> str:
    """Build a table of repair history categories."""
    summary = repair_data.get("summary", {})
    if not summary:
        return ""
    rows: List[str] = []
    for cat, stats in sorted(summary.items()):
        total = stats.get("total", 0)
        resolved = stats.get("resolved", 0)
        rate = (resolved / total * 100) if total else 0.0
        rows.append(
            f"<tr><td>{_esc(cat)}</td><td>{resolved}</td><td>{total}</td><td>{rate:.0f}%</td></tr>"
        )
    return (
        "<table>"
        "<thead><tr><th>Category</th><th>Resolved</th><th>Total</th><th>Rate</th></tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody></table>"
    )


def _build_perf_summary_section(perf_data: Dict[str, Any]) -> str:
    """Build Performance Baseline section for the HTML report.

    Shows current run metrics and baseline comparison with verdicts.
    """
    runs = perf_data.get("runs", [])
    if not runs:
        return ""

    current = runs[-1]
    if not isinstance(current, dict):
        return ""

    # --- Current run metric cards ---
    elapsed_s = current.get("total_elapsed_ms", 0) / 1000
    val_s = current.get("total_validation_ms", 0) / 1000
    tokens = current.get("total_llm_tokens", 0)

    cards = [
        ("Wall Time", f"{elapsed_s:.1f}s"),
        ("Validation", f"{val_s:.1f}s"),
        ("LLM Tokens", f"{tokens:,}"),
        ("Tasks", f"{current.get('passed_tasks', 0)}/{current.get('task_count', 0)}"),
        ("LLM Calls", str(current.get("total_llm_calls", 0))),
        ("Retries", str(current.get("total_llm_retries", 0))),
    ]
    card_html = '<div class="cards">'
    for label, value in cards:
        card_html += (
            f'<div class="card"><div class="value">{_esc(value)}</div>'
            f'<div class="label">{_esc(label)}</div></div>'
        )
    card_html += "</div>"

    # --- Baseline comparison table ---
    last_check = perf_data.get("last_check_result")
    comparison_html = ""
    if isinstance(last_check, dict) and last_check.get("has_baseline"):
        verdicts = last_check.get("verdicts", [])
        if verdicts:
            verdict_badge = "PASS" if last_check.get("ok") else "REGRESSION"
            badge_cls = "badge-pass" if last_check.get("ok") else "badge-fail"
            comparison_html += (
                f'<p>Baseline ({last_check.get("baseline_run_count", 0)} runs): '
                f'<span class="badge {badge_cls}">{verdict_badge}</span></p>'
            )
            comparison_html += (
                "<table>"
                "<thead><tr><th>Metric</th><th>Current</th><th>Baseline Avg</th>"
                "<th>Delta</th><th>Ratio</th><th>Status</th></tr></thead><tbody>"
            )
            for v in verdicts:
                if not isinstance(v, dict):
                    continue
                ok = v.get("ok", True)
                cls = "status-pass" if ok else "status-fail"
                icon = "\u2713" if ok else "\u2717"
                metric = v.get("metric_name", "")
                cur = v.get("current_value", 0)
                avg = v.get("baseline_avg", 0)
                delta = v.get("delta", 0)
                ratio = v.get("ratio", 0)
                comparison_html += (
                    f"<tr>"
                    f"<td>{_esc(metric)}</td>"
                    f"<td>{cur:,.0f}</td>"
                    f"<td>{avg:,.0f}</td>"
                    f"<td>{delta:+,.0f}</td>"
                    f"<td>{ratio:+.1%}</td>"
                    f'<td class="{cls}">{icon}</td>'
                    f"</tr>"
                )
            comparison_html += "</tbody></table>"

    return card_html + comparison_html


def _build_change_scope(change_summary: Dict[str, Any]) -> str:
    """Build change scope section HTML."""
    incremental = change_summary.get("incremental_mode", False)
    title = "Change Scope (Incremental Mode)" if incremental else "Change Scope"
    html = f"<h2>{_esc(title)}</h2>"
    html += (
        f'<p>Files added: <strong>{change_summary.get("files_added_count", 0)}</strong> | '
        f'Modified: <strong>{change_summary.get("files_possibly_modified_count", 0)}</strong> | '
        f'Deleted: <strong>{change_summary.get("files_deleted_count", 0)}</strong></p>'
    )
    added = change_summary.get("files_added", [])
    if added:
        items = "".join(f"<li>{_esc(f)}</li>" for f in added[:30])
        html += '<ul class="file-list">' + items + "</ul>"
        if len(added) > 30:
            html += f"<p>... and {len(added) - 30} more</p>"
    return html


def _build_html_report(
    prd_struct: Dict[str, Any],
    plan: Dict[str, Any],
    final_validation: Any,
    ok: bool,
    quality_summary: Dict[str, Any],
    quality_profile: Dict[str, Any],
    run_trace: Dict[str, Any] | None,
    repair_data: Dict[str, Any] | None,
    change_summary: Dict[str, Any] | None,
    ts: str,
    perf_baseline: Dict[str, Any] | None = None,
) -> str:
    """Build a self-contained HTML report string."""
    title = _esc(str(prd_struct.get("title", "AutoDev Report")))
    project_type = _esc(str(plan.get("project", {}).get("type", "")))
    badge_cls = "badge-pass" if ok else "badge-fail"
    badge_text = "PASSED" if ok else "FAILED"

    profile_name = _esc(str(quality_profile.get("name", "")))
    run_id = ""
    if run_trace:
        run_id = _esc(str(run_trace.get("run_id", "")))

    # --- Header ---
    body: List[str] = []
    body.append(f'<h1>{title} <span class="badge {badge_cls}">{badge_text}</span></h1>')
    meta_parts = [f"Generated: {_esc(ts)}"]
    if project_type:
        meta_parts.append(f"Type: {project_type}")
    if profile_name:
        meta_parts.append(f"Profile: {profile_name}")
    if run_id:
        meta_parts.append(f"Run: {run_id[:12]}")
    body.append(f'<div class="meta">{" &middot; ".join(meta_parts)}</div>')

    # --- Phase Timeline ---
    if run_trace and run_trace.get("phases"):
        body.append("<h2>Phase Timeline</h2>")
        body.append(_build_phase_timeline(run_trace["phases"]))

    # --- Quality Scorecard ---
    if quality_summary:
        scorecard = _derive_scorecard(quality_summary)
        body.append("<h2>Quality Scorecard</h2>")
        body.append(_build_scorecard_cards(scorecard))

        # --- Task Quality Trend ---
        trend = quality_summary.get("task_validation_trend", [])
        if trend:
            body.append("<h2>Task Quality Trend</h2>")
            body.append(_build_task_trend_table(trend))

        # --- Unresolved Blockers ---
        blockers = quality_summary.get("unresolved_blockers", [])
        if blockers:
            body.append("<h2>Unresolved Blockers</h2>")
            items = "".join(f"<li>{_esc(str(b))}</li>" for b in blockers)
            body.append(f"<ul>{items}</ul>")

    # --- Final Validation ---
    if isinstance(final_validation, list) and final_validation:
        body.append("<h2>Final Validation</h2>")
        body.append(_build_validation_table(final_validation))

    # --- Repair History ---
    if repair_data:
        repair_table = _build_repair_table(repair_data)
        if repair_table:
            body.append("<h2>Repair Strategy</h2>")
            body.append(repair_table)

    # --- Performance Baseline ---
    if perf_baseline:
        perf_section = _build_perf_summary_section(perf_baseline)
        if perf_section:
            body.append("<h2>Performance Baseline</h2>")
            body.append(perf_section)

    # --- Change Scope ---
    if change_summary:
        body.append(_build_change_scope(change_summary))

    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>AutoDev Report - {title}</title>\n"
        f"{_HTML_CSS}\n"
        "</head>\n<body>\n"
        + "\n".join(body)
        + "\n</body>\n</html>"
    )


# ---------------------------------------------------------------------------
# Markdown report (existing — unchanged)
# ---------------------------------------------------------------------------


def write_report(repo_root: str, prd_struct: Dict[str, Any], plan: Dict[str, Any], final_validation: Any, ok: bool) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    quality_summary = _load_quality_summary(repo_root) or {}
    quality_profile = _load_quality_profile(repo_root) or {}

    md: List[str] = []
    md.append("# AUTODEV REPORT")
    md.append(f"- timestamp: {ts}")
    md.append(f"- ok: {ok}")
    md.append("")

    md.append("## Project")
    md.append(f"- title: {prd_struct.get('title')}")
    md.append(f"- type: {plan.get('project', {}).get('type')}")
    if quality_profile:
        md.append(f"- quality_gate_profile: {quality_profile.get('name', 'balanced')}")
        md.append(f"- resolved_profile: {json_dumps(quality_profile.get('resolved_from'))}")

    md.append("")
    md.append("## Final Validation")
    md.append("```json")
    md.append(json_dumps(final_validation))
    md.append("```")

    if quality_summary:
        md.append("")
        md.append("## Quality Scorecard")
        scorecard = _derive_scorecard(quality_summary)
        for key in [
            "task_pass_rate_percent",
            "task_pass_count",
            "task_total",
            "final_status",
            "total_task_attempts",
            "hard_failures",
            "soft_failures",
            "repair_passes",
        ]:
            md.append(f"- {key}: {scorecard.get(key)}")

        md.append("")
        md.append("### Task Validation Trend")
        for row in quality_summary.get("task_validation_trend", []):
            md.append(
                f"- {row.get('task_id')}: status={row.get('status')} "
                f"attempts={row.get('attempts')} hard={row.get('hard_failures')} soft={row.get('soft_failures')}"
            )

        unresolved = quality_summary.get("unresolved_blockers", [])
        if unresolved:
            md.append("")
            md.append("### Unresolved Blockers")
            for t in unresolved:
                md.append(f"- {t}")

        totals = quality_summary.get("totals", {})
        md.append("")
        md.append("### Aggregate Metrics")
        md.append(f"- tasks: {totals.get('tasks', len(quality_summary.get('tasks', [])))}")
        md.append(f"- successful_tasks: {totals.get('successful_tasks', 0)}")
        md.append(f"- total_task_attempts: {totals.get('total_task_attempts', 0)}")
        md.append(f"- repair_passes: {totals.get('repair_passes', 0)}")
        md.append(f"- hard_failures: {totals.get('hard_failures', 0)}")
        md.append(f"- soft_failures: {totals.get('soft_failures', 0)}")

        md.append("")
        md.append("### Per-task quality artifacts")
        for task in quality_summary.get("tasks", []):
            task_id = task.get("task_id")
            if not task_id:
                continue
            md.append(f"- {task_id}: {task.get('status')} (attempts={task.get('attempts', 0)})")

    repair_history_path = os.path.join(repo_root, ".autodev", "repair_history.json")
    if os.path.exists(repair_history_path):
        with open(repair_history_path, "r", encoding="utf-8") as f:
            repair_data = json.load(f)
        summary_data = repair_data.get("summary", {})
        if summary_data:
            md.append("")
            md.append("## Repair Strategy Analysis")
            for cat, stats in sorted(summary_data.items()):
                total = stats.get("total", 0)
                resolved = stats.get("resolved", 0)
                rate = (resolved / total * 100) if total else 0.0
                md.append(f"- {cat}: {resolved}/{total} ({rate:.0f}%)")

    perf_baseline = _load_perf_baseline(repo_root)
    if perf_baseline and perf_baseline.get("runs"):
        md.append("")
        md.append("## Performance Baseline")
        runs = perf_baseline["runs"]
        current = runs[-1] if isinstance(runs, list) and runs else {}
        if isinstance(current, dict):
            md.append(f"- total_elapsed_ms: {current.get('total_elapsed_ms', 0)}")
            md.append(f"- total_validation_ms: {current.get('total_validation_ms', 0)}")
            md.append(f"- total_llm_tokens: {current.get('total_llm_tokens', 0)}")
            md.append(f"- baseline_runs: {len(runs)}")
        last_check = perf_baseline.get("last_check_result")
        if isinstance(last_check, dict) and last_check.get("has_baseline"):
            for v in last_check.get("verdicts", []):
                if not isinstance(v, dict):
                    continue
                status = "OK" if v.get("ok") else "REGRESSION"
                md.append(
                    f"- {v.get('metric_name', '')}: {v.get('current_value', 0):,.0f} "
                    f"(baseline avg: {v.get('baseline_avg', 0):,.0f}, "
                    f"delta: {v.get('delta', 0):+,.0f}) [{status}]"
                )

    change_summary = _load_change_summary(repo_root)
    if change_summary:
        md.append("")
        if change_summary.get("incremental_mode"):
            md.append("## Change Scope (Incremental Mode)")
        else:
            md.append("## Change Scope")
        md.append(f"- Files added: {change_summary.get('files_added_count', 0)}")
        md.append(f"- Files possibly modified: {change_summary.get('files_possibly_modified_count', 0)}")
        md.append(f"- Files deleted: {change_summary.get('files_deleted_count', 0)}")
        added = change_summary.get("files_added", [])
        if added:
            md.append("")
            md.append("### New Files")
            for f in added[:30]:
                md.append(f"- `{f}`")
            if len(added) > 30:
                md.append(f"- ... and {len(added) - 30} more")

    _write(repo_root, ".autodev/REPORT.md", "\n".join(md))

    # --- HTML report ---
    run_trace = _load_run_trace(repo_root)
    repair_data_html = _load_repair_history(repo_root)
    html = _build_html_report(
        prd_struct=prd_struct,
        plan=plan,
        final_validation=final_validation,
        ok=ok,
        quality_summary=quality_summary,
        quality_profile=quality_profile,
        run_trace=run_trace,
        repair_data=repair_data_html,
        change_summary=change_summary,
        ts=ts,
        perf_baseline=perf_baseline,
    )
    _write(repo_root, ".autodev/REPORT.html", html)
