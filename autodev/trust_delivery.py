from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib import request

TRUST_DELIVERY_AUDIT_JSONL = ".autodev/trust_delivery_audit.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_targets(raw: Any) -> list[str]:
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else ["stdout"]
    if not isinstance(raw, list):
        return ["stdout"]
    out: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out or ["stdout"]


def _render_markdown_preview(mode: str, payload: Mapping[str, Any]) -> str:
    if mode == "run":
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        return (
            "# Trust Delivery\n\n"
            f"- mode: run\n"
            f"- run_id: {payload.get('run_id') or '-'}\n"
            f"- trust_status: {summary.get('trust_status') or '-'}\n"
            f"- trust_score: {summary.get('trust_score') or '-'}\n"
            f"- policy_decision: {summary.get('policy_decision') or '-'}\n"
            f"- approval_state: {summary.get('approval_state') or '-'}\n"
        )
    if mode == "events":
        rows = payload.get("events") if isinstance(payload.get("events"), list) else []
        lines = ["# Trust Delivery", "", "- mode: events", "", "## Events"]
        if not rows:
            lines.append("- none")
        for row in rows[:20]:
            if not isinstance(row, dict):
                continue
            lines.append(f"- {row.get('timestamp') or '-'} {row.get('type') or '-'} run={row.get('run_id') or '-'}")
        return "\n".join(lines)

    rows = payload.get("items") if isinstance(payload.get("items"), list) else []
    lines = ["# Trust Delivery", "", "- mode: inbox", "", "## Inbox"]
    if not rows:
        lines.append("- none")
    for row in rows[:20]:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"- {row.get('run_id') or '-'} risk={row.get('risk_tier') or '-'} "
            f"decision={row.get('policy_decision') or '-'} approval={row.get('approval_state') or '-'}"
        )
    return "\n".join(lines)


def preview_trust_delivery(
    runs_root: str | Path,
    *,
    mode: str,
    run_id: str | None = None,
    window: int = 10,
    output_format: str = "json",
) -> dict[str, Any]:
    from .gui_mvp_server import _run_detail, _trust_events, _trust_inbox

    root = Path(runs_root).expanduser().resolve()
    normalized_mode = str(mode or "inbox").strip().lower()
    if normalized_mode == "run":
        if not run_id:
            return {"error": {"code": "missing_run_id", "message": "run_id is required for run delivery preview"}}
        run_dir = root / str(run_id)
        if not run_dir.exists() or not run_dir.is_dir():
            return {"error": {"code": "run_not_found", "message": f"run not found: {run_id}"}}
        detail = _run_detail(run_dir)
        payload = {
            "mode": "run",
            "run_id": detail.get("run_id"),
            "summary": detail.get("trust_summary"),
            "packet": detail.get("trust_packet"),
            "message": detail.get("trust_message"),
        }
    elif normalized_mode == "events":
        events = _trust_events(root, int(window))
        payload = {"mode": "events", **events}
    else:
        inbox = _trust_inbox(root, int(window))
        payload = {"mode": "inbox", **inbox}

    payload["generated_at"] = _utc_now()
    payload["format"] = str(output_format or "json")
    payload["markdown"] = _render_markdown_preview(normalized_mode, payload)
    return payload


def _append_delivery_audit(root: Path, row: dict[str, Any]) -> str:
    audit_path = root / TRUST_DELIVERY_AUDIT_JSONL
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True))
        handle.write("\n")
    return str(audit_path)


def send_trust_delivery(
    runs_root: str | Path,
    *,
    mode: str,
    run_id: str | None = None,
    window: int = 10,
    output_format: str = "json",
    targets: Any = None,
    dry_run: bool = True,
    source: str = "api",
) -> dict[str, Any]:
    root = Path(runs_root).expanduser().resolve()
    preview = preview_trust_delivery(root, mode=mode, run_id=run_id, window=window, output_format=output_format)
    if preview.get("error"):
        return preview

    normalized_targets = _normalize_targets(targets)
    text_payload = preview.get("markdown") if str(output_format or "json").lower() == "markdown" else json.dumps(preview, indent=2)
    outcomes: list[dict[str, Any]] = []

    for target in normalized_targets:
        target_text = str(target)
        outcome = {"target": target_text, "status": "dry_run" if dry_run else "sent"}
        try:
            if not dry_run:
                if target_text == "stdout":
                    print(text_payload)
                elif target_text.startswith("log:"):
                    dest = Path(target_text.split(":", 1)[1]).expanduser()
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(text_payload, encoding="utf-8")
                elif target_text.startswith("webhook:"):
                    url = target_text.split(":", 1)[1]
                    req = request.Request(
                        url=url,
                        data=text_payload.encode("utf-8"),
                        method="POST",
                        headers={"Content-Type": "application/json" if output_format == "json" else "text/markdown"},
                    )
                    with request.urlopen(req, timeout=5):  # noqa: S310
                        pass
                else:
                    outcome["status"] = "failed"
                    outcome["error"] = f"unsupported target: {target_text}"
            outcomes.append(outcome)
        except Exception as exc:  # noqa: BLE001
            outcome["status"] = "failed"
            outcome["error"] = str(exc)
            outcomes.append(outcome)

    audit_row = {
        "timestamp": _utc_now(),
        "source": source,
        "mode": str(mode or "inbox"),
        "run_id": run_id,
        "format": output_format,
        "dry_run": bool(dry_run),
        "targets": normalized_targets,
        "outcomes": outcomes,
    }
    audit_path = _append_delivery_audit(root, audit_row)
    return {
        "preview": preview,
        "dry_run": bool(dry_run),
        "targets": normalized_targets,
        "outcomes": outcomes,
        "audit_log_path": audit_path,
    }
