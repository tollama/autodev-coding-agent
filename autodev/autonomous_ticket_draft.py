from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .json_utils import json_dumps

AUTONOMOUS_INCIDENT_PACKET_JSON = ".autodev/autonomous_incident_packet.json"
AUTONOMOUS_REPORT_JSON = ".autodev/autonomous_report.json"
AUTONOMOUS_TICKET_DRAFT_MD = ".autodev/autonomous_ticket_draft.md"
AUTONOMOUS_TICKET_DRAFT_JSON = ".autodev/autonomous_ticket_draft.json"
SUPPORTED_TICKET_DRAFT_FORMATS = ("markdown", "json")


def _safe_load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # pragma: no cover - defensive parsing branch
        return None, f"invalid_json: {e}"
    if not isinstance(payload, dict):
        return None, "invalid_format: expected object"
    return payload, None


def _safe_str(value: Any, fallback: str = "-") -> str:
    text = str(value).strip() if value is not None else ""
    return text or fallback


def _fallback_actions() -> list[str]:
    return [
        "Inspect .autodev/autonomous_report.json for gate and guard outcomes.",
        "Re-run `autodev autonomous summary --run-dir <path> --format text` to confirm the latest failure context.",
        "Open docs/AUTONOMOUS_FAILURE_PLAYBOOK.md and follow the matching failure-code playbook.",
    ]


def build_autonomous_ticket_draft(run_dir: str | Path) -> dict[str, Any]:
    run_path = Path(run_dir).expanduser().resolve()
    incident_path = run_path / AUTONOMOUS_INCIDENT_PACKET_JSON
    report_path = run_path / AUTONOMOUS_REPORT_JSON

    incident_packet, incident_error = _safe_load_json(incident_path)
    report_payload, report_error = _safe_load_json(report_path)

    diagnostics: list[dict[str, str]] = []
    if incident_error is not None:
        diagnostics.append(
            {
                "level": "warning",
                "code": "ticket_draft.incident_packet_unavailable",
                "message": f"incident packet unavailable: {incident_error}",
            }
        )
    if report_error is not None:
        diagnostics.append(
            {
                "level": "warning",
                "code": "ticket_draft.report_unavailable",
                "message": f"autonomous report unavailable: {report_error}",
            }
        )

    run_summary = incident_packet.get("run_summary") if isinstance(incident_packet, dict) and isinstance(incident_packet.get("run_summary"), dict) else {}
    report_routing = report_payload.get("incident_routing") if isinstance(report_payload, dict) and isinstance(report_payload.get("incident_routing"), dict) else {}
    packet_routing = incident_packet.get("incident_routing") if isinstance(incident_packet, dict) and isinstance(incident_packet.get("incident_routing"), dict) else {}
    routing = packet_routing or report_routing
    routing_primary = routing.get("primary") if isinstance(routing.get("primary"), dict) else {}

    run_id = _safe_str(
        run_summary.get("run_id")
        or (report_payload.get("run_id") if isinstance(report_payload, dict) else None),
        fallback="unknown-run",
    )
    status = _safe_str(
        run_summary.get("status")
        or (report_payload.get("status") if isinstance(report_payload, dict) else None)
        or (
            "failed"
            if isinstance(report_payload, dict) and report_payload.get("ok") is False
            else "unknown"
        ),
        fallback="unknown",
    )
    failure_reason = _safe_str(
        run_summary.get("failure_reason")
        or (report_payload.get("failure_reason") if isinstance(report_payload, dict) else None),
        fallback="autonomous failure requires triage",
    )

    severity = _safe_str(routing_primary.get("severity"), fallback="medium")
    owner_team = _safe_str(routing_primary.get("owner_team"), fallback="Autonomy On-Call")
    target_sla = _safe_str(routing_primary.get("target_sla"), fallback="12h")

    failure_codes = incident_packet.get("failure_codes") if isinstance(incident_packet, dict) and isinstance(incident_packet.get("failure_codes"), dict) else {}
    typed_codes = [
        str(item).strip()
        for item in (failure_codes.get("typed_codes") if isinstance(failure_codes.get("typed_codes"), list) else [])
        if str(item).strip()
    ]
    lead_code = typed_codes[0] if typed_codes else "autonomous.failure"

    title = f"[AutoDev][{severity}] {lead_code} on {run_id}" if lead_code else f"[AutoDev][{severity}] Autonomous run failure on {run_id}"

    reproduction = incident_packet.get("reproduction") if isinstance(incident_packet, dict) and isinstance(incident_packet.get("reproduction"), dict) else {}
    artifact_paths = reproduction.get("artifact_paths") if isinstance(reproduction.get("artifact_paths"), dict) else {}

    repro_steps: list[str] = [
        f"Open run directory: `{run_path}`.",
        "Inspect `.autodev/autonomous_report.json` for stop reason, gate failures, and guard outcomes.",
    ]
    if incident_path.exists():
        repro_steps.append("Inspect `.autodev/autonomous_incident_packet.json` for typed/root-cause codes and routing.")
    if typed_codes:
        repro_steps.append(f"Validate failing code path(s): {', '.join(typed_codes[:3])}.")

    evidence: list[dict[str, str]] = [
        {"label": "run_dir", "path": str(run_path)},
        {"label": "autonomous_report", "path": AUTONOMOUS_REPORT_JSON},
    ]
    if incident_path.exists():
        evidence.append({"label": "incident_packet", "path": AUTONOMOUS_INCIDENT_PACKET_JSON})
    for key in sorted(artifact_paths.keys()):
        value = _safe_str(artifact_paths.get(key), fallback="")
        if not value or value == "-":
            continue
        evidence.append({"label": str(key), "path": value})

    operator_guidance = incident_packet.get("operator_guidance") if isinstance(incident_packet, dict) and isinstance(incident_packet.get("operator_guidance"), dict) else {}
    top_actions = operator_guidance.get("top_actions") if isinstance(operator_guidance.get("top_actions"), list) else []
    next_actions = [
        _safe_str(item.get("action"), fallback="")
        for item in top_actions
        if isinstance(item, dict) and _safe_str(item.get("action"), fallback="") != ""
    ]
    if not next_actions and isinstance(report_payload, dict) and isinstance(report_payload.get("operator_guidance"), dict):
        report_top = report_payload["operator_guidance"].get("top") if isinstance(report_payload["operator_guidance"].get("top"), list) else []
        for item in report_top:
            if not isinstance(item, dict):
                continue
            actions = item.get("actions") if isinstance(item.get("actions"), list) else []
            if actions:
                next_actions.append(_safe_str(actions[0], fallback=""))
    if not next_actions:
        next_actions = _fallback_actions()

    return {
        "schema_version": "av3-012-v1",
        "mode": "autonomous_ticket_draft_v1",
        "run_dir": str(run_path),
        "title": title,
        "status": status,
        "failure_reason": failure_reason,
        "severity": severity,
        "owner_team": owner_team,
        "target_sla": target_sla,
        "typed_codes": typed_codes,
        "repro_steps": repro_steps,
        "evidence": evidence,
        "suggested_next_actions": next_actions,
        "source_artifacts": {
            "incident_packet": {"path": str(incident_path), "status": "ok" if incident_error is None else incident_error},
            "report": {"path": str(report_path), "status": "ok" if report_error is None else report_error},
        },
        "diagnostics": diagnostics,
    }


def render_ticket_draft(draft: dict[str, Any], output_format: str) -> str:
    if output_format == "json":
        return json_dumps(draft)
    if output_format != "markdown":
        raise ValueError(
            f"unsupported ticket draft format: {output_format} "
            f"(expected one of: {', '.join(SUPPORTED_TICKET_DRAFT_FORMATS)})"
        )

    typed_codes = draft.get("typed_codes") if isinstance(draft.get("typed_codes"), list) else []
    repro_steps = draft.get("repro_steps") if isinstance(draft.get("repro_steps"), list) else []
    evidence = draft.get("evidence") if isinstance(draft.get("evidence"), list) else []
    next_actions = draft.get("suggested_next_actions") if isinstance(draft.get("suggested_next_actions"), list) else []
    diagnostics = draft.get("diagnostics") if isinstance(draft.get("diagnostics"), list) else []

    lines = [
        f"# {draft.get('title', 'AutoDev Ticket Draft')}",
        "",
        "## Triage",
        f"- Severity: **{draft.get('severity', '-')}**",
        f"- Owner Team: **{draft.get('owner_team', '-')}**",
        f"- Target SLA: **{draft.get('target_sla', '-')}**",
        f"- Status: `{draft.get('status', '-')}`",
        f"- Failure Reason: `{draft.get('failure_reason', '-')}`",
        "",
        "## Reproduction Steps",
    ]

    if repro_steps:
        for step in repro_steps:
            lines.append(f"1. {step}")
    else:
        lines.append("1. Reproduction details unavailable; inspect run artifacts directly.")

    lines.extend([
        "",
        "## Evidence",
    ])
    if evidence:
        for item in evidence:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {item.get('label', '-')}: `{item.get('path', '-')}`")
    else:
        lines.append("- -")

    lines.extend([
        "",
        "## Suggested Next Actions",
    ])
    if next_actions:
        for action in next_actions:
            lines.append(f"- {action}")
    else:
        lines.append("- -")

    lines.extend([
        "",
        "## Failure Codes",
        f"- Typed Codes: {', '.join(str(item) for item in typed_codes) if typed_codes else '-'}",
    ])

    if diagnostics:
        lines.extend([
            "",
            "## Diagnostics",
        ])
        for item in diagnostics:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {item.get('code', '-')}: {item.get('message', '-')}")

    return "\n".join(lines)


def write_ticket_draft(run_dir: str | Path, output_format: str) -> tuple[dict[str, Any], Path, str]:
    run_path = Path(run_dir).expanduser().resolve()
    artifacts_dir = run_path / ".autodev"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    draft = build_autonomous_ticket_draft(run_path)
    rendered = render_ticket_draft(draft, output_format)

    out_path = artifacts_dir / (
        "autonomous_ticket_draft.md" if output_format == "markdown" else "autonomous_ticket_draft.json"
    )
    out_path.write_text(rendered, encoding="utf-8")
    return draft, out_path, rendered
