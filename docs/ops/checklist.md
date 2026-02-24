# Template and Release SDLC Checklist

## 1) Required Checks (machine-checkable)

- `docs/ops/template-validation-contract.json`
- `docs/ops/check_template_parity_audit.py`
- `docs/ops/check_template_dependency_locks.sh`
- `docs/ops/check_template_ci_drift.sh`

Run from repo root:

```bash
bash docs/ops/check_template_parity_audit.sh
bash docs/ops/check_template_dependency_locks.sh
bash docs/ops/check_template_ci_drift.sh .
```

Required pre-merge checks:

```bash
make check-template
make check-locks
```

## 2) Make targets

```bash
make compile
make check
make tests
make check-template
make check-locks
make ci
make check-untyped-defs       # optional strict mypy lane (non-blocking by default)
make release-check           # release-readiness checks
```

Notes:
- `make ci` = `compile + check + tests + check-template + check-locks`
- `make release-check` additionally runs `check-untyped-defs` and release-gate checks.

## 3) Release-readiness (Go/No-Go)

### Owners
- **Release Lead**: final go/no-go decision, release branch readiness
- **Platform**: runs `make ci` and verifies CI artifact freshness
- **QA**: validates regression scope and template test coverage
- **Security**: validates lock/scan outputs and policy violations
- **Docs**: verifies docs/reference consistency (Onboarding/Deployment/Monitoring/Failure docs)

### Go/No-Go Criteria
1. `make ci` must pass
2. `make check-template` must pass (workflow parity drift free)
3. `make check-locks` must pass (requirements vs lock parity)
4. `docs/ops/check_template_parity_audit.py` pass criteria: workflow/docs references are in sync
5. Known-risk items must have mitigation notes in this checklist

### Weekly cadence
- **Mon**: lightweight run `make compile`, `make check`
- **Wed/Thu**: run `make tests`
- **Fri**: run `make ci` + release-readiness review and update backlog

## 4) RICE roadmap snapshot (refresh weekly)

| # | Item | Reach | Impact | Confidence | Effort | Score |
|---|---|---:|---:|---:|---:|---:|
| 1 | Release/check pipeline hardening | 10 | 9 | 0.9 | 3 | 27.0 |
| 2 | Template import stability automation | 9 | 8 | 0.85 | 2 | 36.0 |
| 3 | E2E regression generation pipeline | 8 | 8 | 0.8 | 4 | 12.8 |
| 4 | Coverage and quality KPI baseline | 8 | 7 | 0.8 | 4 | 11.2 |
| 5 | Failure postmortem automation | 8 | 7 | 0.8 | 5 | 8.96 |
| 6 | Security policy hardening | 7 | 9 | 0.75 | 5 | 9.45 |
| 7 | Reproducibility hardening | 7 | 8 | 0.75 | 5 | 8.4 |
| 8 | Release packaging/traceability | 7 | 6 | 0.8 | 4 | 8.4 |

**Formula:** `Reach × Impact × Confidence ÷ Effort`

## 5) Escalation
- Critical blocker (`P0`) open >24h: immediately page owner + assign mitigation owner.
- Non-critical backlog risk >72h: re-prioritize into next weekly execution slice.
- If a check is repeatedly flaky, annotate in commit message and add a follow-up ticket before merge.

## 6) Periodic template governance

From root:

```bash
make check-template
make check-locks
make check-untyped-defs
```

If any command fails repeatedly, stop and file an explicit corrective ticket before new feature merges.
