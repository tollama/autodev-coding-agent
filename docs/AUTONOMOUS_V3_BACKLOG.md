# AUTONOMOUS V3 — Prioritized Backlog

Status: 🚀 Kickoff started (2026-03-08)
Companion plan: `docs/AUTONOMOUS_V3_WAVE_PLAN.md`

> Effort scale: S (≤1 day), M (1-3 days), L (3-5 days)

| ID | Priority | Effort | Ticket | DoD (Definition of Done) | Test plan | PR split |
|---|---|---|---|---|---|---|
| AV3-001 | P0 | M | CI-enforced autonomous release evidence gate | CI runs `check-release-autonomous`; failure blocks merge; artifacts uploaded on fail | CI workflow test, intentional failing fixture, pass fixture | PR1: workflow + gate; PR2: docs/checklist wiring |
| AV3-002 | P0 | M | Autonomous timeline schema (state/API canonical model) | Timeline schema versioned in artifacts; API exposes latest timeline safely | Unit tests for schema normalization + API response contract tests | PR1: schema + persistence; PR2: API surface |
| AV3-003 | P0 | M | GUI autonomous timeline view parity | GUI renders attempt/phase timeline with fail reasons and timestamps | UI tests (empty/loading/error/success) + API parity snapshot checks | PR1: API client + models; PR2: UI panels + tests |
| AV3-004 | P0 | M | Pause/resume/cancel state-machine contract | Explicit transition matrix implemented; invalid transitions rejected with typed reasons | Unit tests for valid/invalid transitions + persistence tests | PR1: state machine; PR2: typed reason docs |
| AV3-005 | P1 | L | Pause/resume/cancel backend control endpoints | Control endpoints callable and persist transitions in run artifacts | API integration tests for each transition path + terminal-state guards | PR1: endpoints + persistence; PR2: integration tests |
| AV3-006 | P1 | M | CLI bindings for operator control | CLI commands exposed for pause/resume/cancel with clear output/error semantics | CLI e2e command tests against mocked run dirs | PR1: CLI command wiring; PR2: docs/examples |
| AV3-007 | P1 | M | Side-effect policy v2 (typed classes + reason codes) | Policy supports side-effect classes and emits typed allow/deny reason codes | Unit tests across allow/deny matrix + fallback behavior | PR1: policy engine; PR2: reason-code docs |
| AV3-008 | P1 | M | Side-effect decision audit artifact | Per-run audit artifact persisted and referenced by summary/report | Artifact existence/format tests + summary linkage tests | PR1: artifact writer; PR2: summary/report linkage |
| AV3-009 | P1 | S | Failure playbook expansion for AV3 control/policy codes | Playbook has AV3 reason-code mappings and operator actions | `make check-docs` + link anchor checks for new mappings | PR1: docs only |
| AV3-010 | P1 | M | Autonomous summary/API enrichment for AV3 signals | Summary includes timeline/control/policy highlights with graceful degradation | Unit tests for summary builder + API snapshot parity | PR1: summary model; PR2: API and docs |
| AV3-011 | P2 | S | Deterministic smoke extension for AV3 timeline/control evidence | Smoke lane captures AV3 evidence artifacts deterministically | Smoke script tests + artifact assertion tests | PR1: smoke script updates; PR2: docs/runbook updates |
| AV3-012 | P2 | S | Release checklist update for AV3 evidence requirements | Release checklist includes AV3 control/timeline/policy evidence gates | Checklist lint + docs link checks | PR1: docs only |
| AV3-013 | P2 | M | Operator UI action safeguards (confirm/cancel UX) | GUI prevents destructive accidental control actions and shows next-step hints | UI tests for confirmation flows and disabled states | PR1: UX guard components; PR2: test coverage |
| AV3-014 | P2 | S | AV3 wave status board automation hooks | Status board template fields for AV3 progress/risks are documented and reusable | Docs checks + sample status render verification | PR1: status doc template + references |

## Prioritization notes

- **Execution start line:** AV3-001 → AV3-004 should start first in parallel-safe slices.
- **Critical dependency:** AV3-004 precedes full backend/operator-control rollout (`AV3-005`, `AV3-006`).
- **Reliability guardrail:** AV3-011 and AV3-012 should land before broader AV3 rollout claims.

## Related docs

- `docs/AUTONOMOUS_V3_WAVE_PLAN.md`
- `docs/STATUS_BOARD_CURRENT.md`
- `docs/PLAN_NEXT_WEEK.md`
- `docs/AUTONOMOUS_MODE.md`
