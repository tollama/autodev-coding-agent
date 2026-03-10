# AUTONOMOUS V6 — Observability Baseline for Guard Decisions (AV6-004)

Status: ✅ Drafted for merge (docs-first observability baseline)
Owner: @autonomous-docs
Last updated: 2026-03-10 (Asia/Seoul)
Canonical schema: `docs/ops/autonomous_guard_observability_v1.schema.json`
Canonical example: `docs/ops/autonomous_guard_observability_v1.example.json`

## Purpose

Define a canonical telemetry/evidence contract for AV6 guard decisions so blocker, threshold, and budget outcomes are inspectable without deep log forensics.

This baseline is backward-compatible and docs-first:
- no runtime behavior changes,
- only standardizes event/field shape,
- links evidence to existing operator surfaces (CLI/API/GUI/status artifacts).

## Canonical guard-decision events

Every guarded decision must emit exactly one of these event families:

| Event family | Trigger | Typical actions | Canonical reason examples |
|---|---|---|---|
| `guard.blocker.decision` | hard-blocker policy contract evaluated | `stop`, `escalate` | `policy_scope_violation`, `unapproved_external_side_effect`, `evidence_integrity_failure` |
| `guard.threshold.decision` | scoring-threshold matrix evaluated | `pass`, `retry`, `escalate`, `stop` | `score_band_pass`, `retry_budget_exhausted`, `score_unavailable`, `score_invalid` |
| `guard.budget.decision` | global/stage time-budget check evaluated | `retry`, `escalate`, `stop` | `stage_budget_exceeded`, `run_budget_exceeded`, `budget_metadata_missing` |

## Required telemetry fields (minimum)

All three event families above must include the following required fields:

- `event_id` (stable UUID-like identifier)
- `event_family` (`guard.blocker.decision|guard.threshold.decision|guard.budget.decision`)
- `run_id`
- `attempt_index`
- `stage`
- `decision_action` (`pass|retry|escalate|stop`)
- `decision_reason_code` (typed reason)
- `policy_refs` (policy ids/versions involved in this decision)
- `timestamp_utc` (RFC3339)
- `operator_surface_refs` (where operators can observe the decision)

### Event-family extensions

Additional required fields per family:

- **Blocker decision**
  - `hard_blocker` (`true` expected for blocker decisions)
  - `blocker_class`
  - `blocker_severity`

- **Threshold decision**
  - `quality_score_normalized`
  - `max_retries`

- **Budget decision**
  - `budget_scope` (`stage|run`)
  - `elapsed_ms`
  - `budget_limit_ms`

## Operator surface mapping

Each decision event must be linkable to at least one operator-facing surface:

| Surface | Link target | Required mapping behavior |
|---|---|---|
| CLI | `autodev autonomous summary` and `autodev autonomous triage-summary` | show `decision_action`, `decision_reason_code`, and `event_id`/policy refs for latest guard decision |
| API | `GET /api/autonomous/quality-gate/latest` (`summary` + warnings/details payload) | preserve canonical fields and include guard event references in machine-readable JSON |
| GUI | quality-gate panel/operator diagnostics | render latest guard decision + reason and expose source event identifier |
| Status artifacts | `docs/STATUS_BOARD_CURRENT.md`, wave/checkpoint docs, release notes drafts | include concise guard-observability status and references to canonical event contract |

## Evidence artifact envelope (canonical)

Use the schema contract in `docs/ops/autonomous_guard_observability_v1.schema.json`.

Minimum evidence envelope:

1. Contract metadata (`policy_id`, `version`)
2. Canonical event families list
3. Required telemetry fields list
4. Operator surface reference map
5. Canonical sample events for blocker/threshold/budget decisions

## Validation gates

- Evidence contract check: `python3 scripts/check_guard_observability_baseline.py`
- Docs lane: `make check-docs`

## Related docs

- `docs/AUTONOMOUS_V6_BACKLOG.md`
- `docs/AUTONOMOUS_V6_SCORING_THRESHOLD_MATRIX.md`
- `docs/AUTONOMOUS_AUTORESEARCH_BLOCKER_POLICY.md`
- `docs/AUTONOMOUS_OPERATOR_SUMMARY_PARITY_MAP.md`
- `docs/STATUS_BOARD_CURRENT.md`
