# Autonomous retry strategy semantics v2 (AV5-004)

Status: Drafted for AV5 kickoff  
Canonical schema: `docs/ops/autonomous_retry_strategy_v2.schema.json`  
Canonical example: `docs/ops/autonomous_retry_strategy_v2.example.json`

This document defines deterministic replay policy semantics for AV5.
It standardizes when a stage should `retry`, `stop`, or `escalate` based on retry class and explicit thresholds.

## Retry classes

### `retryable`

- Used for transient/fixable failures where bounded replay is expected.
- Default lane: `retry` while within budget.
- Stop threshold: `stop_after_failures`.
- Escalate threshold: `escalate_after_no_progress`.

### `conditional`

- Used when replay is allowed only if evidence indicates progress potential.
- Default lane: `retry` only when class thresholds remain safe.
- Stop/escalate thresholds are tighter than `retryable` to avoid churn.

### `non_retryable`

- Used when replay should not proceed automatically.
- Default lane: `escalate` (manual intervention required).
- Non-retryable hard failures always force `stop` first for safety.

## Deterministic decision order

For each replay attempt, evaluate in this order:

1. If `non_retryable_failure=true` and class enables hard-stop → **`stop`**
2. If class is `non_retryable` → **`escalate`**
3. If `replay_attempt > retry_budget` → **`escalate`**
4. If `no_progress_streak >= escalate_after_no_progress` → **`escalate`**
5. If `consecutive_failures >= stop_after_failures` → **`stop`**
6. Otherwise → **`retry`**

This ordering keeps decisions replayable and deterministic for the same input tuple.

## Reason-code mapping

- `autonomous_guard.repeated_gate_failure_limit_reached` → stop threshold breached via repeated failures
- `autonomous_guard.no_measurable_gate_improvement_limit_reached` → no-progress stop guard in runtime evidence
- `retry_policy.no_progress_escalation` → policy-level escalate due to no-progress streak
- `retry_policy.retry_budget_exhausted` → policy-level escalate due to replay budget
- `retry_policy.non_retryable_failure` → hard stop because failure class is non-retryable
- `retry_policy.non_retryable_class` → escalate because class disallows replay
- `retry_policy.retryable_within_budget` → retry allowed

## Deterministic examples

Canonical scenarios live in `docs/ops/autonomous_retry_strategy_v2.example.json`.
Each scenario includes:

- stage + retry class
- replay counters (`replay_attempt`, `consecutive_failures`, `no_progress_streak`)
- failure hard-stop signal
- expected decision + reason code

## Validation gates

- Policy schema + examples validation: `python scripts/check_retry_strategy_v2.py`
- Replay smoke scenario: `python scripts/retry_strategy_replay_smoke.py`
- Docs lane: `make check-docs`
