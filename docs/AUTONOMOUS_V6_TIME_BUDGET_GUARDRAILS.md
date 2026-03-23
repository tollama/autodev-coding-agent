# AUTONOMOUS V6 — Time-Budget Guardrails (AV6-003)

Status: ✅ Drafted for merge (docs-first guardrail slice)
Owner: @autonomous-docs
Last updated: 2026-03-23 (Asia/Seoul)

## Purpose

Define the minimal AV6 time-budget guardrail contract by aligning the existing autonomous runtime budget implementation with AV6 policy language.

This slice is intentionally narrow:
- **documents what is already enforced today**,
- **standardizes the operator-facing reason codes and overrun actions**, and
- **records stage-budget semantics as a policy envelope / evidence contract** until per-stage runtime enforcement is added in a later slice.

## Current runtime-aligned guardrails

The current autonomous runtime already enforces these global budget controls:

1. **Run wall-clock budget**
   - Source of truth: `run.autonomous.time_budget_sec` or CLI `--time-budget-sec`
   - Runtime behavior: stop before the next autonomous iteration when elapsed wall-clock time reaches the configured limit
   - Typed reason code: `autonomous_budget_guard.max_wall_clock_seconds_exceeded`

2. **Autonomous iteration budget**
   - Source of truth: `run.autonomous.max_iterations` or CLI `--max-iterations`
   - Runtime behavior: stop when the configured autonomous iteration ceiling is reached
   - Typed reason code: `autonomous_budget_guard.max_autonomous_iterations_reached`

3. **Estimated token budget diagnostic (advisory only)**
   - Source of truth: `run.autonomous.budget_guard_policy.max_estimated_token_budget` or CLI `--max-estimated-token-budget`
   - Runtime behavior: persisted as a diagnostic only; no hard stop is enforced because a reliable token estimate is not yet available
   - Typed reason code: `autonomous_budget_guard.estimated_token_budget_not_available`

## Policy contract

### A. Global run budget (enforced now)

| Budget scope | Default | Override | Overrun action | Evidence field(s) |
|---|---|---|---|---|
| Run wall-clock | `3600s` | `run.autonomous.time_budget_sec`, `--time-budget-sec` | `stop` | `budget_guard.checks.wall_clock.*`, `budget_guard.decision.reason_code` |
| Autonomous iterations | `3` | `run.autonomous.max_iterations`, `--max-iterations` | `stop` | `budget_guard.checks.iterations.*`, `budget_guard.decision.reason_code` |
| Estimated token budget | unset | `run.autonomous.budget_guard_policy.max_estimated_token_budget`, `--max-estimated-token-budget` | `diagnostic_only` | `budget_guard.checks.estimated_tokens.*`, `budget_guard.diagnostics[]` |

### B. Stage budget envelope (policy now, enforcement later)

AV6 requires a **stage-aware budget contract**, but the current runtime does **not** yet enforce per-stage timers as independent hard stops.

For this minimal slice, the stage policy is:

| Stage | Policy expectation | Current enforcement posture | Required operator behavior on apparent overrun |
|---|---|---|---|
| `preflight` | must finish inside the global run budget | inherits global run budget only | stop and inspect preflight blockers; do not simply extend budget blindly |
| `execute` | retries/fixes must remain bounded by run budget + iteration budget | inherits global run budget and iteration budget | re-scope work if repeated retries consume budget without measurable improvement |
| `report` / artifact finalization | must not continue after a triggered budget stop except for deterministic artifact persistence | partially aligned via existing final artifact write path | preserve guard decision and operator guidance; avoid additional autonomous work |

### Stage-budget semantics for future enforcement

When per-stage runtime enforcement is implemented, it must remain backward-compatible with the current AV6 slice:

- stage budget decisions should map to event family `guard.budget.decision`
- `budget_scope` must be `stage` for stage overruns and `run` for global overruns
- canonical reason examples remain:
  - `stage_budget_exceeded`
  - `run_budget_exceeded`
  - `budget_metadata_missing`
- stage overrun actions should be deterministic:
  - `preflight` → `stop`
  - `execute` → `escalate` or `stop` depending on retry state
  - `report` → `stop` after best-effort evidence persistence

## Timeout / error contract

### Required stop behavior

When a global budget is exceeded, autonomous mode must:

1. persist `failure_reason`
2. persist `budget_guard.status = triggered`
3. persist a typed `budget_guard.decision.reason_code`
4. expose the same decision in the final report/summary surfaces
5. halt further autonomous iteration work

### Canonical runtime-aligned mappings

| Condition | failure_reason | decision | reason_code |
|---|---|---|---|
| Wall-clock budget exceeded before next iteration | `time_budget_exceeded` | `stop` | `autonomous_budget_guard.max_wall_clock_seconds_exceeded` |
| Max autonomous iterations reached | `max_iterations_exceeded` | `stop` | `autonomous_budget_guard.max_autonomous_iterations_reached` |
| Token budget configured but not enforceable | _no terminal failure by itself_ | `diagnostic_only` | `autonomous_budget_guard.estimated_token_budget_not_available` |

## Operator guidance

Operators should treat budget guard decisions as **scope-control signals**, not as automatic permission to raise limits.

Recommended response order:

1. **Re-scope first** — reduce task breadth or split the run.
2. **Inspect retry waste** — confirm whether repeated gate failures consumed the budget.
3. **Increase limits only deliberately** — explicit approval should be required before extending wall-clock budgets for the same scope.
4. **Preserve evidence** — report/summary artifacts should remain the primary debugging surface.

## Evidence surfaces

This AV6 slice aligns with the existing runtime artifacts:

- `.autodev/autonomous_state.json`
- `.autodev/autonomous_report.json`
- `.autodev/run_metadata.json`
- `AUTONOMOUS_REPORT.md`
- `autodev autonomous summary --run-dir ...`

Minimum evidence expected after a triggered budget stop:

- `budget_guard.status`
- `budget_guard.decision.reason_code`
- `budget_guard.checks.wall_clock` and/or `budget_guard.checks.iterations`
- matching budget-guard payload in final report surfaces

## Validation / evidence plan

Docs-first validation for this slice:

- `make check-docs`
- `pytest autodev/tests/test_autonomous_mode.py -k budget_guard`
- policy dry-run walkthrough against `docs/AUTONOMOUS_MODE.md` and AV6 planning docs

## Related docs

- `docs/AUTONOMOUS_V6_BACKLOG.md`
- `docs/AUTONOMOUS_V6_WAVE_PLAN.md`
- `docs/AUTONOMOUS_V6_WAVE_CHECKPOINT.md`
- `docs/AUTONOMOUS_MODE.md`
- `docs/AUTONOMOUS_FAILURE_PLAYBOOK.md`
- `docs/AUTONOMOUS_V6_GUARD_OBSERVABILITY_BASELINE.md`
