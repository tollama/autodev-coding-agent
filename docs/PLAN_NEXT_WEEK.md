# PLAN — Next Wave (AV3 Kickoff)

## Scope

This plan reflects `main` after AV2 closure and marks AV3 kickoff as started.
Primary objective is to move from AV3 candidate listing to an execution-ready wave package with milestone slices and PR-splittable backlog.

## Current state snapshot

- AV2 wave (`AV2-001` ~ `AV2-014`) is complete and merged (PR `#32` → `#45`).
- AV3 kickoff docs are now published:
  - `docs/AUTONOMOUS_V3_WAVE_PLAN.md`
  - `docs/AUTONOMOUS_V3_BACKLOG.md`

## AV3 kickoff execution plan

1. **Milestone slicing (2 weeks):** week-1 foundation/enforcement, week-2 control-surface/policy hardening.
2. **Architecture transition:** AV2 snapshot-centric flow → AV3 timeline/control/policy model.
3. **Risk-managed rollout:** prioritized tickets with explicit PR split guidance.
4. **Gate discipline:** keep smoke/release/docs checks deterministic and green while AV3 lands.

Detailed milestone and architecture deltas are defined in `docs/AUTONOMOUS_V3_WAVE_PLAN.md`.
Detailed ticket-level DoD/test/PR splits are defined in `docs/AUTONOMOUS_V3_BACKLOG.md`.

## Workflow confidence checks

- Keep `make smoke-autonomous-e2e` as deterministic gate smoke.
- Keep `make check-release-autonomous` in release-readiness flow.
- Keep `make check-docs` mandatory for docs/process updates.

## Definition of done (kickoff package)

- AV3 kickoff status is reflected in status/plan docs.
- AV3 wave plan includes goals, milestones, architecture deltas, and risk mitigations.
- AV3 backlog includes prioritized executable tickets with DoD/test/PR split guidance.
- README/docs navigation includes AV3 plan/backlog links.
- Docs validation remains green (`make check-docs`).

## Related docs

- `docs/AUTONOMOUS_V3_WAVE_PLAN.md`
- `docs/AUTONOMOUS_V3_BACKLOG.md`
- `docs/STATUS_BOARD_CURRENT.md`
- `docs/AUTONOMOUS_V2_WAVE_CLOSURE.md`
- `docs/AUTONOMOUS_MODE.md`
- `docs/ops/AUTONOMOUS_V2_RELEASE_CHECKLIST.md`
- `docs/AUTONOMOUS_FAILURE_PLAYBOOK.md`
