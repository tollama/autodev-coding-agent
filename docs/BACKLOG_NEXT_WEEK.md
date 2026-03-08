# BACKLOG — Next Wave (AV3 Candidates)

This backlog is the execution companion for `docs/PLAN_NEXT_WEEK.md`.

## AV2 wave closure snapshot (`AV2-001` ~ `AV2-014`)

- Closure state: ✅ **complete**
- Ticket count: **14 / 14 done**
- Mainline merge span: PR **#32 → #45**
- Closure summary: `docs/AUTONOMOUS_V2_WAVE_CLOSURE.md`

## AV2 completed baseline

- AV2-001 ✅ quality-gate policy loader
- AV2-002 ✅ quality-gate evaluation engine
- AV2-003 ✅ gate signal normalization taxonomy
- AV2-004 ✅ gate baseline trend persistence
- AV2-005 ✅ auto-fix strategy routing
- AV2-006 ✅ autonomous summary surfacing
- AV2-007 ✅ stop/rollback decision guard
- AV2-008 ✅ resume/restart reliability hardening
- AV2-009 ✅ preflight safety gate
- AV2-010 ✅ budget guard diagnostics
- AV2-011 ✅ operator playbook guidance linking
- AV2-012 ✅ latest quality-gate snapshot API
- AV2-013 ✅ deterministic autonomous E2E smoke lane
- AV2-014 ✅ release evidence checklist guardrails

## Priority-ranked AV3 candidates

> Ticket format
> - **Priority:** P0 / P1 / P2
> - **Owner role:** backend / frontend / platform / docs
> - **Effort:** S / M / L
> - **Acceptance criteria:** testable outcomes
> - **PR split:** recommended patch boundaries for reviewability

### AV3-001 — CI-enforced autonomous release evidence gate

- **Priority:** P0
- **Owner role:** platform
- **Effort:** M
- **Scope:** Run `check_release_autonomous` in CI and block merge/release when required evidence is missing.
- **Acceptance criteria:**
  - CI job executes deterministic autonomous evidence check and uploads artifacts on fail.
  - Branch protection treats gate failure as blocking.
  - README/release docs describe CI evidence workflow.
- **PR split:**
  1) CI workflow + artifact upload
  2) docs wiring and release checklist references

### AV3-002 — Autonomous observability stream + GUI parity hardening

- **Priority:** P0
- **Owner role:** frontend
- **Effort:** M
- **Scope:** Improve operator visibility of autonomous iteration lifecycle beyond periodic snapshots.
- **Acceptance criteria:**
  - Operator can inspect recent autonomous attempt timeline with clear phase/status transitions.
  - API/GUI parity tests cover state, gate, guard, and summary views.
  - Failure states include actionable operator next-step hints.
- **PR split:**
  1) API/state timeline surfacing
  2) GUI presentation + parity tests

### AV3-003 — Operator pause/resume/cancel control surface

- **Priority:** P1
- **Owner role:** backend
- **Effort:** L
- **Scope:** Add safe run-control semantics for long autonomous loops.
- **Acceptance criteria:**
  - Commands support pause/resume/cancel with persisted state transition records.
  - Guardrails prevent unsafe transitions (e.g., resume after terminal fail without explicit restart).
  - Operator runbook and failure playbook include recovery branches.
- **PR split:**
  1) state machine + API control endpoints
  2) CLI/GUI bindings + docs

### AV3-004 — External side-effect policy hardening + audit trail

- **Priority:** P1
- **Owner role:** platform
- **Effort:** M
- **Scope:** Tighten policy and visibility for network/publish/git-like side-effect operations.
- **Acceptance criteria:**
  - Policy config supports explicit allow/deny classes with typed reason codes.
  - Side-effect decisions are persisted to audit artifacts.
  - Summary/report surfaces latest side-effect policy decisions for operators.
- **PR split:**
  1) policy engine + reason-code persistence
  2) summary/report + docs updates

## Related docs

- `docs/PLAN_NEXT_WEEK.md`
- `docs/AUTONOMOUS_V2_WAVE_CLOSURE.md`
- `docs/AUTONOMOUS_MODE.md`
- `docs/ops/AUTONOMOUS_V2_RELEASE_CHECKLIST.md`
- `README.md`
