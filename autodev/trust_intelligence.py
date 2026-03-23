from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .json_utils import json_dumps
from .xai_delivery_packet import build_xai_delivery_packet, write_xai_delivery_packet

TRUST_INTELLIGENCE_SCHEMA_VERSION = "av3-trust-v1"
TRUST_INTELLIGENCE_JSON = ".autodev/autonomous_trust_intelligence.json"
TRUST_INTELLIGENCE_MD = ".autodev/autonomous_trust_intelligence.md"
TRUST_ATTESTATION_JSON = ".autodev/autonomous_trust_attestation.json"
TRUST_WORKFLOW_JSON = ".autodev/trust_workflow.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_status(value: Any) -> str:
    text = str(value or "").strip()
    return text or "missing"


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"invalid_json: {exc}"
    if not isinstance(payload, dict):
        return None, "invalid_format: expected object"
    return payload, None


def _safe_load_jsonl(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    if not path.exists():
        return [], "missing"

    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if isinstance(payload, dict):
                rows.append(payload)
    except Exception as exc:
        return [], f"invalid_jsonl: {exc}"
    return rows, None


def _parse_iso8601(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _sha256_file(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _stable_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _is_present_status(status: str) -> bool:
    return status in {"ok", "not_generated", "generated"}


def _score_band(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.6:
        return "moderate"
    return "low"


def _clamp_score(score: float) -> float:
    return max(0.0, min(1.0, score))


def _normalize_percent_like(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric > 1.0:
        numeric = numeric / 100.0
    return _clamp_score(numeric)


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        out.append(text)
    return out


def _artifact_ref(name: str, details: Mapping[str, Any]) -> dict[str, Any]:
    path = Path(str(details.get("path") or "")).expanduser()
    status = _safe_status(details.get("status"))
    return {
        "name": name,
        "path": str(path),
        "status": status,
        "sha256": _sha256_file(path) if status == "ok" else "",
    }


def _collect_artifact_refs(
    run_path: Path,
    summary: Mapping[str, Any],
) -> list[dict[str, Any]]:
    artifact_status = summary.get("artifacts")
    summary_artifacts = artifact_status if isinstance(artifact_status, dict) else {}

    refs = [
        _artifact_ref(name, details)
        for name, details in sorted(summary_artifacts.items())
        if isinstance(details, dict)
    ]

    extra_artifacts = {
        "run_metadata": {
            "path": run_path / ".autodev" / "run_metadata.json",
            "status": "ok" if (run_path / ".autodev" / "run_metadata.json").exists() else "missing",
        },
        "run_trace": {
            "path": run_path / ".autodev" / "run_trace.json",
            "status": "ok" if (run_path / ".autodev" / "run_trace.json").exists() else "missing",
        },
        "experiment_log": {
            "path": run_path / ".autodev" / "experiment_log.jsonl",
            "status": "ok" if (run_path / ".autodev" / "experiment_log.jsonl").exists() else "missing",
        },
    }
    refs.extend(
        _artifact_ref(name, details)
        for name, details in sorted(extra_artifacts.items())
    )
    return refs


def _derive_latest_quality(
    report_payload: Mapping[str, Any],
    experiment_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    gate_results = report_payload.get("gate_results")
    if isinstance(gate_results, dict):
        gates = gate_results.get("gates")
        if isinstance(gates, dict):
            composite = gates.get("composite_quality")
            if isinstance(composite, dict):
                return {
                    "source": "report.gate_results.composite_quality",
                    "status": _safe_status(composite.get("status")),
                    "composite_score": composite.get("composite_score"),
                    "normalized_composite_score": _normalize_percent_like(composite.get("composite_score")),
                    "hard_blocked": bool(composite.get("hard_blocked")),
                    "components": _safe_dict(composite.get("components")),
                    "fail_reasons": [
                        str(item.get("code"))
                        for item in _safe_list(gate_results.get("fail_reasons"))
                        if isinstance(item, dict) and item.get("code")
                    ],
                }

    if experiment_rows:
        latest = experiment_rows[-1]
        decision = _safe_dict(latest.get("decision"))
        return {
            "source": "experiment_log.latest_entry",
            "status": _safe_status(decision.get("decision") or "unknown"),
            "composite_score": latest.get("composite_score"),
            "normalized_composite_score": _normalize_percent_like(latest.get("composite_score")),
            "hard_blocked": bool(latest.get("hard_blocked")),
            "components": _safe_dict(latest.get("components")),
            "decision": decision,
            "validators_failed": [
                str(item) for item in _safe_list(latest.get("validators_failed")) if item
            ],
        }

    return {
        "source": "unavailable",
        "status": "unknown",
        "composite_score": None,
        "normalized_composite_score": None,
        "hard_blocked": None,
        "components": {},
    }


def _derive_runtime_observability(
    run_trace_payload: Mapping[str, Any],
    experiment_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    events = _safe_list(run_trace_payload.get("events"))
    phases = _safe_list(run_trace_payload.get("phases"))
    llm_metrics = run_trace_payload.get("llm_metrics")
    llm_metric_rows = llm_metrics if isinstance(llm_metrics, dict) else {}

    llm_call_count = 0
    llm_retry_count = 0
    for row in llm_metric_rows.values():
        if not isinstance(row, dict):
            continue
        llm_call_count += int(row.get("call_count") or 0)
        llm_retry_count += int(row.get("retry_count") or 0)

    experiment_decisions = {"accepted": 0, "reverted": 0, "neutral": 0}
    for row in experiment_rows:
        decision = _safe_dict(row.get("decision"))
        key = str(decision.get("decision") or "").strip()
        if key in experiment_decisions:
            experiment_decisions[key] += 1

    return {
        "event_count": len(events),
        "phase_count": len(phases),
        "quality_score_events": len(
            [
                event
                for event in events
                if isinstance(event, dict)
                and str(event.get("event_type") or "") == "quality_score.computed"
            ]
        ),
        "experiment_decision_events": len(
            [
                event
                for event in events
                if isinstance(event, dict)
                and str(event.get("event_type") or "") == "experiment.decision"
            ]
        ),
        "llm_call_count": llm_call_count,
        "llm_retry_count": llm_retry_count,
        "experiment_entry_count": len(experiment_rows),
        "experiment_decisions": experiment_decisions,
    }


def _derive_evidence_integrity_signal(
    refs: list[dict[str, Any]],
    status: str,
) -> dict[str, Any]:
    by_name = {str(item.get("name")): item for item in refs}
    if status == "completed":
        required = ["report", "run_trace"]
        recommended = ["gate_results", "guard_decisions", "run_metadata", "experiment_log", "strategy_trace"]
    else:
        required = ["report", "gate_results", "guard_decisions", "run_trace"]
        recommended = ["run_metadata", "experiment_log", "strategy_trace"]
    if status == "failed":
        required.extend(["incident_packet", "ticket_draft_markdown", "ticket_draft_json"])

    missing_required = [
        name
        for name in required
        if not _is_present_status(_safe_status(_safe_dict(by_name.get(name)).get("status")))
    ]
    missing_recommended = [
        name
        for name in recommended
        if not _is_present_status(_safe_status(_safe_dict(by_name.get(name)).get("status")))
    ]

    required_total = len(required) if required else 1
    required_coverage = max(0.0, min(1.0, (required_total - len(missing_required)) / required_total))
    recommended_total = len(recommended) if recommended else 1
    recommended_coverage = max(0.0, min(1.0, (recommended_total - len(missing_recommended)) / recommended_total))
    score = _clamp_score((required_coverage * 0.8) + (recommended_coverage * 0.2))
    return {
        "score": round(score, 2),
        "status": _score_band(score),
        "required_coverage": round(required_coverage, 2),
        "recommended_coverage": round(recommended_coverage, 2),
        "missing_required": missing_required,
        "missing_recommended": missing_recommended,
    }


def _derive_validation_signal(
    summary: Mapping[str, Any],
    latest_quality: Mapping[str, Any],
    experiment_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    reasons: list[str] = []
    evidence: list[dict[str, Any]] = []
    status = str(summary.get("status") or "unknown")
    quality_status = str(latest_quality.get("status") or "unknown")
    hard_blocked = latest_quality.get("hard_blocked") is True
    preflight_status = str(summary.get("preflight_status") or "unknown")
    gate_counts = _safe_dict(summary.get("gate_counts"))
    gate_total = max(0, int(gate_counts.get("total") or 0))
    gate_pass = max(0, int(gate_counts.get("pass") or 0))
    gate_pass_rate = (gate_pass / gate_total) if gate_total else 0.0
    normalized_quality = _normalize_percent_like(latest_quality.get("normalized_composite_score"))
    if normalized_quality is None:
        normalized_quality = _normalize_percent_like(latest_quality.get("composite_score"))

    accepted = 0
    reverted = 0
    for row in experiment_rows:
        decision = _safe_dict(row.get("decision"))
        decision_value = str(decision.get("decision") or "").strip().lower()
        if decision_value == "accepted":
            accepted += 1
        elif decision_value == "reverted":
            reverted += 1
    decision_total = accepted + reverted
    repeatability = accepted / decision_total if decision_total else (1.0 if status == "completed" else 0.5)

    score = 0.0
    quality_component = normalized_quality if normalized_quality is not None else 0.4
    score += quality_component * 0.55
    evidence.append({"factor": "quality_score", "weight": 0.55, "value": round(quality_component, 2)})

    gate_component = gate_pass_rate if gate_total else (1.0 if status == "completed" else 0.4)
    score += gate_component * 0.2
    evidence.append({"factor": "gate_pass_rate", "weight": 0.2, "value": round(gate_component, 2)})

    repeatability_component = repeatability
    score += repeatability_component * 0.15
    evidence.append({"factor": "repeatability", "weight": 0.15, "value": round(repeatability_component, 2)})

    source_component = 1.0 if latest_quality.get("source") != "unavailable" else 0.35
    score += source_component * 0.1
    evidence.append({"factor": "quality_source_available", "weight": 0.1, "value": round(source_component, 2)})

    if latest_quality.get("source") == "unavailable":
        reasons.append("latest_quality_signal_unavailable")
    if hard_blocked:
        score -= 0.4
        reasons.append("quality_signal_hard_blocked")
        evidence.append({"factor": "hard_block_penalty", "weight": -0.4, "value": 1.0})
    if status == "failed":
        score -= 0.25
        reasons.append("run_failed")
        evidence.append({"factor": "run_failed_penalty", "weight": -0.25, "value": 1.0})
    if preflight_status not in {"passed", "ok"}:
        score -= 0.15
        reasons.append(f"preflight_{preflight_status}")
        evidence.append({"factor": "preflight_penalty", "weight": -0.15, "value": 1.0})
    if quality_status in {"advisory_warning", "neutral", "soft_fail"}:
        score -= 0.1
        reasons.append("quality_signal_advisory")
        evidence.append({"factor": "advisory_penalty", "weight": -0.1, "value": 1.0})

    score = _clamp_score(score)

    return {
        "score": round(score, 2),
        "status": _score_band(score),
        "latest_quality_status": quality_status,
        "quality_score_normalized": round(normalized_quality, 2) if normalized_quality is not None else None,
        "gate_pass_rate": round(gate_pass_rate, 2) if gate_total else None,
        "repeatability": round(repeatability, 2),
        "evidence": evidence,
        "reasons": reasons,
    }


def _derive_change_surface(
    summary: Mapping[str, Any],
    latest_quality: Mapping[str, Any],
) -> dict[str, Any]:
    dominant_fail_codes = _normalize_string_list(summary.get("dominant_fail_codes"))
    quality_reasons = _normalize_string_list(latest_quality.get("fail_reasons"))
    validators_failed = _normalize_string_list(latest_quality.get("validators_failed"))
    combined = [item.lower() for item in [*dominant_fail_codes, *quality_reasons, *validators_failed]]

    categories: list[str] = []
    if any("security" in item or "semgrep" in item or "bandit" in item for item in combined):
        categories.append("security")
    if any("performance" in item or "perf" in item or "regression" in item for item in combined):
        categories.append("performance")
    if any("test" in item or "pytest" in item for item in combined):
        categories.append("tests")
    if any("preflight" in item or "guard" in item or "budget" in item for item in combined):
        categories.append("operations")
    if not categories:
        categories.append("general")

    primary = categories[0] if len(categories) == 1 else "mixed"
    return {
        "primary": primary,
        "categories": categories,
        "evidence_codes": dominant_fail_codes[:10],
    }


def _derive_policy_traceability_signal(summary: Mapping[str, Any]) -> dict[str, Any]:
    status = str(summary.get("status") or "unknown")
    operator_guidance = _safe_dict(summary.get("operator_guidance"))
    incident_routing = _safe_dict(summary.get("incident_routing"))
    guidance_top = _safe_list(operator_guidance.get("top"))
    routing_primary = _safe_dict(incident_routing.get("primary"))
    guard_decision = summary.get("guard_decision")
    preflight_status = str(summary.get("preflight_status") or "unknown")
    reasons: list[str] = []
    parts: list[float] = []

    preflight_present = preflight_status not in {"", "unknown", "missing"}
    parts.append(1.0 if preflight_present else 0.0)
    if not preflight_present:
        reasons.append("preflight_status_missing")

    if status != "completed":
        guard_present = isinstance(guard_decision, dict)
        parts.append(1.0 if guard_present else 0.0)
        if not guard_present:
            reasons.append("guard_decision_missing")

    guidance_present = len(guidance_top) > 0
    parts.append(1.0 if guidance_present else 0.0)
    if not guidance_present:
        reasons.append("operator_guidance_missing")

    routing_present = bool(routing_primary.get("owner_team"))
    parts.append(1.0 if routing_present else 0.0)
    if not routing_present:
        reasons.append("incident_routing_missing")

    score = sum(parts) / len(parts) if parts else 1.0
    return {
        "score": round(score, 2),
        "status": _score_band(score),
        "reasons": reasons,
    }


def _derive_policy_enforcement_signal(
    summary: Mapping[str, Any],
    latest_quality: Mapping[str, Any],
    refs: list[dict[str, Any]],
    run_metadata_payload: Mapping[str, Any],
) -> dict[str, Any]:
    status = str(summary.get("status") or "unknown")
    preflight_status = str(summary.get("preflight_status") or "unknown")
    quality_status = str(latest_quality.get("status") or "unknown")
    hard_blocked = latest_quality.get("hard_blocked") is True
    incident_severity = str(summary.get("incident_severity") or "").strip().lower()
    gate_counts = _safe_dict(summary.get("gate_counts"))
    gate_failures = int(gate_counts.get("fail") or 0)
    change_surface = _derive_change_surface(summary, latest_quality)
    by_name = {str(item.get("name")): item for item in refs}
    policy_source = "default_autonomous_trust_policy_v1"
    if isinstance(run_metadata_payload.get("autonomous_quality_gate_policy"), dict):
        policy_source = "run_metadata.autonomous_quality_gate_policy"

    risk_tier = "low"
    if hard_blocked or status == "failed" or preflight_status not in {"passed", "ok"} or incident_severity in {"high", "critical"}:
        risk_tier = "high"
    elif gate_failures > 0 or quality_status not in {"passed", "accepted", "ok"} or change_surface.get("primary") in {"mixed", "security", "performance"}:
        risk_tier = "moderate"

    required_evidence = ["report", "run_trace"]
    if risk_tier in {"moderate", "high"}:
        required_evidence.extend(["run_metadata", "gate_results", "guard_decisions", "experiment_log"])
    if risk_tier == "high":
        required_evidence.extend(["incident_packet", "ticket_draft_markdown", "ticket_draft_json"])

    missing_evidence = [
        name
        for name in required_evidence
        if not _is_present_status(_safe_status(_safe_dict(by_name.get(name)).get("status")))
    ]

    reasons: list[str] = []
    if preflight_status not in {"passed", "ok"}:
        reasons.append(f"preflight_status={preflight_status}")
    if hard_blocked:
        reasons.append("quality_gate_hard_blocked")
    if status == "failed":
        reasons.append("run_status=failed")
    if gate_failures > 0:
        reasons.append(f"gate_failures={gate_failures}")
    if quality_status not in {"passed", "accepted", "ok"}:
        reasons.append(f"quality_status={quality_status}")
    if missing_evidence:
        reasons.append(f"missing_policy_evidence={','.join(missing_evidence)}")

    decision = "approved"
    if hard_blocked or preflight_status not in {"passed", "ok"} or (risk_tier == "high" and missing_evidence):
        decision = "blocked"
    elif risk_tier != "low" or missing_evidence or quality_status not in {"passed", "accepted", "ok"}:
        decision = "review_required"

    min_approvals = 0
    required_roles: list[str] = []
    if decision != "approved":
        min_approvals = 2 if risk_tier == "high" else 1
        required_roles = ["operator", "developer"] if risk_tier == "high" else ["operator"]

    score = 1.0
    if decision == "review_required":
        score = 0.62
    elif decision == "blocked":
        score = 0.22
    if missing_evidence:
        score = _clamp_score(score - min(0.25, len(missing_evidence) * 0.05))

    return {
        "score": round(score, 2),
        "status": _score_band(score),
        "policy_source": policy_source,
        "risk_tier": risk_tier,
        "change_surface": change_surface,
        "decision": decision,
        "required_evidence": required_evidence,
        "missing_evidence": missing_evidence,
        "reasons": reasons,
        "approval_requirements": {
            "min_approvals": min_approvals,
            "required_roles": required_roles,
            "unique_roles_required": len(required_roles),
        },
    }


def _derive_operator_readiness_signal(
    summary: Mapping[str, Any],
    refs: list[dict[str, Any]],
) -> dict[str, Any]:
    status = str(summary.get("status") or "unknown")
    operator_guidance = _safe_dict(summary.get("operator_guidance"))
    guidance_top = _safe_list(operator_guidance.get("top"))
    by_name = {str(item.get("name")): item for item in refs}
    reasons: list[str] = []
    parts: list[float] = []

    parts.append(1.0 if guidance_top else 0.0)
    if not guidance_top:
        reasons.append("operator_guidance_top_missing")

    routing_ready = bool(str(summary.get("incident_owner_team") or "").strip() not in {"", "-"})
    parts.append(1.0 if routing_ready else 0.0)
    if not routing_ready:
        reasons.append("incident_owner_team_missing")

    severity_ready = bool(str(summary.get("incident_severity") or "").strip() not in {"", "-", "unknown"})
    parts.append(1.0 if severity_ready else 0.0)
    if not severity_ready:
        reasons.append("incident_severity_missing")

    if status == "failed":
        for name in ("incident_packet", "ticket_draft_markdown", "ticket_draft_json"):
            present = _is_present_status(
                _safe_status(_safe_dict(by_name.get(name)).get("status"))
            )
            parts.append(1.0 if present else 0.0)
            if not present:
                reasons.append(f"{name}_missing")

    score = sum(parts) / len(parts) if parts else 1.0
    return {
        "score": round(score, 2),
        "status": _score_band(score),
        "reasons": reasons,
    }


def _normalize_approval_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        decision = str(row.get("decision") or "").strip().lower()
        if decision not in {"approve", "reject", "acknowledge"}:
            continue
        role = str(row.get("role") or "unknown").strip().lower() or "unknown"
        reviewer = str(row.get("reviewer") or row.get("subject") or "").strip() or "unknown"
        out.append(
            {
                "recorded_at": str(row.get("recorded_at") or row.get("timestamp") or ""),
                "decision": decision,
                "role": role,
                "reviewer": reviewer,
                "note": str(row.get("note") or "").strip(),
                "source": str(row.get("source") or "trust_approval_log").strip() or "trust_approval_log",
            }
        )
    return out


def _normalize_workflow_payload(
    workflow_payload: Mapping[str, Any],
    *,
    approval_requirements: Mapping[str, Any],
    policy_decision: str,
) -> dict[str, Any]:
    assignees_raw = workflow_payload.get("assignees")
    assignees: list[dict[str, Any]] = []
    if isinstance(assignees_raw, list):
        for row in assignees_raw:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or row.get("id") or "").strip()
            if not name:
                continue
            assignees.append(
                {
                    "name": name,
                    "role": str(row.get("role") or "").strip().lower(),
                    "contact": str(row.get("contact") or "").strip(),
                }
            )
    elif isinstance(workflow_payload.get("assignee"), str) and str(workflow_payload.get("assignee") or "").strip():
        assignees.append({"name": str(workflow_payload.get("assignee")).strip(), "role": "", "contact": ""})

    escalation_targets = _normalize_string_list(workflow_payload.get("escalation_targets"))
    due_at = str(workflow_payload.get("due_at") or "").strip()
    workflow_status = str(workflow_payload.get("status") or "").strip().lower() or "pending"
    current_owner = str(workflow_payload.get("current_owner") or "").strip() or (assignees[0]["name"] if assignees else "")
    manual_escalation_state = str(workflow_payload.get("manual_escalation_state") or "").strip().lower()
    escalation_reason = str(workflow_payload.get("escalation_reason") or "").strip()
    escalated_at = str(workflow_payload.get("escalated_at") or "").strip()
    escalated_by = str(workflow_payload.get("escalated_by") or "").strip()
    cleared_at = str(workflow_payload.get("cleared_at") or "").strip()
    cleared_by = str(workflow_payload.get("cleared_by") or "").strip()
    snoozed_until = str(workflow_payload.get("snoozed_until") or "").strip()
    last_action = _safe_dict(workflow_payload.get("last_action"))

    required_roles = _normalize_string_list(approval_requirements.get("required_roles"))
    if not assignees and required_roles and policy_decision != "approved":
        assignees = [{"name": role.title(), "role": role, "contact": ""} for role in required_roles]
        current_owner = assignees[0]["name"]

    return {
        "assignees": assignees,
        "due_at": due_at,
        "current_owner": current_owner,
        "escalation_targets": escalation_targets,
        "status": workflow_status,
        "notes": _normalize_string_list(workflow_payload.get("notes")),
        "manual_escalation_state": manual_escalation_state,
        "escalation_reason": escalation_reason,
        "escalated_at": escalated_at,
        "escalated_by": escalated_by,
        "cleared_at": cleared_at,
        "cleared_by": cleared_by,
        "snoozed_until": snoozed_until,
        "last_action": last_action,
    }


def _derive_governance_signal(
    policy_enforcement: Mapping[str, Any],
    approval_rows: list[dict[str, Any]],
    workflow_payload: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = _normalize_approval_rows(approval_rows)
    requirements = _safe_dict(policy_enforcement.get("approval_requirements"))
    required_roles = _normalize_string_list(requirements.get("required_roles"))
    min_approvals = int(requirements.get("min_approvals") or 0)
    decision = str(policy_enforcement.get("decision") or "review_required")
    workflow = _normalize_workflow_payload(
        workflow_payload,
        approval_requirements=requirements,
        policy_decision=decision,
    )

    approved = [row for row in normalized if row.get("decision") == "approve"]
    rejected = [row for row in normalized if row.get("decision") == "reject"]
    acknowledged = [row for row in normalized if row.get("decision") == "acknowledge"]
    approved_roles = {str(row.get("role") or "").strip().lower() for row in approved}
    missing_roles = [role for role in required_roles if role.lower() not in approved_roles]

    state = "not_required"
    reasons: list[str] = []
    score = 1.0
    if decision == "blocked":
        state = "blocked"
        reasons.append("policy_decision_blocked")
        score = 0.15
    elif min_approvals > 0:
        if rejected:
            state = "rejected"
            reasons.append("approval_rejected")
            score = 0.1
        elif len(approved) >= min_approvals and not missing_roles:
            state = "approved"
            score = 1.0
        else:
            state = "pending"
            score = 0.45 if approved else 0.3
            if len(approved) < min_approvals:
                reasons.append(f"approvals_needed={min_approvals - len(approved)}")
            if missing_roles:
                reasons.append(f"missing_roles={','.join(missing_roles)}")

    due_at = str(workflow.get("due_at") or "")
    due_dt = _parse_iso8601(due_at)
    now = datetime.now(timezone.utc)
    overdue = bool(due_dt and due_dt < now and state == "pending")
    escalation_state = "clear"
    manual_escalation_state = str(workflow.get("manual_escalation_state") or "").strip().lower()
    snoozed_until = str(workflow.get("snoozed_until") or "")
    snoozed_until_dt = _parse_iso8601(snoozed_until)
    if overdue:
        state = "expired"
        escalation_state = "escalated"
        reasons.append("approval_due_at_expired")
        score = min(score, 0.18)
    elif state in {"pending", "blocked"} and workflow.get("escalation_targets"):
        escalation_state = "watch"
    elif state == "rejected":
        escalation_state = "blocked"

    if manual_escalation_state == "escalated":
        escalation_state = "escalated"
        reasons.append("workflow_escalated_manually")
        score = min(score, 0.18)
    elif manual_escalation_state == "cleared" and escalation_state not in {"blocked"} and not overdue:
        escalation_state = "clear"
    if snoozed_until_dt and snoozed_until_dt > now and state in {"pending", "blocked"} and manual_escalation_state != "escalated":
        escalation_state = "snoozed"
        reasons.append("workflow_snoozed")

    next_approvers = [
        assignee
        for assignee in workflow.get("assignees") if isinstance(assignee, dict)
        if not required_roles or str(assignee.get("role") or "").strip().lower() in {role.lower() for role in missing_roles or required_roles}
    ]

    return {
        "score": round(score, 2),
        "status": _score_band(score),
        "approval_state": state,
        "min_approvals": min_approvals,
        "approved_count": len(approved),
        "rejected_count": len(rejected),
        "acknowledged_count": len(acknowledged),
        "required_roles": required_roles,
        "missing_roles": missing_roles,
        "approvals": normalized[-10:],
        "workflow": workflow,
        "due_at": due_at,
        "overdue": overdue,
        "escalation_state": escalation_state,
        "next_approvers": next_approvers,
        "current_owner": workflow.get("current_owner") or "",
        "escalation_targets": workflow.get("escalation_targets"),
        "manual_escalation_state": workflow.get("manual_escalation_state") or "",
        "escalation_reason": workflow.get("escalation_reason") or "",
        "escalated_at": workflow.get("escalated_at") or "",
        "escalated_by": workflow.get("escalated_by") or "",
        "cleared_at": workflow.get("cleared_at") or "",
        "cleared_by": workflow.get("cleared_by") or "",
        "snoozed_until": workflow.get("snoozed_until") or "",
        "last_action": workflow.get("last_action") if isinstance(workflow.get("last_action"), dict) else {},
        "reasons": reasons,
    }


def _derive_provenance_signal(
    refs: list[dict[str, Any]],
    run_metadata_payload: Mapping[str, Any],
    run_trace_payload: Mapping[str, Any],
    experiment_rows: list[dict[str, Any]],
    approval_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest = [
        {
            "name": str(item.get("name") or ""),
            "path": str(item.get("path") or ""),
            "sha256": str(item.get("sha256") or ""),
            "status": str(item.get("status") or ""),
        }
        for item in refs
        if isinstance(item, dict)
    ]
    ok_hashes = [item for item in manifest if item.get("sha256")]
    manifest_sha256 = _sha256_bytes(_stable_json_bytes(ok_hashes))
    run_metadata_sha256 = _sha256_bytes(_stable_json_bytes(_safe_dict(run_metadata_payload))) if run_metadata_payload else ""
    run_trace_sha256 = _sha256_bytes(_stable_json_bytes(_safe_dict(run_trace_payload))) if run_trace_payload else ""
    experiment_log_sha256 = _sha256_bytes(_stable_json_bytes(experiment_rows)) if experiment_rows else ""
    approval_log_sha256 = _sha256_bytes(_stable_json_bytes(approval_rows)) if approval_rows else ""
    score_parts = [
        1.0 if manifest_sha256 else 0.0,
        1.0 if run_metadata_sha256 else 0.0,
        1.0 if run_trace_sha256 else 0.0,
    ]
    score = sum(score_parts) / len(score_parts) if score_parts else 0.0
    return {
        "score": round(score, 2),
        "status": _score_band(score),
        "artifact_manifest": manifest,
        "manifest_sha256": manifest_sha256,
        "run_metadata_sha256": run_metadata_sha256,
        "run_trace_sha256": run_trace_sha256,
        "experiment_log_sha256": experiment_log_sha256,
        "approval_log_sha256": approval_log_sha256,
        "experiment_entry_count": len(experiment_rows),
        "approval_entry_count": len(approval_rows),
    }


def _derive_explainability(
    *,
    overall: Mapping[str, Any],
    validation_signal: Mapping[str, Any],
    policy_enforcement: Mapping[str, Any],
    governance: Mapping[str, Any],
    operator_readiness: Mapping[str, Any],
) -> dict[str, Any]:
    decision = str(policy_enforcement.get("decision") or "review_required")
    approval_state = str(governance.get("approval_state") or "unknown")
    risk_tier = str(policy_enforcement.get("risk_tier") or "unknown")
    quality_status = str(validation_signal.get("latest_quality_status") or "unknown")
    if overall.get("requires_human_review") is False:
        narrative = (
            f"Trust is approval-ready because validation is {quality_status}, "
            f"policy decision is {decision}, and governance state is {approval_state}."
        )
    else:
        review_reasons = _normalize_string_list(overall.get("review_reasons"))
        reason_text = ", ".join(review_reasons[:3]) if review_reasons else "policy or evidence signals remain unresolved"
        narrative = (
            f"Human review is required because the run is {risk_tier}-risk, "
            f"policy decision is {decision}, governance is {approval_state}, and {reason_text}."
        )

    return {
        "narrative": narrative,
        "evidence_tree": [
            {
                "node": "validation_signal",
                "status": validation_signal.get("status"),
                "summary": {
                    "latest_quality_status": validation_signal.get("latest_quality_status"),
                    "gate_pass_rate": validation_signal.get("gate_pass_rate"),
                    "repeatability": validation_signal.get("repeatability"),
                },
            },
            {
                "node": "policy_enforcement",
                "status": policy_enforcement.get("status"),
                "summary": {
                    "decision": policy_enforcement.get("decision"),
                    "risk_tier": policy_enforcement.get("risk_tier"),
                    "change_surface": _safe_dict(policy_enforcement.get("change_surface")).get("primary"),
                    "missing_evidence": _safe_list(policy_enforcement.get("missing_evidence")),
                },
            },
            {
                "node": "governance",
                "status": governance.get("status"),
                "summary": {
                    "approval_state": governance.get("approval_state"),
                    "approved_count": governance.get("approved_count"),
                    "required_roles": governance.get("required_roles"),
                    "missing_roles": governance.get("missing_roles"),
                },
            },
            {
                "node": "operator_readiness",
                "status": operator_readiness.get("status"),
                "summary": {
                    "reasons": operator_readiness.get("reasons"),
                },
            },
        ],
    }


def _derive_overall_trust_signal(
    *,
    summary: Mapping[str, Any],
    components: Mapping[str, Mapping[str, Any]],
    latest_quality: Mapping[str, Any],
    runtime_observability: Mapping[str, Any],
) -> dict[str, Any]:
    weights = {
        "evidence_integrity": 0.2,
        "validation_signal": 0.32,
        "policy_traceability": 0.1,
        "operator_readiness": 0.13,
        "policy_enforcement": 0.15,
        "governance": 0.1,
    }
    weighted_total = 0.0
    breakdown: list[dict[str, Any]] = []
    for key, weight in weights.items():
        component = _safe_dict(components.get(key))
        component_score = _clamp_score(float(component.get("score") or 0.0))
        weighted_total += component_score * weight
        breakdown.append(
            {
                "signal": key,
                "weight": weight,
                "score": round(component_score, 2),
                "weighted_score": round(component_score * weight, 2),
                "status": component.get("status"),
            }
        )

    diagnostics = _safe_list(summary.get("diagnostics"))
    warnings = _safe_list(summary.get("warnings"))
    event_count = int(runtime_observability.get("event_count") or 0)
    llm_call_count = int(runtime_observability.get("llm_call_count") or 0)
    quality_status = str(latest_quality.get("status") or "unknown")
    hard_blocked = latest_quality.get("hard_blocked") is True
    status = str(summary.get("status") or "unknown")
    preflight_status = str(summary.get("preflight_status") or "unknown")

    review_reasons: list[str] = []
    if preflight_status not in {"passed", "ok"}:
        review_reasons.append(f"preflight_status={preflight_status}")
    if hard_blocked:
        review_reasons.append("quality_gate_hard_blocked")
    if status == "failed":
        review_reasons.append("run_status=failed")
    evidence_integrity = _safe_dict(components.get("evidence_integrity"))
    missing_required = _safe_list(evidence_integrity.get("missing_required"))
    if missing_required:
        review_reasons.append(f"missing_required_artifacts={','.join(str(item) for item in missing_required)}")
    if diagnostics and status != "completed":
        review_reasons.append(f"diagnostics_present={len(diagnostics)}")
    if warnings and status != "completed":
        review_reasons.append(f"warnings_present={len(warnings)}")
    if event_count <= 0 and llm_call_count > 0:
        review_reasons.append("run_trace_events_missing")
    if quality_status not in {"passed", "accepted"}:
        review_reasons.append(f"latest_quality_status={quality_status}")
    policy_enforcement = _safe_dict(components.get("policy_enforcement"))
    policy_decision = str(policy_enforcement.get("decision") or "").strip()
    if policy_decision and policy_decision != "approved":
        review_reasons.append(f"policy_decision={policy_decision}")
    governance = _safe_dict(components.get("governance"))
    approval_state = str(governance.get("approval_state") or "").strip()
    if approval_state and approval_state not in {"approved", "not_required"}:
        review_reasons.append(f"approval_state={approval_state}")

    score = _clamp_score(weighted_total)
    if diagnostics and status != "completed":
        score = _clamp_score(score - min(0.15, len(diagnostics) * 0.03))
    if warnings and status != "completed":
        score = _clamp_score(score - min(0.1, len(warnings) * 0.02))
    status_band = _score_band(score)
    requires_human_review = bool(review_reasons) or score < 0.85 or status_band != "high"

    explanation = "Autonomous approval-ready." if not requires_human_review else "Human review required because evidence, policy, or governance signals remain unresolved."
    return {
        "score": round(score, 2),
        "status": status_band,
        "requires_human_review": requires_human_review,
        "review_reasons": review_reasons,
        "explanation": explanation,
        "breakdown": breakdown,
    }


def build_trust_intelligence_packet(
    run_dir: str | Path,
    *,
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    run_path = Path(run_dir).expanduser().resolve()
    artifacts_dir = run_path / ".autodev"

    report_payload, _ = _safe_load_json(artifacts_dir / "autonomous_report.json")
    run_trace_payload, _ = _safe_load_json(artifacts_dir / "run_trace.json")
    run_metadata_payload, _ = _safe_load_json(artifacts_dir / "run_metadata.json")
    workflow_payload, _ = _safe_load_json(artifacts_dir / Path(TRUST_WORKFLOW_JSON).name)
    experiment_rows, _ = _safe_load_jsonl(artifacts_dir / "experiment_log.jsonl")
    approval_rows, _ = _safe_load_jsonl(artifacts_dir / "trust_approvals.jsonl")

    artifact_refs = _collect_artifact_refs(run_path, summary)
    latest_quality = _derive_latest_quality(_safe_dict(report_payload), experiment_rows)
    runtime_observability = _derive_runtime_observability(
        _safe_dict(run_trace_payload),
        experiment_rows,
    )

    evidence_integrity = _derive_evidence_integrity_signal(
        artifact_refs,
        str(summary.get("status") or "unknown"),
    )
    validation_signal = _derive_validation_signal(summary, latest_quality, experiment_rows)
    policy_traceability = _derive_policy_traceability_signal(summary)
    operator_readiness = _derive_operator_readiness_signal(summary, artifact_refs)
    policy_enforcement = _derive_policy_enforcement_signal(
        summary,
        latest_quality,
        artifact_refs,
        _safe_dict(run_metadata_payload),
    )
    governance = _derive_governance_signal(policy_enforcement, approval_rows, _safe_dict(workflow_payload))
    provenance_signal = _derive_provenance_signal(
        artifact_refs,
        _safe_dict(run_metadata_payload),
        _safe_dict(run_trace_payload),
        experiment_rows,
        approval_rows,
    )
    component_signals = {
        "evidence_integrity": evidence_integrity,
        "validation_signal": validation_signal,
        "policy_traceability": policy_traceability,
        "operator_readiness": operator_readiness,
        "policy_enforcement": policy_enforcement,
        "governance": governance,
    }
    overall = _derive_overall_trust_signal(
        summary=summary,
        components=component_signals,
        latest_quality=latest_quality,
        runtime_observability=runtime_observability,
    )

    operator_guidance = _safe_dict(summary.get("operator_guidance"))
    incident_routing = _safe_dict(summary.get("incident_routing"))
    top_guidance = _safe_list(operator_guidance.get("top"))
    primary_routing = _safe_dict(incident_routing.get("primary"))
    explainability = _derive_explainability(
        overall=overall,
        validation_signal=validation_signal,
        policy_enforcement=policy_enforcement,
        governance=governance,
        operator_readiness=operator_readiness,
    )

    packet = {
        "schema_version": TRUST_INTELLIGENCE_SCHEMA_VERSION,
        "mode": "autonomous_v1_trust_intelligence",
        "generated_at": _utc_now(),
        "run_dir": str(run_path),
        "latest_run": _safe_dict(summary.get("latest_run")),
        "status": summary.get("status"),
        "summary_snapshot": {
            "preflight_status": summary.get("preflight_status"),
            "gate_counts": summary.get("gate_counts"),
            "dominant_fail_codes": summary.get("dominant_fail_codes"),
            "guard_decision": summary.get("guard_decision"),
            "guard_decision_source": summary.get("guard_decision_source"),
            "guard_decisions_total": summary.get("guard_decisions_total"),
            "budget_guard_status": summary.get("budget_guard_status"),
            "budget_guard_decision": summary.get("budget_guard_decision"),
            "budget_guard_reason_codes": summary.get("budget_guard_reason_codes"),
            "operator_guidance_top": top_guidance,
            "incident_owner_team": summary.get("incident_owner_team"),
            "incident_severity": summary.get("incident_severity"),
            "incident_target_sla": summary.get("incident_target_sla"),
            "incident_escalation_class": summary.get("incident_escalation_class"),
            "warnings": summary.get("warnings"),
        },
        "artifacts": {
            "refs": artifact_refs,
            "total": len(artifact_refs),
            "ok_count": len([item for item in artifact_refs if item.get("status") == "ok"]),
        },
        "trust_signals": {
            "overall": overall,
            "evidence_integrity": evidence_integrity,
            "validation_signal": validation_signal,
            "policy_traceability": policy_traceability,
            "operator_readiness": operator_readiness,
            "policy_enforcement": policy_enforcement,
            "governance": governance,
            "provenance": {
                "score": provenance_signal.get("score"),
                "status": provenance_signal.get("status"),
            },
        },
        "policy": policy_enforcement,
        "governance": governance,
        "latest_quality": latest_quality,
        "runtime_observability": runtime_observability,
        "explainability": explainability,
        "decision_trace": {
            "latest_strategy": summary.get("latest_strategy"),
            "guard_decision": summary.get("guard_decision"),
            "guard_decision_source": summary.get("guard_decision_source"),
            "guard_decisions_total": summary.get("guard_decisions_total"),
            "budget_guard_status": summary.get("budget_guard_status"),
            "budget_guard_decision": summary.get("budget_guard_decision"),
            "budget_guard_reason_codes": summary.get("budget_guard_reason_codes"),
            "dominant_fail_codes": summary.get("dominant_fail_codes"),
            "operator_guidance_top": top_guidance,
            "incident_routing_primary": primary_routing,
        },
        "operator_next": {
            "owner_team": primary_routing.get("owner_team") or "-",
            "severity": primary_routing.get("severity") or "-",
            "target_sla": primary_routing.get("target_sla") or "-",
            "escalation_class": primary_routing.get("escalation_class") or "-",
            "review_reasons": _safe_list(overall.get("review_reasons")),
            "policy_decision": policy_enforcement.get("decision"),
            "risk_tier": policy_enforcement.get("risk_tier"),
            "approval_state": governance.get("approval_state"),
            "current_owner": governance.get("current_owner"),
            "due_at": governance.get("due_at"),
            "escalation_state": governance.get("escalation_state"),
            "top_actions": [
                {
                    "code": item.get("code"),
                    "title": item.get("title"),
                    "actions": _safe_list(item.get("actions")),
                    "playbook_url": item.get("playbook_url"),
                }
                for item in top_guidance[:3]
                if isinstance(item, dict)
            ],
        },
        "provenance": {
            "run_metadata": _safe_dict(run_metadata_payload),
            "run_trace_available": bool(run_trace_payload),
            "experiment_log_available": len(experiment_rows) > 0,
            "approval_log_available": len(approval_rows) > 0,
            "workflow_available": bool(workflow_payload),
            "artifact_manifest": provenance_signal.get("artifact_manifest"),
            "manifest_sha256": provenance_signal.get("manifest_sha256"),
            "run_metadata_sha256": provenance_signal.get("run_metadata_sha256"),
            "run_trace_sha256": provenance_signal.get("run_trace_sha256"),
            "experiment_log_sha256": provenance_signal.get("experiment_log_sha256"),
            "approval_log_sha256": provenance_signal.get("approval_log_sha256"),
        },
        "warnings": [str(item) for item in _safe_list(summary.get("warnings")) if item],
    }
    attestation_payload = {
        "schema_version": "autonomous_trust_attestation_v1",
        "generated_at": packet.get("generated_at"),
        "run_dir": packet.get("run_dir"),
        "manifest_sha256": provenance_signal.get("manifest_sha256"),
        "run_metadata_sha256": provenance_signal.get("run_metadata_sha256"),
        "run_trace_sha256": provenance_signal.get("run_trace_sha256"),
        "experiment_log_sha256": provenance_signal.get("experiment_log_sha256"),
        "approval_log_sha256": provenance_signal.get("approval_log_sha256"),
        "policy_decision": policy_enforcement.get("decision"),
        "risk_tier": policy_enforcement.get("risk_tier"),
        "approval_state": governance.get("approval_state"),
        "current_owner": governance.get("current_owner"),
        "due_at": governance.get("due_at"),
        "escalation_state": governance.get("escalation_state"),
    }
    attestation_payload["packet_sha256"] = _sha256_bytes(_stable_json_bytes(packet))
    packet["attestation"] = attestation_payload
    return packet


def build_xai_delivery_packet_from_trust(packet: Mapping[str, Any]) -> dict[str, Any]:
    latest_run = _safe_dict(packet.get("latest_run"))
    trust_signals = _safe_dict(packet.get("trust_signals"))
    overall = _safe_dict(trust_signals.get("overall"))
    latest_quality = _safe_dict(packet.get("latest_quality"))
    summary_snapshot = _safe_dict(packet.get("summary_snapshot"))
    operator_next = _safe_dict(packet.get("operator_next"))
    artifacts = _safe_dict(packet.get("artifacts"))
    refs = _safe_list(artifacts.get("refs"))

    repo_name = Path(str(packet.get("run_dir") or "")).name or "autodev-run"
    summary = (
        f"Run {latest_run.get('run_id') or '-'} trust={overall.get('status') or 'unknown'} "
        f"score={overall.get('score') or 0} status={packet.get('status') or 'unknown'}"
    )
    files = [str(item.get("path")) for item in refs if isinstance(item, dict) and item.get("status") == "ok"][:10]

    validations = [
        f"trust_status={overall.get('status') or 'unknown'}",
        f"evidence_integrity={_safe_dict(trust_signals.get('evidence_integrity')).get('status') or 'unknown'}",
        f"latest_quality_status={latest_quality.get('status') or 'unknown'}",
        f"incident_owner_team={operator_next.get('owner_team') or '-'}",
    ]

    packet_validation = {
        "status": "ready" if overall.get("requires_human_review") is False else "review_required",
        "notes": [
            f"overall_trust_score={overall.get('score') or 0}",
            f"gate_fail_count={_safe_dict(summary_snapshot.get('gate_counts')).get('fail') or 0}",
        ],
    }

    repo_payload = {
        "name": repo_name,
        "xai_capabilities": [
            "trust_intelligence_packet",
            "operator_guidance",
            "incident_routing",
            "quality_gate_summary",
            "run_trace_telemetry",
            "experiment_decision_log",
        ],
        "endpoints": [
            "autodev autonomous summary --run-dir <path>",
            "autodev autonomous triage-summary --run-dir <path>",
            "autodev autonomous trust-summary --run-dir <path>",
        ],
        "files": files,
        "validations": validations,
    }

    return build_xai_delivery_packet(
        summary=summary,
        repositories=[repo_payload],
        validation=packet_validation,
        artifacts=[
            {"label": str(item.get("name") or "-"), "path": str(item.get("path") or "-")}
            for item in refs[:10]
            if isinstance(item, dict)
        ],
    )


def build_trust_summary(packet: Mapping[str, Any]) -> dict[str, Any]:
    trust_signals = _safe_dict(packet.get("trust_signals"))
    overall = _safe_dict(trust_signals.get("overall"))
    latest_quality = _safe_dict(packet.get("latest_quality"))
    summary_snapshot = _safe_dict(packet.get("summary_snapshot"))
    operator_next = _safe_dict(packet.get("operator_next"))
    runtime_observability = _safe_dict(packet.get("runtime_observability"))
    policy = _safe_dict(packet.get("policy"))
    governance = _safe_dict(packet.get("governance"))
    explainability = _safe_dict(packet.get("explainability"))
    attestation = _safe_dict(packet.get("attestation"))
    decision_trace = _safe_dict(packet.get("decision_trace"))
    guard_decision = _safe_dict(decision_trace.get("guard_decision"))
    budget_guard_decision = _safe_dict(summary_snapshot.get("budget_guard_decision"))
    review_reasons = _safe_list(overall.get("review_reasons"))
    quality_status = str(latest_quality.get("status") or "unknown")
    residual_risk_level = "low"
    if overall.get("requires_human_review") is True:
        residual_risk_level = "high"
    elif quality_status not in {"passed", "ok"}:
        residual_risk_level = "moderate"

    residual_risk_summary = (
        "Human review remains required before closure."
        if overall.get("requires_human_review") is True
        else (
            f"Latest quality signal remains {quality_status}."
            if quality_status not in {"passed", "ok"}
            else "No material residual risk detected from current trust signals."
        )
    )
    if review_reasons:
        residual_risk_summary = f"{residual_risk_summary} Reasons: {', '.join(str(item) for item in review_reasons[:3])}."

    return {
        "status": packet.get("status"),
        "trust_status": overall.get("status"),
        "trust_score": overall.get("score"),
        "requires_human_review": overall.get("requires_human_review"),
        "human_review_reasons": review_reasons,
        "trust_explanation": overall.get("explanation"),
        "residual_risk_level": residual_risk_level,
        "residual_risk_summary": residual_risk_summary,
        "risk_tier": policy.get("risk_tier"),
        "policy_decision": policy.get("decision"),
        "policy_change_surface": _safe_dict(policy.get("change_surface")).get("primary"),
        "policy_missing_evidence": _safe_list(policy.get("missing_evidence")),
        "approval_state": governance.get("approval_state"),
        "approval_required_roles": _safe_list(governance.get("required_roles")),
        "approval_missing_roles": _safe_list(governance.get("missing_roles")),
        "approved_count": governance.get("approved_count"),
        "min_approvals": governance.get("min_approvals"),
        "approval_due_at": governance.get("due_at"),
        "approval_overdue": governance.get("overdue"),
        "approval_escalation_state": governance.get("escalation_state"),
        "approval_manual_escalation_state": governance.get("manual_escalation_state"),
        "approval_escalation_reason": governance.get("escalation_reason"),
        "approval_current_owner": governance.get("current_owner"),
        "approval_next_approvers": _safe_list(governance.get("next_approvers")),
        "approval_snoozed_until": governance.get("snoozed_until"),
        "approval_last_action": _safe_dict(governance.get("last_action")),
        "explainability_narrative": explainability.get("narrative"),
        "attestation_packet_sha256": attestation.get("packet_sha256"),
        "latest_quality_status": latest_quality.get("status"),
        "latest_quality_score": latest_quality.get("composite_score"),
        "incident_owner_team": operator_next.get("owner_team"),
        "incident_severity": operator_next.get("severity"),
        "incident_target_sla": operator_next.get("target_sla"),
        "preflight_status": summary_snapshot.get("preflight_status"),
        "guard_decision_action": guard_decision.get("decision"),
        "guard_decision_reason_code": guard_decision.get("reason_code"),
        "guard_decision_source": decision_trace.get("guard_decision_source") or summary_snapshot.get("guard_decision_source"),
        "guard_decisions_total": decision_trace.get("guard_decisions_total") or summary_snapshot.get("guard_decisions_total"),
        "budget_guard_status": summary_snapshot.get("budget_guard_status"),
        "budget_guard_action": budget_guard_decision.get("decision"),
        "budget_guard_reason_code": budget_guard_decision.get("reason_code"),
        "budget_guard_reason_codes": _safe_list(summary_snapshot.get("budget_guard_reason_codes")),
        "event_count": runtime_observability.get("event_count"),
        "llm_call_count": runtime_observability.get("llm_call_count"),
        "experiment_entry_count": runtime_observability.get("experiment_entry_count"),
    }


def render_trust_intelligence_packet(
    packet: Mapping[str, Any],
    *,
    output_format: str = "markdown",
) -> str:
    if output_format == "json":
        return json_dumps(dict(packet))

    trust_signals = _safe_dict(packet.get("trust_signals"))
    overall = _safe_dict(trust_signals.get("overall"))
    latest_quality = _safe_dict(packet.get("latest_quality"))
    operator_next = _safe_dict(packet.get("operator_next"))
    decision_trace = _safe_dict(packet.get("decision_trace"))
    policy = _safe_dict(packet.get("policy"))
    governance = _safe_dict(packet.get("governance"))
    explainability = _safe_dict(packet.get("explainability"))
    attestation = _safe_dict(packet.get("attestation"))
    guidance = _safe_list(operator_next.get("top_actions"))

    lines = [
        "# Autonomous Trust Intelligence",
        f"- run_dir: {packet.get('run_dir')}",
        f"- status: {packet.get('status')}",
        f"- trust_status: {overall.get('status', 'unknown')}",
        f"- trust_score: {overall.get('score', 0)}",
        f"- requires_human_review: {overall.get('requires_human_review', True)}",
        f"- trust_explanation: {overall.get('explanation', '-')}",
        f"- explainability_narrative: {explainability.get('narrative', '-')}",
        f"- latest_quality_source: {latest_quality.get('source', 'unavailable')}",
        f"- latest_quality_status: {latest_quality.get('status', 'unknown')}",
        f"- latest_quality_score: {latest_quality.get('composite_score', '-')}",
        f"- risk_tier: {policy.get('risk_tier', '-')}",
        f"- policy_decision: {policy.get('decision', '-')}",
        f"- approval_state: {governance.get('approval_state', '-')}",
        f"- approval_current_owner: {governance.get('current_owner', '-')}",
        f"- approval_due_at: {governance.get('due_at', '-')}",
        f"- approval_escalation_state: {governance.get('escalation_state', '-')}",
        f"- incident_owner_team: {operator_next.get('owner_team', '-')}",
        f"- incident_severity: {operator_next.get('severity', '-')}",
        f"- incident_target_sla: {operator_next.get('target_sla', '-')}",
        f"- incident_escalation_class: {operator_next.get('escalation_class', '-')}",
        f"- attestation_packet_sha256: {attestation.get('packet_sha256', '-')}",
    ]

    for key in (
        "evidence_integrity",
        "validation_signal",
        "policy_traceability",
        "operator_readiness",
        "policy_enforcement",
        "governance",
    ):
        signal = _safe_dict(trust_signals.get(key))
        lines.append(
            f"- {key}: {signal.get('status', 'unknown')} (score={signal.get('score', 0)})"
        )

    latest_strategy = decision_trace.get("latest_strategy")
    if isinstance(latest_strategy, dict):
        lines.append(f"- latest_strategy: {latest_strategy.get('name', '-')}")
    else:
        lines.append("- latest_strategy: -")

    guard_decision = decision_trace.get("guard_decision")
    if isinstance(guard_decision, dict):
        lines.append(
            f"- guard_decision: {guard_decision.get('decision', '-')} "
            f"({guard_decision.get('reason_code', '-')})"
        )
    else:
        lines.append("- guard_decision: -")

    budget_guard_decision = decision_trace.get("budget_guard_decision")
    if isinstance(budget_guard_decision, dict):
        lines.append(
            f"- budget_guard_decision: {budget_guard_decision.get('decision', '-')} "
            f"({budget_guard_decision.get('reason_code', '-')})"
        )
    else:
        lines.append("- budget_guard_decision: -")

    budget_guard_reason_codes = _safe_list(decision_trace.get("budget_guard_reason_codes"))
    if budget_guard_reason_codes:
        lines.append(
            "- budget_guard_reason_codes: "
            + ", ".join(str(item) for item in budget_guard_reason_codes if item)
        )
    else:
        lines.append("- budget_guard_reason_codes: -")

    if guidance:
        lines.append("- top_actions:")
        for item in guidance:
            if not isinstance(item, dict):
                continue
            actions = [
                str(action)
                for action in _safe_list(item.get("actions"))
                if action
            ]
            lines.append(
                f"  - {item.get('code', '-')}: {'; '.join(actions) or '-'}"
            )
    else:
        lines.append("- top_actions: -")

    review_reasons = [str(item) for item in _safe_list(overall.get("review_reasons")) if item]
    if review_reasons:
        lines.append("- human_review_reasons:")
        for item in review_reasons:
            lines.append(f"  - {item}")
    else:
        lines.append("- human_review_reasons: -")

    return "\n".join(lines)


def persist_trust_intelligence_artifacts(
    run_dir: str | Path,
    packet: Mapping[str, Any],
) -> dict[str, str]:
    run_path = Path(run_dir).expanduser().resolve()
    artifacts_dir = run_path / ".autodev"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    trust_json = artifacts_dir / Path(TRUST_INTELLIGENCE_JSON).name
    trust_md = artifacts_dir / Path(TRUST_INTELLIGENCE_MD).name
    trust_attestation = artifacts_dir / Path(TRUST_ATTESTATION_JSON).name
    trust_json.write_text(json_dumps(dict(packet)), encoding="utf-8")
    trust_md.write_text(
        render_trust_intelligence_packet(packet, output_format="markdown"),
        encoding="utf-8",
    )
    trust_attestation.write_text(
        json_dumps(_safe_dict(packet.get("attestation"))),
        encoding="utf-8",
    )

    xai_packet = build_xai_delivery_packet_from_trust(packet)
    xai_json = write_xai_delivery_packet(
        run_dir=artifacts_dir,
        packet=xai_packet,
        output_format="json",
    )
    xai_md = write_xai_delivery_packet(
        run_dir=artifacts_dir,
        packet=xai_packet,
        output_format="markdown",
    )

    return {
        "trust_json": str(trust_json),
        "trust_markdown": str(trust_md),
        "trust_attestation": str(trust_attestation),
        "xai_json": str(xai_json),
        "xai_markdown": str(xai_md),
    }
