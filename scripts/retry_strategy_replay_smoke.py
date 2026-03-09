#!/usr/bin/env python3
"""AV5-004 replay smoke scenario for deterministic retry policy decisions."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _evaluate_decision(example: dict[str, Any], klass: dict[str, Any]) -> tuple[str, str]:
    if bool(example.get("non_retryable_failure")) and bool(klass.get("hard_stop_on_non_retryable_failure")):
        return "stop", "retry_policy.non_retryable_failure"

    class_name = str(klass.get("name") or "")
    if class_name == "non_retryable":
        return "escalate", "retry_policy.non_retryable_class"

    replay_attempt = int(example.get("replay_attempt") or 0)
    retry_budget = int(klass.get("retry_budget") or 0)
    if replay_attempt > retry_budget:
        return "escalate", "retry_policy.retry_budget_exhausted"

    no_progress_streak = int(example.get("no_progress_streak") or 0)
    escalate_after = int(klass.get("escalate_after_no_progress") or 0)
    if no_progress_streak >= escalate_after:
        return "escalate", "retry_policy.no_progress_escalation"

    consecutive_failures = int(example.get("consecutive_failures") or 0)
    stop_after = int(klass.get("stop_after_failures") or 0)
    if consecutive_failures >= stop_after:
        return "stop", "autonomous_guard.repeated_gate_failure_limit_reached"

    return "retry", "retry_policy.retryable_within_budget"


def run_smoke(*, example_path: Path, artifacts_dir: Path) -> Path:
    payload = json.loads(example_path.read_text(encoding="utf-8"))
    retry_classes = payload.get("retry_classes") if isinstance(payload.get("retry_classes"), list) else []
    examples = payload.get("deterministic_examples") if isinstance(payload.get("deterministic_examples"), list) else []

    class_map = {
        str(item.get("name")): item
        for item in retry_classes
        if isinstance(item, dict) and item.get("name")
    }

    checks: list[dict[str, Any]] = []
    for row in examples:
        if not isinstance(row, dict):
            continue
        ex_id = str(row.get("id") or "<missing>")
        class_name = str(row.get("retry_class") or "")
        klass = class_map.get(class_name)
        if not isinstance(klass, dict):
            raise RuntimeError(f"missing class for example {ex_id}: {class_name}")

        got_decision, got_reason = _evaluate_decision(row, klass)
        expected_decision = str(row.get("expected_decision") or "")
        expected_reason = str(row.get("expected_reason_code") or "")
        ok = got_decision == expected_decision and got_reason == expected_reason
        checks.append(
            {
                "id": ex_id,
                "retry_class": class_name,
                "expected": {"decision": expected_decision, "reason_code": expected_reason},
                "actual": {"decision": got_decision, "reason_code": got_reason},
                "ok": ok,
            }
        )

    failed = [c for c in checks if not c.get("ok")]
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    out_dir = artifacts_dir / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "schema_version": "av5-004-replay-smoke-v1",
        "generated_at": _utc_now(),
        "policy_id": payload.get("policy_id"),
        "ok": len(failed) == 0,
        "total": len(checks),
        "failed": len(failed),
    }
    (out_dir / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "checks.json").write_text(json.dumps(checks, indent=2, ensure_ascii=False), encoding="utf-8")

    if failed:
        ids = ", ".join(str(item.get("id")) for item in failed)
        raise RuntimeError(f"deterministic replay mismatches: {ids}")

    return out_dir


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="AV5-004 replay smoke for retry strategy semantics v2")
    ap.add_argument(
        "--example",
        default="docs/ops/autonomous_retry_strategy_v2.example.json",
        help="path to retry strategy v2 canonical example JSON",
    )
    ap.add_argument(
        "--artifacts-dir",
        default="artifacts/retry-strategy-replay-smoke",
        help="directory to persist smoke result/check snapshots",
    )
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    example_path = Path(args.example)
    artifacts_dir = Path(args.artifacts_dir)

    if not example_path.exists():
        print(f"[AV5-004 replay smoke] FAIL: missing example file {example_path}")
        return 1

    try:
        out_dir = run_smoke(example_path=example_path, artifacts_dir=artifacts_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"[AV5-004 replay smoke] FAIL: {exc}")
        print(f"[AV5-004 replay smoke] Artifacts root: {artifacts_dir}")
        return 1

    print("[AV5-004 replay smoke] PASS")
    print(f"[AV5-004 replay smoke] Artifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
