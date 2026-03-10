#!/usr/bin/env python3
"""Validate AV6 guard observability baseline schema + canonical example."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EXPECTED_POLICY_ID = "autonomous.guard-observability.v1"
EXPECTED_EVENT_FAMILIES = {
    "guard.blocker.decision",
    "guard.threshold.decision",
    "guard.budget.decision",
}
EXPECTED_TELEMETRY_FIELDS = {
    "event_id",
    "event_family",
    "run_id",
    "attempt_index",
    "stage",
    "decision_action",
    "decision_reason_code",
    "policy_refs",
    "timestamp_utc",
    "operator_surface_refs",
}
EXPECTED_SURFACES = {"cli", "api", "gui", "status_artifacts"}


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

    event_enum = set(
        schema.get("properties", {})
        .get("guard_event_families", {})
        .get("items", {})
        .get("enum", [])
    )
    if event_enum != EXPECTED_EVENT_FAMILIES:
        errors.append(ValidationError(f"schema guard_event_families enum must be {sorted(EXPECTED_EVENT_FAMILIES)}"))

    surface_enum = set(
        schema.get("$defs", {})
        .get("operatorSurface", {})
        .get("properties", {})
        .get("name", {})
        .get("enum", [])
    )
    if surface_enum != EXPECTED_SURFACES:
        errors.append(ValidationError(f"schema operator surfaces enum must be {sorted(EXPECTED_SURFACES)}"))

    return errors


def _validate_example(example: Any) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not isinstance(example, dict):
        return [ValidationError("example root must be a JSON object")]

    if example.get("policy_id") != EXPECTED_POLICY_ID:
        errors.append(ValidationError(f"example policy_id must be {EXPECTED_POLICY_ID}"))

    event_families = set(example.get("guard_event_families") or [])
    if event_families != EXPECTED_EVENT_FAMILIES:
        errors.append(ValidationError(f"example guard_event_families must be {sorted(EXPECTED_EVENT_FAMILIES)}"))

    telemetry_fields = set(example.get("required_telemetry_fields") or [])
    missing_telemetry = sorted(EXPECTED_TELEMETRY_FIELDS - telemetry_fields)
    if missing_telemetry:
        errors.append(ValidationError(f"example missing telemetry fields: {missing_telemetry}"))

    surfaces = example.get("operator_surfaces")
    if not isinstance(surfaces, list) or len(surfaces) < 4:
        errors.append(ValidationError("example must define at least 4 operator_surfaces"))
        surfaces = []

    seen_surfaces: set[str] = set()
    for surface in surfaces:
        if not isinstance(surface, dict):
            errors.append(ValidationError("each operator_surface must be an object"))
            continue
        name = surface.get("name")
        reference = surface.get("reference")
        if name not in EXPECTED_SURFACES:
            errors.append(ValidationError(f"invalid operator surface name: {name}"))
            continue
        seen_surfaces.add(name)
        if not isinstance(reference, str) or not reference.strip():
            errors.append(ValidationError(f"operator surface {name} missing reference"))

    if seen_surfaces != EXPECTED_SURFACES:
        errors.append(ValidationError(f"operator surfaces must include exactly {sorted(EXPECTED_SURFACES)}"))

    sample_events = example.get("sample_events")
    if not isinstance(sample_events, list) or len(sample_events) < 3:
        errors.append(ValidationError("example must define at least 3 sample_events"))
        sample_events = []

    sample_families: set[str] = set()
    for event in sample_events:
        if not isinstance(event, dict):
            errors.append(ValidationError("each sample event must be an object"))
            continue
        family = event.get("event_family")
        action = event.get("decision_action")
        if family not in EXPECTED_EVENT_FAMILIES:
            errors.append(ValidationError(f"sample event has invalid event_family: {family}"))
        else:
            sample_families.add(family)
        if action not in {"pass", "retry", "escalate", "stop"}:
            errors.append(ValidationError(f"sample event has invalid decision_action: {action}"))

    missing_families = sorted(EXPECTED_EVENT_FAMILIES - sample_families)
    if missing_families:
        errors.append(ValidationError(f"sample_events missing event families: {missing_families}"))

    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate AV6 guard observability baseline schema/example")
    ap.add_argument(
        "--schema",
        default="docs/ops/autonomous_guard_observability_v1.schema.json",
        help="Path to guard observability baseline schema",
    )
    ap.add_argument(
        "--example",
        default="docs/ops/autonomous_guard_observability_v1.example.json",
        help="Path to guard observability baseline example",
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
        print("[FAIL] guard observability baseline check failed")
        for err in errors:
            print(f"  - {err.message}")
        return 1

    print("[PASS] guard observability baseline schema/example validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
