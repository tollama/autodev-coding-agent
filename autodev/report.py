from __future__ import annotations

import json
import os
from datetime import datetime
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

    _write(repo_root, ".autodev/REPORT.md", "\n".join(md))
