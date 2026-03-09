# AUTONOMOUS V6 — Wave Plan (Kickoff)

Status: 🚧 Kickoff started (2026-03-09)

## Goals / outcomes

1. **Safe autoresearch operationalization:** convert existing autoresearch integration into explicitly bounded policy controls before wider rollout.
2. **Deterministic quality decisions:** define hard scoring thresholds and blocker semantics so pass/retry/escalate behavior is reproducible.
3. **Bounded execution cost:** enforce per-run and per-stage time budgets to prevent runaway autonomous loops.
4. **Operator-grade observability:** expose enough telemetry/evidence to debug guard decisions without deep log forensics.

## 2-week milestone slices

### Week 1 (Days 1-7): guardrails-first baseline
- Publish AV6 kickoff packet and status-hook alignment.
- Lock hard blocker contract for autoresearch-triggered actions.
- Define scoring threshold matrix and decision semantics.
- Draft time-budget envelope (global + stage-level) with fail-fast policy.

### Week 2 (Days 8-14): verification + operator visibility
- Add observability/event schema for blocker and threshold decisions.
- Index kickoff evidence for reproducible checks.
- Run smoke/drift checks and close initial AV6 kickoff tickets in small PR slices.

## Architecture deltas from AV5

- **Policy posture:** AV5 documented carryover/governance; AV6 adds enforceable blocker thresholds for autoresearch execution paths.
- **Decision engine expectations:** AV6 formalizes score thresholds into explicit gate semantics (pass/retry/escalate/stop).
- **Runtime controls:** AV6 introduces concrete wall-clock budgets and timeout contracts tied to stage boundaries.
- **Evidence discipline:** AV6 prioritizes observable decision traces and compact operator-facing diagnostics.

## Top risks + mitigations

1. **Risk:** Over-strict blockers cause unnecessary run halts.
   - **Mitigation:** staged threshold defaults, rationale fields, and replayable policy examples.
2. **Risk:** Time budgets hide slow degradation until late failure.
   - **Mitigation:** budget preflight checks + stage-level overrun telemetry with deterministic stop reasons.
3. **Risk:** Observability additions increase artifact noise.
   - **Mitigation:** canonical event taxonomy and minimal required fields for operator triage.
4. **Risk:** Kickoff scope expands beyond docs-first boundaries.
   - **Mitigation:** strict small-ticket backlog with one-PR-per-ticket policy.

## Related docs

- `docs/AUTONOMOUS_V6_BACKLOG.md`
- `docs/AUTONOMOUS_V6_WAVE_CHECKPOINT.md`
- `docs/AUTONOMOUS_V5_WAVE_PLAN.md`
- `docs/AUTONOMOUS_V5_BACKLOG.md`
- `docs/AUTONOMOUS_V5_CARRYOVER_POLICY.md`
- `docs/PLAN_NEXT_WEEK.md`
- `docs/BACKLOG_NEXT_WEEK.md`
- `docs/STATUS_BOARD_CURRENT.md`
- `docs/STATUS_HOOK_TRANSITION_MATRIX.md`
