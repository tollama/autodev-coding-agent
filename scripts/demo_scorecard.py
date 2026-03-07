#!/usr/bin/env python3
"""Generate a concise local demo scorecard from recent runs.

Outputs:
- Markdown summary (operator-friendly)
- JSON payload (automation-friendly)

Default output location:
- artifacts/demo-day/demo_scorecard_latest.md
- artifacts/demo-day/demo_scorecard_latest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autodev.gui_mvp_dto import normalize_validation
from autodev.run_status import normalize_run_status


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    status: str
    profile: str
    model: str
    completed_at: str
    totals: dict[str, int]
    blockers: list[str]
    validation: dict[str, int]
    failed_validators: list[str]


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _extract_completed_at(run_trace: dict[str, Any] | None, metadata: dict[str, Any] | None) -> str:
    if isinstance(run_trace, dict):
        completed = str(run_trace.get("run_completed_at") or "").strip()
        if completed:
            return completed
    if isinstance(metadata, dict):
        completed = str(metadata.get("run_completed_at") or "").strip()
        if completed:
            return completed
    return ""


def _build_run_summary(run_dir: Path) -> RunSummary:
    ad = run_dir / ".autodev"
    quality = _read_json(ad / "task_quality_index.json") or {}
    final_validation = _read_json(ad / "task_final_last_validation.json") or {}
    run_trace = _read_json(ad / "run_trace.json") or {}
    metadata = _read_json(ad / "run_metadata.json") or {}
    checkpoint = _read_json(ad / "checkpoint.json") or {}

    totals = quality.get("totals") if isinstance(quality.get("totals"), dict) else {}
    resolved_profile = quality.get("resolved_quality_profile") if isinstance(quality.get("resolved_quality_profile"), dict) else {}
    blockers_raw = quality.get("unresolved_blockers")
    blockers = [str(b) for b in blockers_raw] if isinstance(blockers_raw, list) else []

    validation_norm = normalize_validation(final_validation, quality)
    validation_summary = validation_norm.get("summary") if isinstance(validation_norm.get("summary"), dict) else {}
    cards = validation_norm.get("validator_cards") if isinstance(validation_norm.get("validator_cards"), list) else []

    failed_validators = sorted(
        {
            str(card.get("name") or "").strip()
            for card in cards
            if isinstance(card, dict)
            and str(card.get("status") or "").strip().lower() == "failed"
            and str(card.get("name") or "").strip()
        }
    )

    model = ""
    llm = run_trace.get("llm") if isinstance(run_trace.get("llm"), dict) else {}
    if llm:
        model = str(llm.get("model") or "").strip()
    if not model:
        model = str(run_trace.get("model") or "").strip()

    return RunSummary(
        run_id=run_dir.name,
        status=normalize_run_status(metadata=metadata, checkpoint=checkpoint, quality_index=quality),
        profile=str(resolved_profile.get("name") or metadata.get("requested_profile") or "").strip(),
        model=model,
        completed_at=_extract_completed_at(run_trace, metadata),
        totals={
            "total_task_attempts": _safe_int(totals.get("total_task_attempts"), 0),
            "hard_failures": _safe_int(totals.get("hard_failures"), 0),
            "soft_failures": _safe_int(totals.get("soft_failures"), 0),
        },
        blockers=blockers,
        validation={
            "total": _safe_int(validation_summary.get("total"), 0),
            "passed": _safe_int(validation_summary.get("passed"), 0),
            "failed": _safe_int(validation_summary.get("failed"), 0),
            "soft_fail": _safe_int(validation_summary.get("soft_fail"), 0),
            "skipped": _safe_int(validation_summary.get("skipped"), 0),
            "blocking_failed": _safe_int(validation_summary.get("blocking_failed"), 0),
        },
        failed_validators=failed_validators,
    )


def _discover_runs(runs_root: Path, latest: int, run_ids: list[str] | None = None) -> list[Path]:
    if not runs_root.is_dir():
        return []

    wanted = {rid.strip() for rid in run_ids or [] if rid.strip()}
    run_dirs: list[Path] = []
    for child in runs_root.iterdir():
        if not child.is_dir():
            continue
        if wanted and child.name not in wanted:
            continue
        run_dirs.append(child)

    run_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    if latest > 0:
        return run_dirs[:latest]
    return run_dirs


def _compute_delta(previous: RunSummary, latest: RunSummary) -> dict[str, Any]:
    prev_blockers = set(previous.blockers)
    latest_blockers = set(latest.blockers)
    prev_failed = set(previous.failed_validators)
    latest_failed = set(latest.failed_validators)

    return {
        "from_run_id": previous.run_id,
        "to_run_id": latest.run_id,
        "status_changed": previous.status != latest.status,
        "status": {"from": previous.status, "to": latest.status},
        "totals": {
            "total_task_attempts": latest.totals["total_task_attempts"] - previous.totals["total_task_attempts"],
            "hard_failures": latest.totals["hard_failures"] - previous.totals["hard_failures"],
            "soft_failures": latest.totals["soft_failures"] - previous.totals["soft_failures"],
        },
        "validation": {
            "passed": latest.validation["passed"] - previous.validation["passed"],
            "failed": latest.validation["failed"] - previous.validation["failed"],
            "blocking_failed": latest.validation["blocking_failed"] - previous.validation["blocking_failed"],
            "new_failed_validators": sorted(latest_failed - prev_failed),
            "resolved_failed_validators": sorted(prev_failed - latest_failed),
        },
        "blockers": {
            "count": len(latest.blockers) - len(previous.blockers),
            "added": sorted(latest_blockers - prev_blockers),
            "resolved": sorted(prev_blockers - latest_blockers),
        },
    }


def _compute_trends(runs: list[RunSummary]) -> dict[str, Any]:
    status_counts = Counter(r.status for r in runs)
    validator_fail_counts = Counter()
    blocker_counts = Counter()

    total_hard = 0
    total_soft = 0
    for run in runs:
        total_hard += run.totals["hard_failures"]
        total_soft += run.totals["soft_failures"]
        validator_fail_counts.update(run.failed_validators)
        blocker_counts.update(run.blockers)

    run_count = len(runs)
    pass_rate = (status_counts.get("ok", 0) / run_count * 100.0) if run_count else 0.0

    return {
        "run_count": run_count,
        "status_counts": dict(status_counts),
        "pass_rate_percent": round(pass_rate, 1),
        "avg_hard_failures": round(total_hard / run_count, 2) if run_count else 0.0,
        "avg_soft_failures": round(total_soft / run_count, 2) if run_count else 0.0,
        "top_failed_validators": [
            {"name": name, "count": count} for name, count in validator_fail_counts.most_common(5)
        ],
        "top_blockers": [{"name": name, "count": count} for name, count in blocker_counts.most_common(5)],
    }


def build_scorecard(runs_root: Path, *, latest: int, run_ids: list[str] | None = None) -> dict[str, Any]:
    discovered = _discover_runs(runs_root, latest, run_ids)
    summaries = [_build_run_summary(run_dir) for run_dir in discovered]

    if not summaries:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runs_root": str(runs_root),
            "status": "unknown",
            "latest": None,
            "compare_delta": None,
            "trends": _compute_trends([]),
            "notes": ["No runs discovered. Check --runs-root or generate fixture runs first."],
        }

    latest_run = summaries[0]
    previous_run = summaries[1] if len(summaries) > 1 else None
    compare_delta = _compute_delta(previous_run, latest_run) if previous_run else None

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runs_root": str(runs_root),
        "status": latest_run.status,
        "latest": {
            "run_id": latest_run.run_id,
            "status": latest_run.status,
            "profile": latest_run.profile,
            "model": latest_run.model,
            "completed_at": latest_run.completed_at,
            "totals": latest_run.totals,
            "validation": latest_run.validation,
            "blockers": latest_run.blockers,
            "failed_validators": latest_run.failed_validators,
        },
        "compare_delta": compare_delta,
        "trends": _compute_trends(summaries),
    }


def _format_int_delta(value: int) -> str:
    return f"{value:+d}"


def _format_pct(value: float) -> str:
    return f"{value:.1f}%"


def render_markdown(scorecard: dict[str, Any]) -> str:
    latest = scorecard.get("latest") if isinstance(scorecard.get("latest"), dict) else None
    compare = scorecard.get("compare_delta") if isinstance(scorecard.get("compare_delta"), dict) else None
    trends = scorecard.get("trends") if isinstance(scorecard.get("trends"), dict) else {}

    lines: list[str] = [
        "# Demo Day Scorecard",
        "",
        f"- generated_at: {scorecard.get('generated_at', '')}",
        f"- runs_root: `{scorecard.get('runs_root', '')}`",
        f"- overall_status: `{scorecard.get('status', 'unknown')}`",
        "",
    ]

    if latest:
        totals = latest.get("totals", {})
        validation = latest.get("validation", {})
        lines.extend(
            [
                "## Latest Run",
                f"- run_id: `{latest.get('run_id', '')}`",
                f"- status: `{latest.get('status', 'unknown')}`",
                f"- profile/model: `{latest.get('profile', '')}` / `{latest.get('model', '')}`",
                f"- completed_at: {latest.get('completed_at', '') or '-'}",
                (
                    "- task totals: "
                    f"attempts={totals.get('total_task_attempts', 0)}, "
                    f"hard_failures={totals.get('hard_failures', 0)}, "
                    f"soft_failures={totals.get('soft_failures', 0)}"
                ),
                (
                    "- validators: "
                    f"passed={validation.get('passed', 0)}, "
                    f"failed={validation.get('failed', 0)}, "
                    f"soft_fail={validation.get('soft_fail', 0)}, "
                    f"blocking_failed={validation.get('blocking_failed', 0)}"
                ),
            ]
        )

        blockers = latest.get("blockers") if isinstance(latest.get("blockers"), list) else []
        failed_validators = latest.get("failed_validators") if isinstance(latest.get("failed_validators"), list) else []

        lines.append(f"- blockers: {', '.join(str(b) for b in blockers) if blockers else 'none'}")
        lines.append(
            "- failed_validators: "
            f"{', '.join(str(v) for v in failed_validators) if failed_validators else 'none'}"
        )
        lines.append("")

    if compare:
        totals = compare.get("totals", {})
        validation = compare.get("validation", {})
        blockers = compare.get("blockers", {})
        status_change = compare.get("status", {})
        lines.extend(
            [
                "## Compare Delta (previous → latest)",
                f"- from `{compare.get('from_run_id', '')}` to `{compare.get('to_run_id', '')}`",
                f"- status: `{status_change.get('from', 'unknown')}` → `{status_change.get('to', 'unknown')}`",
                (
                    "- totals delta: "
                    f"attempts={_format_int_delta(_safe_int(totals.get('total_task_attempts'), 0))}, "
                    f"hard_failures={_format_int_delta(_safe_int(totals.get('hard_failures'), 0))}, "
                    f"soft_failures={_format_int_delta(_safe_int(totals.get('soft_failures'), 0))}"
                ),
                (
                    "- validator delta: "
                    f"passed={_format_int_delta(_safe_int(validation.get('passed'), 0))}, "
                    f"failed={_format_int_delta(_safe_int(validation.get('failed'), 0))}, "
                    "blocking_failed="
                    f"{_format_int_delta(_safe_int(validation.get('blocking_failed'), 0))}"
                ),
                (
                    "- blockers delta: "
                    f"count={_format_int_delta(_safe_int(blockers.get('count'), 0))}, "
                    f"added={', '.join(blockers.get('added', [])) or 'none'}, "
                    f"resolved={', '.join(blockers.get('resolved', [])) or 'none'}"
                ),
                (
                    "- validator changes: "
                    f"new_failed={', '.join(validation.get('new_failed_validators', [])) or 'none'}, "
                    f"resolved_failed={', '.join(validation.get('resolved_failed_validators', [])) or 'none'}"
                ),
                "",
            ]
        )

    status_counts = trends.get("status_counts") if isinstance(trends.get("status_counts"), dict) else {}
    lines.extend(
        [
            "## Trends Snapshot",
            f"- runs analyzed: {trends.get('run_count', 0)}",
            f"- pass_rate: {_format_pct(float(trends.get('pass_rate_percent', 0.0)))}",
            (
                "- status_counts: "
                f"ok={status_counts.get('ok', 0)}, "
                f"failed={status_counts.get('failed', 0)}, "
                f"running={status_counts.get('running', 0)}, "
                f"unknown={status_counts.get('unknown', 0)}"
            ),
            (
                "- avg_failures_per_run: "
                f"hard={trends.get('avg_hard_failures', 0)}, "
                f"soft={trends.get('avg_soft_failures', 0)}"
            ),
        ]
    )

    top_failed = trends.get("top_failed_validators") if isinstance(trends.get("top_failed_validators"), list) else []
    if top_failed:
        lines.append("- top_failed_validators:")
        for row in top_failed:
            if isinstance(row, dict):
                lines.append(f"  - {row.get('name', 'unknown')}: {row.get('count', 0)}")
    else:
        lines.append("- top_failed_validators: none")

    top_blockers = trends.get("top_blockers") if isinstance(trends.get("top_blockers"), list) else []
    if top_blockers:
        lines.append("- top_blockers:")
        for row in top_blockers:
            if isinstance(row, dict):
                lines.append(f"  - {row.get('name', 'unknown')}: {row.get('count', 0)}")
    else:
        lines.append("- top_blockers: none")

    lines.append("")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate local demo-day scorecard from recent runs")
    parser.add_argument("--runs-root", default="generated_runs", help="run directory root (default: generated_runs)")
    parser.add_argument("--output-dir", default="artifacts/demo-day", help="output directory (default: artifacts/demo-day)")
    parser.add_argument("--latest", type=int, default=5, help="number of most recent runs to analyze (default: 5)")
    parser.add_argument(
        "--run-ids",
        default="",
        help="optional comma-separated run IDs to include (still sorted by mtime)",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    runs_root = Path(args.runs_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    run_ids = [rid.strip() for rid in str(args.run_ids).split(",") if rid.strip()]
    scorecard = build_scorecard(runs_root, latest=max(args.latest, 0), run_ids=run_ids or None)

    json_path = output_dir / "demo_scorecard_latest.json"
    md_path = output_dir / "demo_scorecard_latest.md"

    json_path.write_text(json.dumps(scorecard, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(scorecard), encoding="utf-8")

    print(f"[demo-scorecard] wrote: {json_path}")
    print(f"[demo-scorecard] wrote: {md_path}")


if __name__ == "__main__":
    main()
