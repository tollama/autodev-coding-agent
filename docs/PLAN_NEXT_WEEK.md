# PLAN — Next Week (Operator Reliability)

## Scope

This plan reflects `main` after merges through **NXT-013**, and includes **NXT-014 backlog grooming + priority re-rank**.
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
- NXT-013: Next-cut RC checklist + changelog draft

## NXT-014 outcome (this ticket)

- Groomed backlog using demo-day findings and runbook failure branches.
- Re-ranked carry-over follow-ups by operator impact and demo risk.
- Converted carry-over work into actionable tickets with explicit metadata:
  - priority
  - owner role
  - effort
  - acceptance criteria
  - recommended PR split

## Next-wave priority stack (post NXT-014)

1. **NXT-015 (P0)** — RC evidence completeness preflight
   - Why first: removes cut-time risk by preventing incomplete RC evidence bundles.
2. **NXT-016 (P0)** — Local-simple startup diagnostics quick-check lane
   - Why second: fastest way to reduce demo interruption when GUI/API boot path fails.
3. **NXT-017 (P1)** — Processes triage UX follow-up (filtering + stale hints)
   - Why third: improves operator recovery speed during stop/retry troubleshooting.
4. **NXT-018 (P1)** — Artifact Viewer triage exports + docs consistency lint
   - Why fourth: strengthens incident handoff and avoids docs drift across runbooks.

Detailed ticket specs live in `docs/BACKLOG_NEXT_WEEK.md`.

## Workflow confidence checks

- Continue using `make smoke-local-simple-e2e` for operator-path smoke validation.
- Keep `make check-docs` mandatory for docs-only planning/process changes.
- Keep RC dry-run command examples copy-paste ready from repo root.

## Handoff clarity

- Keep local-simple (single-user) vs hardened mode (`autodev gui`) boundaries explicit.
- Keep planning docs synced with README and demo playbook known limits.

## Definition of done (planning/workflow)

- Plan and backlog are aligned on priority order and ownership.
- Carry-over tickets have concrete acceptance + PR split guidance.
- Active planning links point to this file and `docs/BACKLOG_NEXT_WEEK.md`.
- Docs validation remains green (`make check-docs`).

## Related docs

- `docs/BACKLOG_NEXT_WEEK.md`
- `docs/LOCAL_SIMPLE_MODE.md`
- `docs/DEMO_PLAYBOOK.md`
- `docs/RC_NEXT_CUT_CHECKLIST.md`
- `docs/CHANGELOG_DRAFT_NEXT_CUT.md`
