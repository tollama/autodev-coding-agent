# AUTONOMOUS V3 — Wave Kickoff Plan

Status: 🚀 Kickoff started (2026-03-08)

## Goals / outcomes

1. **Operator control maturity**: pause/resume/cancel flows are safe, auditable, and recoverable.
2. **Observability parity**: autonomous state/timeline is first-class across state artifacts, API, and GUI.
3. **Release confidence**: autonomous release evidence is CI-enforced and merge-blocking when missing.
4. **Policy hardening**: external side-effect controls are explicit, typed, and traceable.
5. **Execution reliability**: deterministic smoke + docs/process gates remain green while AV3 lands.

## 2-week milestone slices

### Week 1 (D1–D7): foundation + enforcement

- Finalize AV3 scope and acceptance contracts (`AV3-001`~`AV3-006`).
- Land CI autonomous release-evidence gate wiring.
- Add autonomous timeline/state model extensions for API consumption.
- Draft operator control state-transition contract (pause/resume/cancel).
- Add baseline docs/runbook updates for AV3 operator flow.

Exit criteria:
- CI gate is running in PR checks.
- Timeline payload schema is defined and test-covered.
- Control-surface contract is approved and linked from docs.

### Week 2 (D8–D14): control surface + hardening

- Land GUI/API parity for autonomous timeline and control status.
- Implement pause/resume/cancel path with guardrail checks and persistence.
- Land side-effect policy/audit trail scaffolding.
- Extend smoke/check lanes for AV3 evidence paths.
- Complete AV3 kickoff review package (status, backlog health, next PR slices).

Exit criteria:
- Operator can observe + control autonomous runs via defined surfaces.
- Docs/checks are green (`make check-docs`) with AV3 references.
- Backlog has clear PR-splittable sequence for wave execution.

## Architecture deltas from AV2

- **From snapshots to timeline stream**: AV2 focused on latest summary snapshot; AV3 adds attempt/phase timeline model for richer operator triage.
- **From guard-only to control-loop**: AV2 emphasized stop/retry/rollback decisioning; AV3 adds explicit operator control transitions (pause/resume/cancel) with invariants.
- **From local evidence check to CI policy enforcement**: AV2 delivered deterministic evidence check tooling; AV3 moves this into CI branch protection posture.
- **From binary side-effect toggles to typed policy decisions**: AV2 default-safe toggles remain; AV3 introduces explicit side-effect classes and audit-grade decision artifacts.
- **From handoff planning docs to wave execution package**: AV2 closure + AV3 candidates evolve into a milestone-backed plan/backlog pair.

## Top risks + mitigations

1. **Risk:** control transitions introduce inconsistent run state.
   - **Mitigation:** enforce strict state-machine invariants + transition tests before UI exposure.
2. **Risk:** observability payload drift between state/API/GUI.
   - **Mitigation:** parity contract tests and a single canonical timeline schema.
3. **Risk:** CI evidence gate increases friction/noise.
   - **Mitigation:** deterministic artifacts + fail-reason clarity + documented remediation path.
4. **Risk:** policy hardening blocks legitimate workflows.
   - **Mitigation:** phased rollout (warn → enforce) and reason-code-based override review.
5. **Risk:** scope creep across AV3 domains in one PR.
   - **Mitigation:** enforce backlog PR splits and narrow, reviewable slices.

## Linked execution docs

- `docs/AUTONOMOUS_V3_BACKLOG.md`
- `docs/STATUS_BOARD_CURRENT.md`
- `docs/PLAN_NEXT_WEEK.md`
- `docs/AUTONOMOUS_MODE.md`
