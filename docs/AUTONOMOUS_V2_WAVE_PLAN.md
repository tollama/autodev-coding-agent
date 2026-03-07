# AUTONOMOUS v2 — Wave Kickoff Plan

> Scope: docs-only kickoff package for the next autonomous delivery wave.

## Wave goals and target outcomes

This wave moves Autonomous mode from a resilient **single-loop v1** into a controllable **multi-lane v2 execution system** with stronger policy, gate orchestration, and release governance.

### Goals

1. **Scale execution safely**
   - introduce bounded parallel lanes with explicit risk/cost/time controls.
2. **Improve determinism and observability**
   - standardize run contracts, event schemas, and evidence manifests.
3. **Raise promotion confidence**
   - tighten gate policy handling and release-governor decisions.
4. **Reduce operator burden**
   - better defaults, clearer triage, and faster incident recovery paths.

### Target outcomes (end of wave)

- v2 execution contract documented and accepted (`plan + policy + evidence`).
- parallel lane orchestration available behind a feature flag with deterministic replay on fixtures.
- unified gate decision payload used consistently in autonomous reports.
- release-governor canary/rollback policy aligned with risk tier definitions.
- KPI-ready telemetry map (run success, first-pass gate rate, rollback triggers, policy denials).

---

## Milestones (2-week slices)

## Slice 1 (Weeks 1-2): Contract + control-plane baseline

- finalize v2 execution contract (task DAG metadata, lane budget, side-effect envelope).
- define event taxonomy (`run`, `lane`, `gate`, `release`) and evidence manifest schema.
- add feature flags for v2 lane scheduler and gate payload version.
- deliver architecture decision record for v1 -> v2 transitions.

**Exit criteria**
- docs + schema examples merged.
- contract review sign-off from platform/orchestration/quality owners.

## Slice 2 (Weeks 3-4): Multi-lane executor (guarded rollout)

- implement lane scheduler rules (max concurrency, backoff, starvation prevention).
- add per-lane isolation boundaries and artifact lineage mapping.
- integrate budget/time/risk enforcement at lane admission.
- run replay suite against representative autonomous fixtures.

**Exit criteria**
- deterministic replay success on target fixture set.
- no cross-lane artifact contamination in integration checks.

## Slice 3 (Weeks 5-6): Quality and release gate unification

- standardize gate decision model (`pass` / `conditional-pass` / `fail`) with signed evidence links.
- align release-governor stage decisions with risk tiers and SLO gates.
- add policy exception lifecycle fields (owner, expiry, rationale, incident link).
- connect autonomous report generation to unified gate + release payloads.

**Exit criteria**
- gate/release payload contract stable and documented.
- canary + rollback dry run reproducible from fixture artifacts.

## Slice 4 (Weeks 7-8): Pilot hardening + operator readiness

- finalize operator runbook deltas for v2 mode and fallback paths.
- publish KPI starter dashboard mapping (sources, formulas, thresholds).
- run low-risk pilot wave and collect failure taxonomy + mitigations.
- produce go/no-go decision memo for broader enablement.

**Exit criteria**
- pilot completes with defined success thresholds.
- unresolved blockers converted into post-wave backlog with owners.

---

## Architecture deltas from v1

| Area | v1 (current) | v2 (target) | Expected benefit |
|---|---|---|---|
| Execution model | Mostly single-loop attempts with bounded retries | Multi-lane DAG execution with admission control | Faster throughput without uncontrolled risk |
| Policy enforcement | Primarily run-level caps | Run-level + lane-level + phase-level controls | Finer safety and budget governance |
| Evidence model | Artifact files per run; partially heterogeneous payload shapes | Versioned evidence manifest + normalized event schema | Better auditability and replay/debug |
| Quality gates | Validator outputs + report synthesis | Unified gate decision payload with explicit conditions/exceptions | Deterministic promotion criteria |
| Release governance | Conceptually documented; partially coupled to run artifacts | First-class release-governor decision model (stage, SLO watch, rollback reason) | Safer rollout automation |
| Observability | Run artifacts + logs | KPI-ready telemetry map and correlation IDs across planner/lanes/gates/release | Faster incident triage and trend tracking |
| Recovery behavior | Fix loops and bounded retries | Failure-class-aware playbooks with escalation hooks | Lower MTTR and clearer operator actions |

### Compatibility strategy

- keep `autodev autonomous start` CLI compatible; v2 behavior introduced via explicit profile/flag.
- preserve v1 artifact readability during transition (dual-write or adapter for key payloads).
- avoid breaking existing local-simple and GUI operator flows during initial v2 rollout.

---

## Risk register and mitigations

| Risk ID | Risk | Probability | Impact | Mitigation | Owner |
|---|---|---|---|---|---|
| AV2-R01 | Lane scheduler introduces non-deterministic ordering bugs | M | H | deterministic tie-break rules; replay fixtures in CI; explicit seed/logging | Orchestration |
| AV2-R02 | Parallel lanes exceed token/time budgets | M | H | lane admission quotas + global budget governor + hard stop behavior | Platform |
| AV2-R03 | Evidence schema drift breaks downstream tools | M | M | schema versioning, contract tests, migration notes, deprecation window | Platform |
| AV2-R04 | Gate decision semantics inconsistent across validators | M | H | unified gate adapter layer + golden fixture verification | Quality |
| AV2-R05 | Release-governor false positives trigger noisy rollbacks | L | H | canary threshold tuning, hold period, rollback reason codes, staged enablement | Release Eng |
| AV2-R06 | Policy exception process becomes permanent bypass | M | H | mandatory expiry + owner + weekly exception review | Security/Quality |
| AV2-R07 | Operator confusion during v1/v2 coexistence | M | M | clear runbook matrix, feature-flag labels, UI copy updates | Docs/Ops |
| AV2-R08 | Increased complexity slows triage and onboarding | M | M | concise architecture diagrams, quickstart diagnostics, incident drills | Docs/Ops |
| AV2-R09 | Backward compatibility regressions in existing CLI/UI paths | L | H | compatibility tests for v1 commands; canary rollout for v2 profile only | Platform |
| AV2-R10 | Pilot scope expands beyond low-risk envelope | L | H | strict pilot allowlist + approval gate for scope changes | Product/Release |

---

## Deliverables in this kickoff package

- `docs/AUTONOMOUS_V2_WAVE_PLAN.md` (this file)
- `docs/AUTONOMOUS_V2_BACKLOG.md` (execution tickets)
- cross-links from:
  - `README.md`
  - `docs/AUTONOMOUS_COMMERCIAL_PLAN.md`

## Related references

- `docs/AUTONOMOUS_MODE.md`
- `docs/AUTONOMOUS_COMMERCIAL_PLAN.md`
- `docs/PLAN_NEXT_WEEK.md`
- `docs/BACKLOG_NEXT_WEEK.md`
