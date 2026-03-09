#!/usr/bin/env python3
"""Validate AV5 retry strategy semantics v2 schema + canonical examples."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXPECTED_RETRY_CLASSES = ["retryable", "conditional", "non_retryable"]
EXPECTED_DECISIONS = {"retry", "stop", "escalate"}
VERSION_RE = re.compile(r"^v\d+$")


@dataclass
class ValidationError:
    message: str


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _validate_schema(schema: Any) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not isinstance(schema, dict):
        return [ValidationError("schema root must be a JSON object")]

    required_top_keys = {"$schema", "$id", "title", "type", "required", "properties", "$defs"}
    missing = sorted(required_top_keys - set(schema.keys()))
    if missing:
        errors.append(ValidationError(f"schema missing top-level keys: {missing}"))

    policy_id_const = (
        schema.get("properties", {})
        .get("policy_id", {})
        .get("const")
    )
    if policy_id_const != "autonomous.retry-strategy.v2":
        errors.append(ValidationError("schema.properties.policy_id.const must be autonomous.retry-strategy.v2"))

    class_enum = (
        schema.get("$defs", {})
        .get("retryClass", {})
        .get("properties", {})
        .get("name", {})
        .get("enum", [])
    )
    if class_enum != EXPECTED_RETRY_CLASSES:
        errors.append(ValidationError(f"schema retry class enum must be {EXPECTED_RETRY_CLASSES}"))

    decision_enum = (
        schema.get("$defs", {})
        .get("deterministicExample", {})
        .get("properties", {})
        .get("expected_decision", {})
        .get("enum", [])
    )
    if set(decision_enum) != EXPECTED_DECISIONS:
        errors.append(ValidationError(f"schema expected_decision enum must be {sorted(EXPECTED_DECISIONS)}"))

    return errors


def _validate_example(example: Any) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not isinstance(example, dict):
        return [ValidationError("example root must be a JSON object")]

    if example.get("policy_id") != "autonomous.retry-strategy.v2":
        errors.append(ValidationError("example.policy_id must be autonomous.retry-strategy.v2"))

    version = example.get("version")
    if not isinstance(version, str) or not VERSION_RE.match(version):
        errors.append(ValidationError("example.version must match ^v\\d+$"))

    retry_classes = example.get("retry_classes")
    if not isinstance(retry_classes, list) or len(retry_classes) != 3:
        return errors + [ValidationError("example.retry_classes must include exactly 3 class entries")]

    class_map: dict[str, dict[str, Any]] = {}
    for row in retry_classes:
        if not isinstance(row, dict):
            errors.append(ValidationError("each retry_classes entry must be an object"))
            continue

        name = str(row.get("name") or "")
        if name not in EXPECTED_RETRY_CLASSES:
            errors.append(ValidationError(f"invalid retry class name: {name!r}"))
            continue
        class_map[name] = row

        retry_budget = row.get("retry_budget")
        stop_after = row.get("stop_after_failures")
        escalate_after = row.get("escalate_after_no_progress")
        if not isinstance(retry_budget, int) or retry_budget < 0:
            errors.append(ValidationError(f"class[{name}].retry_budget must be an integer >= 0"))
        if not isinstance(stop_after, int) or stop_after < 1:
            errors.append(ValidationError(f"class[{name}].stop_after_failures must be an integer >= 1"))
        if not isinstance(escalate_after, int) or escalate_after < 1:
            errors.append(ValidationError(f"class[{name}].escalate_after_no_progress must be an integer >= 1"))
        if isinstance(retry_budget, int) and isinstance(stop_after, int) and retry_budget > stop_after:
            errors.append(
                ValidationError(
                    f"class[{name}] retry_budget ({retry_budget}) must be <= stop_after_failures ({stop_after})"
                )
            )

    if sorted(class_map.keys()) != sorted(EXPECTED_RETRY_CLASSES):
        errors.append(ValidationError(f"example.retry_classes must include {EXPECTED_RETRY_CLASSES}"))

    examples = example.get("deterministic_examples")
    if not isinstance(examples, list) or not examples:
        return errors + [ValidationError("example.deterministic_examples must be a non-empty array")]

    for idx, row in enumerate(examples, start=1):
        if not isinstance(row, dict):
            errors.append(ValidationError(f"deterministic_examples[{idx}] must be an object"))
            continue
        ex_id = str(row.get("id") or f"#{idx}")
        class_name = str(row.get("retry_class") or "")
        if class_name not in class_map:
            errors.append(ValidationError(f"example[{ex_id}] has unknown retry_class {class_name!r}"))
            continue

        expected_decision = row.get("expected_decision")
        expected_reason = row.get("expected_reason_code")
        if expected_decision not in EXPECTED_DECISIONS:
            errors.append(ValidationError(f"example[{ex_id}] expected_decision must be one of {sorted(EXPECTED_DECISIONS)}"))
            continue
        if not isinstance(expected_reason, str) or not expected_reason.strip():
            errors.append(ValidationError(f"example[{ex_id}] expected_reason_code must be a non-empty string"))
            continue

        computed_decision, computed_reason = _evaluate_decision(row, class_map[class_name])
        if computed_decision != expected_decision or computed_reason != expected_reason:
            errors.append(
                ValidationError(
                    "example[{id}] deterministic mismatch: expected ({ed}, {er}) got ({cd}, {cr})".format(
                        id=ex_id,
                        ed=expected_decision,
                        er=expected_reason,
                        cd=computed_decision,
                        cr=computed_reason,
                    )
                )
            )

    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate autonomous retry strategy v2 schema/example")
    ap.add_argument(
        "--schema",
        default="docs/ops/autonomous_retry_strategy_v2.schema.json",
        help="Path to retry strategy v2 JSON schema",
    )
    ap.add_argument(
        "--example",
        default="docs/ops/autonomous_retry_strategy_v2.example.json",
        help="Path to canonical retry strategy v2 example",
    )
    args = ap.parse_args()

    schema_path = Path(args.schema)
    example_path = Path(args.example)

    missing = [str(p) for p in (schema_path, example_path) if not p.exists()]
    if missing:
        print("[FAIL] missing required file(s):")
        for path in missing:
            print(f"  - {path}")
        return 1

    try:
        schema = _load_json(schema_path)
    except json.JSONDecodeError as exc:
        print(f"[FAIL] invalid JSON in schema file {schema_path}: {exc}")
        return 1

    try:
        example = _load_json(example_path)
    except json.JSONDecodeError as exc:
        print(f"[FAIL] invalid JSON in example file {example_path}: {exc}")
        return 1

    errors = _validate_schema(schema)
    errors.extend(_validate_example(example))

    if errors:
        print("[FAIL] retry strategy v2 validation failed")
        for err in errors:
            print(f"  - {err.message}")
        return 1

    print("[PASS] retry strategy v2 schema/example validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
