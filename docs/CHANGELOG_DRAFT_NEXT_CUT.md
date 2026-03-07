# CHANGELOG DRAFT — Next Cut (RC)

Status: Draft for RC review (do not treat as final release notes).

How to use:
1. Fill evidence placeholders below during RC dry-run.
2. Remove/trim placeholder notes.
3. Copy finalized sections into root `CHANGELOG.md` at release cut.

## Added

- RC process documentation for next-cut handoff:
  - `docs/RC_NEXT_CUT_CHECKLIST.md`
  - `docs/CHANGELOG_DRAFT_NEXT_CUT.md`
- Planning docs refreshed for baseline through NXT-012 and NXT-013 RC scope:
  - `docs/PLAN_NEXT_WEEK.md`
  - `docs/BACKLOG_NEXT_WEEK.md`

## Changed

- Release-candidate dry-run command examples are now explicitly documented in `docs/RC_NEXT_CUT_CHECKLIST.md`:
  - docs validation command (`make check-docs`)
  - local-simple API start dry-run (`POST /api/runs/start` with `execute=false`)

## Fixed

- N/A (docs/process-only ticket; no runtime bug fix in this draft)

## Known limits (carry forward / confirm before final cut)

- Polling-based updates only (no live stream/WebSocket yet).
- Process control remains best-effort and depends on tracked subprocess lifecycle.
- JSON artifact schema remains unversioned; GUI compatibility can break on schema changes.

Evidence placeholder: `TODO: link to README.md#known-limits-mvp review note`

## RC evidence placeholders

- Tests evidence: `TODO`
- Docs evidence (`make check-docs` output): `TODO`
- Dry-run API response capture: `TODO`
- Reviewer sign-off: `TODO`
