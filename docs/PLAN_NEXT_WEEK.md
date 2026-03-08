# PLAN — Next Wave (AV3 Candidates)

## Scope

This plan reflects `main` after AV2 closure and marks the autonomous v2 wave (`AV2-001` ~ `AV2-014`) as complete and merged.
Primary objective now shifts to AV3 candidate execution with a reliability-first rollout.

## AV2 baseline (already merged)

- AV2-001: Quality-gate policy loader
- AV2-002: Quality-gate evaluation engine
- AV2-003: Gate signal normalization taxonomy
- AV2-004: Gate baseline trend persistence
- AV2-005: Auto-fix strategy routing
- AV2-006: Autonomous summary surfacing
- AV2-007: Stop/rollback decision guard
- AV2-008: Resume/restart reliability hardening
- AV2-009: Preflight safety gate
- AV2-010: Budget guard diagnostics
- AV2-011: Operator playbook guidance linking
- AV2-012: Latest quality-gate snapshot API
- AV2-013: Deterministic autonomous E2E smoke lane
- AV2-014: Release evidence checklist guardrails

## AV2 closure status

- Wave: `AV2-001` → `AV2-014`
- Completion: ✅ **14/14 done**
- Source of truth: PR merges **#32 through #45**
- Closure summary: `docs/AUTONOMOUS_V2_WAVE_CLOSURE.md`

## AV3 prioritized stack (proposed)

1. **AV3-001 (P0)** — CI-enforced autonomous release evidence gate
2. **AV3-002 (P0)** — Autonomous observability stream (state/attempt timeline UI parity)
3. **AV3-003 (P1)** — Operator pause/resume/cancel control surface
4. **AV3-004 (P1)** — External side-effect policy hardening + audit trail

Detailed acceptance criteria and split guidance live in `docs/BACKLOG_NEXT_WEEK.md`.

## Workflow confidence checks

- Keep `make smoke-autonomous-e2e` as deterministic gate smoke.
- Keep `make check-release-autonomous` in release-readiness flow.
- Keep `make check-docs` mandatory for docs/process updates.

## Definition of done (planning/workflow)

- AV2 closure is clearly recorded across status/plan/backlog docs.
- AV3 candidates include priority, owner role, effort, and acceptance criteria.
- README/docs navigation includes AV2 closure summary entry.
- Docs validation remains green (`make check-docs`).

## Related docs

- `docs/BACKLOG_NEXT_WEEK.md`
- `docs/AUTONOMOUS_V2_WAVE_CLOSURE.md`
- `docs/AUTONOMOUS_MODE.md`
- `docs/ops/AUTONOMOUS_V2_RELEASE_CHECKLIST.md`
- `docs/AUTONOMOUS_FAILURE_PLAYBOOK.md`
