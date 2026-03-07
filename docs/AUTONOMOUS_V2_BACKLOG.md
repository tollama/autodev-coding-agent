# AUTONOMOUS v2 — Backlog (Kickoff Wave)

This backlog is the execution companion for `docs/AUTONOMOUS_V2_WAVE_PLAN.md`.

## Ticket format

Each ticket includes:
- ID
- Priority (P0/P1/P2)
- Owner
- Effort (S/M/L)
- DoD (Definition of Done)
- Test plan
- PR split

---

## Wave tickets (14)

| ID | Priority | Owner | Effort | DoD | Test plan | PR split |
|---|---|---|---|---|---|---|
| AV2-001 | P0 | Platform | M | v2 execution contract schema added with examples for task DAG metadata, lane budgets, and policy envelope. | Schema validation tests for valid/invalid fixtures; docs link checks. | (1) schema + fixtures (2) docs wiring |
| AV2-002 | P0 | Orchestration | M | Lane scheduler admission policy (concurrency cap + queue ordering) implemented behind feature flag. | Unit tests for ordering/fairness + starvation guard; replay smoke on sample DAGs. | (1) scheduler core (2) flag plumbing + docs |
| AV2-003 | P0 | Orchestration | M | Per-lane isolation boundaries enforced for workspace writes and artifact namespaces. | Integration test proving no cross-lane file contamination on parallel run. | (1) isolation mechanism (2) integration tests |
| AV2-004 | P0 | Platform | S | Global + per-lane budget governor (token/time/tool calls) integrated into admission checks. | Deterministic budget exhaustion fixtures; verify halt reason codes. | (1) governor logic (2) fixture tests + report fields |
| AV2-005 | P0 | Quality | M | Unified gate decision payload (`pass`/`conditional-pass`/`fail`) emitted from gate runner. | Golden fixture tests for each decision type + edge conditions. | (1) payload model/adapters (2) docs + fixture updates |
| AV2-006 | P0 | Release Eng | M | Release-governor stage decision model aligned with risk tiers and SLO checks. | Canary simulation tests for advance/hold/rollback transitions. | (1) decision model (2) simulation tests + docs |
| AV2-007 | P1 | Quality | S | Policy exception registry fields (owner, expiry, rationale, linked incident) required for conditional pass. | Validation tests reject missing/expired exception metadata. | (1) schema + validator (2) runbook/docs updates |
| AV2-008 | P1 | Platform | M | Versioned evidence manifest (`manifest_version`, index, references) produced for autonomous runs. | Contract test for manifest completeness and backward-compatible reads. | (1) manifest writer (2) readers + migration notes |
| AV2-009 | P1 | Observability | M | Correlation IDs stitched across planner -> lane -> gate -> release artifacts. | End-to-end trace test confirming consistent correlation linkage in artifacts/logs. | (1) ID propagation (2) observability assertions |
| AV2-010 | P1 | Docs/Ops | S | v2 operator runbook draft includes feature flags, fallback path, and incident triage map. | Docs lint + scenario checklist walkthrough in dry run. | (1) runbook content (2) README/doc cross-links |
| AV2-011 | P1 | Reliability | M | Failure taxonomy mapping expanded for v2 lane/gate/release failures with playbook IDs. | Table-driven tests mapping representative failure signatures to classes/actions. | (1) taxonomy map (2) dispatcher hooks + docs |
| AV2-012 | P2 | Platform | S | v1/v2 compatibility adapter for core autonomous artifacts added and documented. | Compatibility tests load old v1 fixtures and emit normalized view. | (1) adapter implementation (2) fixture coverage |
| AV2-013 | P2 | Product/Release | S | Pilot scope policy file (service allowlist + risk guardrails + success criteria) merged. | Policy lint + dry-run policy checks for denied out-of-scope target. | (1) pilot policy config (2) rollout checklist docs |
| AV2-014 | P2 | Docs/Ops | S | KPI starter dashboard spec documented (definitions, formulas, data sources, thresholds). | Doc review checklist + consistency check against commercial plan KPI section. | (1) dashboard spec doc (2) cross-reference cleanup |

---

## Priority sequencing (recommended)

1. **First block (must finish for v2 technical baseline):** AV2-001 → AV2-006
2. **Second block (operational hardening):** AV2-007 → AV2-011
3. **Third block (pilot/readiness):** AV2-012 → AV2-014

## Notes

- Keep initial rollout docs-first + flag-guarded for implementation changes.
- Preserve v1 command/operator compatibility during all P0/P1 work.
- Any schema change must include fixture updates and migration notes.

## Related references

- `docs/AUTONOMOUS_V2_WAVE_PLAN.md`
- `docs/AUTONOMOUS_COMMERCIAL_PLAN.md`
- `docs/AUTONOMOUS_MODE.md`
