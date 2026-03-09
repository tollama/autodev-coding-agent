#!/usr/bin/env python3
"""Validate AV6 autoresearch hard-blocker policy contract schema + canonical example."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


EXPECTED_POLICY_ID = "autonomous.autoresearch-hard-blocker.v1"
EXPECTED_SEVERITY = {"high", "critical"}
EXPECTED_DECISIONS = {"stop", "escalate"}


@dataclass(frozen=True)
class ValidationError:
    message: str


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _validate_schema(schema: Any) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not isinstance(schema, dict):
        return [ValidationError("schema root must be a JSON object")]

    required_top = {"$schema", "$id", "title", "type", "required", "properties", "$defs"}
    missing = sorted(required_top - set(schema.keys()))
    if missing:
        errors.append(ValidationError(f"schema missing top-level keys: {missing}"))

    policy_id_const = schema.get("properties", {}).get("policy_id", {}).get("const")
    if policy_id_const != EXPECTED_POLICY_ID:
        errors.append(ValidationError(f"schema.properties.policy_id.const must be {EXPECTED_POLICY_ID}"))

    severity_enum = schema.get("$defs", {}).get("severity", {}).get("enum", [])
    if set(severity_enum) != EXPECTED_SEVERITY:
        errors.append(ValidationError(f"schema severity enum must be {sorted(EXPECTED_SEVERITY)}"))

    decision_enum = schema.get("$defs", {}).get("decisionLane", {}).get("enum", [])
    if set(decision_enum) != EXPECTED_DECISIONS:
        errors.append(ValidationError(f"schema decisionLane enum must be {sorted(EXPECTED_DECISIONS)}"))

    return errors


def _validate_example(example: Any) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not isinstance(example, dict):
        return [ValidationError("example root must be a JSON object")]

    if example.get("policy_id") != EXPECTED_POLICY_ID:
        errors.append(ValidationError(f"example policy_id must be {EXPECTED_POLICY_ID}"))

    severity_levels = example.get("severity_levels")
    if set(severity_levels or []) != EXPECTED_SEVERITY:
        errors.append(ValidationError(f"example severity_levels must be {sorted(EXPECTED_SEVERITY)}"))

    blocker_classes = example.get("blocker_classes")
    if not isinstance(blocker_classes, list) or len(blocker_classes) < 4:
        errors.append(ValidationError("example must define at least 4 blocker_classes"))
        blocker_classes = []

    decisions_seen: set[str] = set()
    class_ids: set[str] = set()
    for item in blocker_classes:
        if not isinstance(item, dict):
            errors.append(ValidationError("each blocker class must be an object"))
            continue
        class_id = item.get("id")
        if isinstance(class_id, str):
            class_ids.add(class_id)
        severity = item.get("severity")
        if severity not in EXPECTED_SEVERITY:
            errors.append(ValidationError(f"invalid blocker severity for {class_id}: {severity}"))
        decision = item.get("mandatory_lane")
        if decision not in EXPECTED_DECISIONS:
            errors.append(ValidationError(f"invalid mandatory_lane for {class_id}: {decision}"))
        else:
            decisions_seen.add(decision)

    canonical_examples = example.get("canonical_examples")
    if not isinstance(canonical_examples, list) or len(canonical_examples) < 4:
        errors.append(ValidationError("example must define at least 4 canonical_examples"))
        canonical_examples = []

    for item in canonical_examples:
        if not isinstance(item, dict):
            errors.append(ValidationError("each canonical example must be an object"))
            continue
        blocker_class = item.get("blocker_class")
        decision = item.get("expected_decision")
        if blocker_class not in class_ids:
            errors.append(ValidationError(f"canonical example references unknown blocker_class: {blocker_class}"))
        if decision not in EXPECTED_DECISIONS:
            errors.append(ValidationError(f"canonical example decision must be one of {sorted(EXPECTED_DECISIONS)}"))

    if decisions_seen != EXPECTED_DECISIONS:
        errors.append(ValidationError("blocker classes must include both mandatory lanes: stop and escalate"))

    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate autoresearch hard-blocker policy schema/example")
    ap.add_argument(
        "--schema",
        default="docs/ops/autonomous_autoresearch_blocker_policy_v1.schema.json",
        help="Path to hard-blocker policy schema",
    )
    ap.add_argument(
        "--example",
        default="docs/ops/autonomous_autoresearch_blocker_policy_v1.example.json",
        help="Path to hard-blocker policy example",
    )
    args = ap.parse_args()

    schema_path = Path(args.schema)
    example_path = Path(args.example)

    missing = [str(p) for p in (schema_path, example_path) if not p.exists()]
    if missing:
        print(f"[FAIL] missing file(s): {', '.join(missing)}")
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
        print("[FAIL] autoresearch hard-blocker policy check failed")
        for err in errors:
            print(f"  - {err.message}")
        return 1

    print("[PASS] autoresearch hard-blocker policy schema/example validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
