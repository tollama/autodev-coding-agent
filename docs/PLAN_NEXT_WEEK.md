# PLAN — Next Week (Operator Reliability)

## Scope

This plan reflects `main` after merges through **NXT-012**.
Primary objective: keep local-simple operator workflow reliable, demoable, and RC handoff-ready on a single laptop.

## Current baseline (already merged)

- NXT-001: Quick-run payload validation hardening
- NXT-002: Process polling backoff + stale indicator
- NXT-003: Artifact viewer large-JSON responsiveness
- NXT-004: Timeline taxonomy normalization
- NXT-005: Scorecard API + Overview widget
- NXT-006: Correlation-id tracing for run controls
- NXT-007: Local-simple E2E smoke lane
- NXT-008: Fixture expansion + typed artifact errors
- NXT-009: Stop/retry race hardening + idempotency
- NXT-010: One-command demo bootstrap (`make demo-bootstrap*`)
- NXT-011: Local-simple operator runbook refresh
- NXT-012: Overview/Validation/Processes empty/error/loading UX pass

## Next-week focus

1. **RC readiness docs/process (NXT-013)**
   - Add next-cut release-candidate checklist with explicit pass/fail gates.
   - Add changelog draft artifact for RC notes handoff.
   - Keep evidence placeholders explicit (tests/docs/known limits) so dry-run and final RC can share the same template.

2. **Workflow confidence checks**
   - Continue using `make smoke-local-simple-e2e` for operator path smoke.
   - Keep `make check-docs` in docs-only changes.

3. **Handoff clarity**
   - Keep local-simple (single-user) vs hardened mode (`autodev gui`) boundaries explicit.
   - Keep RC dry-run command examples copy-paste ready.

## Definition of done (docs/workflow)

- Docs describe what operators can actually do today.
- RC checklist includes clear pass/fail sections with evidence placeholders.
- RC changelog draft exists and is ready to copy into `CHANGELOG.md` at cut time.
- Active planning links point to this file and `docs/BACKLOG_NEXT_WEEK.md`.

## Related docs

- `docs/BACKLOG_NEXT_WEEK.md`
- `docs/LOCAL_SIMPLE_MODE.md`
- `docs/DEMO_PLAYBOOK.md`
- `docs/RC_NEXT_CUT_CHECKLIST.md`
- `docs/CHANGELOG_DRAFT_NEXT_CUT.md`
