# BACKLOG — Next Week (Operator Reliability)

This backlog is the execution companion for `docs/PLAN_NEXT_WEEK.md`.

## In progress / ready

### NXT-013 — Next-cut RC checklist + changelog draft

- **Goal:** Prepare docs/process artifacts for release-candidate dry-run and cut handoff.
- **Scope:** docs-only updates (no product code changes).
- **Acceptance:**
  - next-cut RC checklist includes tests/docs/known-limits/changelog evidence placeholders
  - checklist has explicit pass/fail gate sections and go/no-go outcome block
  - RC dry-run command examples are copy-paste ready
  - changelog draft file exists and maps changes to next cut categories
  - docs validation command documented/used (`make check-docs`)

## Completed baseline (for context)

- NXT-001 ✅ quick-run payload validation hardening
- NXT-002 ✅ process polling backoff + stale indicator
- NXT-003 ✅ artifact viewer large-JSON responsiveness
- NXT-004 ✅ timeline taxonomy normalization
- NXT-005 ✅ scorecard API + Overview widget
- NXT-006 ✅ correlation-id tracing for run controls
- NXT-007 ✅ local-simple E2E smoke lane
- NXT-008 ✅ fixture expansion + typed artifact errors
- NXT-009 ✅ stop/retry race hardening + idempotent retry
- NXT-010 ✅ one-command demo bootstrap lane
- NXT-011 ✅ local-simple operator runbook refresh
- NXT-012 ✅ explicit empty/error/loading UX pass for Overview/Validation/Processes

## Candidate follow-ups (post NXT-013)

- Add a lightweight script that validates RC checklist evidence-path fields are filled before release tag.
- Add an optional `make rc-dry-run` alias that wraps the documented API dry-run command + response assertions.
- Add docs freshness checks to keep known-limit statements aligned across README and runbooks.

## Related docs

- `docs/PLAN_NEXT_WEEK.md`
- `docs/LOCAL_SIMPLE_MODE.md`
- `docs/DEMO_PLAYBOOK.md`
- `docs/RC_NEXT_CUT_CHECKLIST.md`
- `docs/CHANGELOG_DRAFT_NEXT_CUT.md`
- `README.md`
