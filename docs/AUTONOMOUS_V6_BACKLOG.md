# AUTONOMOUS V6 — Prioritized Backlog (Kickoff)

Status: 🚧 Kickoff started (2026-03-09)
Companion plan: `docs/AUTONOMOUS_V6_WAVE_PLAN.md`
Checkpoint scaffold: `docs/AUTONOMOUS_V6_WAVE_CHECKPOINT.md`

| ID | Priority | Effort | Status | Ticket | Definition of Done (DoD) | Test plan | PR split |
|---|---|---:|---|---|---|---|---|
| AV6-001 | P0 | S | ✅ Merged | Autoresearch hard-blocker policy contract | blocker classes, severity mapping, and mandatory stop/escalate semantics are documented with canonical examples | `make check-docs` + policy example review | 1 PR |
| AV6-002 | P0 | S | ✅ Merged | Scoring threshold matrix (pass/retry/escalate/stop) | threshold bands and tie-break rules are defined with deterministic decision table and fallback semantics | threshold table review + `make check-docs` | 1 PR |
| AV6-003 | P0 | M | ✅ Merged | Time-budget guardrails (global + stage budget caps) | per-run/per-stage budget defaults and overrun actions are defined with explicit timeout/error contracts and linked to the runtime-aligned AV6 policy doc | policy dry-run walkthrough + `make check-docs` + `pytest autodev/tests/test_autonomous_mode.py -k budget_guard` | 1 PR |
| AV6-004 | P1 | M | ✅ Drafted | Observability baseline for autoresearch guard decisions | canonical telemetry fields/events for blocker + threshold + budget decisions are documented and linked to operator surfaces | evidence schema review + `make check-docs` + `pytest autodev/tests/test_trust_intelligence.py -k trust_summary` | 1 PR |
| AV6-005 | P1 | S | 🚧 Planned | Status-hook transition draft for AV6 kickoff lifecycle | AV6 kickoff/execution/stabilization/closure transition semantics are reflected in transition matrix/runbook | `make check-status-hooks` + docs diff review | 1 PR |
| AV6-006 | P2 | S | ✅ Merged | AV5 carryover intake map | deferred AV5 tickets are mapped to AV6 IDs with traceability annotations per carryover policy | carryover format audit + `make check-docs` | 1 PR |
| AV6-007 | P2 | S | 🚧 Planned | AV5-010 carryover: Docs cross-link upgrade for AV5 governance set | carryover target ticket is registered with AV5 source traceability and closure annotation contract | intake map review + `make check-docs` | 1 PR |
| AV6-008 | P2 | S | 🚧 Planned | AV5-011 carryover: Transition-runbook update (AV4 closed → AV5 active) | carryover target ticket is registered with AV5 source traceability and closure annotation contract | intake map review + `make check-docs` | 1 PR |

## Prioritization notes

- Execute `AV6-001` ~ `AV6-003` first to set hard safety envelopes before expanding feature scope.
- Keep observability (`AV6-004`) immediately behind policy controls to avoid blind guard behavior.
- Use `AV6-005` to keep status automation deterministic as AV6 progresses.

## Related docs

- `docs/AUTONOMOUS_V6_WAVE_PLAN.md`
- `docs/AUTONOMOUS_V6_WAVE_CHECKPOINT.md`
- `docs/AUTONOMOUS_V6_SCORING_THRESHOLD_MATRIX.md`
- `docs/AUTONOMOUS_V6_TIME_BUDGET_GUARDRAILS.md`
- `docs/AUTONOMOUS_V6_GUARD_OBSERVABILITY_BASELINE.md`
- `docs/AUTONOMOUS_AUTORESEARCH_BLOCKER_POLICY.md`
- `docs/AUTONOMOUS_V5_CARRYOVER_POLICY.md`
- `docs/AUTONOMOUS_V6_AV5_CARRYOVER_INTAKE_MAP.md`
- `docs/PLAN_NEXT_WEEK.md`
- `docs/BACKLOG_NEXT_WEEK.md`
- `docs/STATUS_BOARD_CURRENT.md`
