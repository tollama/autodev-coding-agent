# Next-Cut Release Candidate (RC) Checklist

This checklist is for **NXT-013 docs/process RC dry-runs** and final cut handoff.

Scope guard:
- Docs/process only (no product/runtime code changes)
- Evidence-first: each gate requires an attached path/link before marking PASS

## 1) Gate summary (PASS/FAIL)

| Gate | Status (PASS/FAIL) | Evidence (link or path placeholder) | Notes |
| --- | --- | --- | --- |
| Tests gate | ☐ PASS / ☐ FAIL | `TODO: artifacts/local-simple-e2e-smoke/<timestamp>/` | Include smoke and any targeted test logs |
| Docs gate | ☐ PASS / ☐ FAIL | `TODO: output of make check-docs` | Include command + timestamp |
| Known limits review | ☐ PASS / ☐ FAIL | `TODO: README.md#known-limits-mvp + docs/LOCAL_SIMPLE_MODE.md` | Confirm limits are current and non-contradictory |
| Changelog draft ready | ☐ PASS / ☐ FAIL | `docs/CHANGELOG_DRAFT_NEXT_CUT.md` | Ready to copy into root `CHANGELOG.md` |

## 2) RC dry-run commands (copy-paste)

### 2.1 Docs/process validation

```bash
make check-docs
```

Expected: `[PASS] markdown link check` with no broken local links.

### 2.2 Local-simple API start dry-run (no process spawn)

Start GUI in a separate terminal first:

```bash
autodev local-simple --runs-root ./generated_runs --host 127.0.0.1 --port 8787
```

Then run dry-run command:

```bash
curl -fsS -X POST http://127.0.0.1:8787/api/runs/start \
  -H 'Content-Type: application/json' \
  -d '{
    "prd": "examples/PRD.md",
    "out": "./generated_runs",
    "profile": "local_simple",
    "execute": false
  }'
```

Expected response highlights:
- `"spawned": false`
- `"result_status": "dry_run"`
- `command_preview` is present for operator review

## 3) Detailed pass/fail criteria

### PASS criteria

- All gate rows in section 1 are marked PASS.
- Evidence fields contain concrete links/paths (not TODO placeholders).
- Dry-run response confirms non-executing start path (`execute=false`, `spawned=false`).
- No broken docs links from `make check-docs`.

### FAIL / BLOCKERS

- Any gate marked FAIL.
- Missing evidence for any PASS-marked gate.
- Dry-run command cannot be reproduced from repo-root copy-paste.
- `make check-docs` reports broken links.

## 4) RC decision record

- Decision: ☐ GO / ☐ NO-GO
- RC candidate tag/label: `TODO`
- Checked by: `TODO`
- Checked at (KST): `TODO`
- Follow-up owner (if NO-GO): `TODO`

## 5) Evidence bundle template

Use this block when posting RC status in PR/comments/releases:

```text
[RC Evidence Bundle]
- Tests: <path-or-link>
- Docs: <path-or-link>
- Known limits review: <path-or-link>
- Changelog draft: docs/CHANGELOG_DRAFT_NEXT_CUT.md
- Dry-run response capture: <path-or-link>
- Final decision: GO | NO-GO
```
