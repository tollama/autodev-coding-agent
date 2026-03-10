# AUTONOMOUS V6 — AV5 Carryover Intake Map

Status: ✅ AV6-006 draft complete (pending merge)
Source policy: `docs/AUTONOMOUS_V5_CARRYOVER_POLICY.md`

## Purpose

Map AV5 deferred tickets into AV6 carryover targets with policy-compliant traceability annotations.

## Intake ledger

| Source (AV5) | Source title | Target (AV6) | AV6 ticket title (policy naming) | Carryover annotation |
|---|---|---|---|---|
| `AV5-010` | Docs cross-link upgrade for AV5 governance set | `AV6-007` | `AV5-010 carryover: Docs cross-link upgrade for AV5 governance set` | `[CARRYOVER][AV5->AV6] source=AV5-010 target=AV6-007 status=deferred reason="Deferred at AV5 checkpoint; governance cross-link cleanup moved to AV6 kickoff queue" owner=@autonomous-docs` |
| `AV5-011` | Transition-runbook update (AV4 closed → AV5 active) | `AV6-008` | `AV5-011 carryover: Transition-runbook update (AV4 closed → AV5 active)` | `[CARRYOVER][AV5->AV6] source=AV5-011 target=AV6-008 status=deferred reason="Deferred at AV5 checkpoint; transition-runbook hardening moved to AV6 carryover intake" owner=@autonomous-docs` |

## Carryover format audit checklist

- `source` and `target` use `AV5-###` / `AV6-###` ID patterns.
- `status` is fixed to `deferred`.
- `reason` is non-empty and quoted.
- `owner` is an accountable team handle.
- AV6 ticket title follows `<AV5-ID> carryover: <original AV5 ticket title>`.

## References

- `docs/AUTONOMOUS_V5_BACKLOG.md`
- `docs/AUTONOMOUS_V5_WAVE_CHECKPOINT.md`
- `docs/AUTONOMOUS_V5_CARRYOVER_POLICY.md`
- `docs/AUTONOMOUS_V6_BACKLOG.md`
- `docs/BACKLOG_NEXT_WEEK.md`
