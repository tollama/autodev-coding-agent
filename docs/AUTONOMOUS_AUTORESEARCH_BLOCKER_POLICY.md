# Autonomous autoresearch hard-blocker policy contract (AV6-001)

Status: Drafted for AV6 kickoff  
Canonical schema: `docs/ops/autonomous_autoresearch_blocker_policy_v1.schema.json`  
Canonical example: `docs/ops/autonomous_autoresearch_blocker_policy_v1.example.json`

This policy defines **non-negotiable hard blockers** for autoresearch-triggered actions.
If a blocker matches, runtime must take the contract's mandatory decision lane (`stop` or `escalate`) with no soft override.

## Severity model

- `high`: operator escalation boundary; execution cannot continue unattended.
- `critical`: immediate hard stop boundary; execution halts before further mutation.

## Hard-blocker classes

| Blocker class | Severity | Mandatory lane | Intent |
|---|---|---|---|
| `policy_scope_violation` | `critical` | `stop` | Requested mutation or target is outside declared policy scope. |
| `unapproved_external_side_effect` | `critical` | `stop` | Action would cause external side effects without explicit approval token. |
| `evidence_integrity_failure` | `high` | `escalate` | Evidence is missing/corrupted/non-reproducible, so autonomous trust cannot be established. |
| `high_risk_surface_without_guard` | `high` | `escalate` | Change touches high-risk surfaces without required guard controls (tests/checklists/approval path). |

## Mandatory decision semantics

1. Resolve blocker class from typed guard signal.
2. Read severity + mandatory lane from policy contract (no ad-hoc remap).
3. Persist decision reason and policy references in artifacts/operator summary.
4. `stop` requires run termination before any retry decision.
5. `escalate` requires explicit operator acknowledgement before resuming.

## Canonical examples

| Example | Typed code | Blocker class | Expected decision |
|---|---|---|---|
| `HB-01` | `autonomous_preflight.scope_policy_mismatch` | `policy_scope_violation` | `stop` |
| `HB-02` | `autonomous_execute.external_write_without_approval` | `unapproved_external_side_effect` | `stop` |
| `HB-03` | `autonomous_verify.operator_summary_missing_evidence` | `evidence_integrity_failure` | `escalate` |
| `HB-04` | `autonomous_execute.production_surface_without_guardrail` | `high_risk_surface_without_guard` | `escalate` |

## Validation gates

- Policy contract schema/example check: `python3 scripts/check_autoresearch_blocker_policy.py`
- Docs lane: `make check-docs`

## Related docs

- `docs/AUTONOMOUS_V6_BACKLOG.md`
- `docs/AUTONOMOUS_V6_WAVE_PLAN.md`
- `docs/AUTODEV_AUTORESEARCH_ADAPTATION.md`
- `docs/AUTONOMOUS_FAILURE_TAXONOMY_V2.md`
