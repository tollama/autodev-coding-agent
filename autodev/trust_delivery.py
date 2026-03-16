from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib import request
from uuid import uuid4

TRUST_DELIVERY_AUDIT_JSONL = ".autodev/trust_delivery_audit.jsonl"
TRUST_DELIVERY_STATE_JSONL = ".autodev/trust_delivery_state.jsonl"


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


def _delivery_state_path(root: Path) -> Path:
    return root / TRUST_DELIVERY_STATE_JSONL


def _append_delivery_state(root: Path, row: dict[str, Any]) -> str:
    state_path = _delivery_state_path(root)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True))
        handle.write("\n")
    return str(state_path)


def _load_delivery_state_rows(root: Path) -> list[dict[str, Any]]:
    state_path = _delivery_state_path(root)
    if not state_path.exists() or not state_path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for raw_line in state_path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _normalize_adapter_target(target_text: str) -> tuple[str, str]:
    if target_text == "stdout":
        return "stdout", ""
    if ":" not in target_text:
        return "unsupported", target_text
    adapter, value = target_text.split(":", 1)
    return adapter.strip().lower(), value


def _render_ticket_payload(preview: Mapping[str, Any]) -> dict[str, Any]:
    mode = str(preview.get("mode") or "inbox")
    if mode == "run":
        summary = preview.get("summary") if isinstance(preview.get("summary"), dict) else {}
        run_id = str(preview.get("run_id") or "-")
        return {
            "title": f"Trust review for {run_id}",
            "run_id": run_id,
            "mode": mode,
            "trust_status": summary.get("trust_status"),
            "trust_score": summary.get("trust_score"),
            "policy_decision": summary.get("policy_decision"),
            "approval_state": summary.get("approval_state"),
            "body_markdown": str(preview.get("markdown") or ""),
        }
    if mode == "events":
        events = preview.get("events") if isinstance(preview.get("events"), list) else []
        return {
            "title": f"Trust event digest ({len(events)} events)",
            "mode": mode,
            "event_count": len(events),
            "body_markdown": str(preview.get("markdown") or ""),
        }
    items = preview.get("items") if isinstance(preview.get("items"), list) else []
    return {
        "title": f"Trust inbox digest ({len(items)} item{'s' if len(items) != 1 else ''})",
        "mode": mode,
        "item_count": len(items),
        "body_markdown": str(preview.get("markdown") or ""),
    }


def _render_github_issue_payload(preview: Mapping[str, Any]) -> dict[str, Any]:
    ticket = _render_ticket_payload(preview)
    return {
        "title": ticket.get("title"),
        "body": ticket.get("body_markdown"),
        "labels": ["trust-intelligence", f"mode:{ticket.get('mode') or 'inbox'}"],
    }


def _render_jira_ticket_payload(preview: Mapping[str, Any]) -> dict[str, Any]:
    ticket = _render_ticket_payload(preview)
    return {
        "fields": {
            "summary": ticket.get("title"),
            "description": ticket.get("body_markdown"),
            "issuetype": {"name": "Task"},
            "labels": ["trust-intelligence", f"mode-{ticket.get('mode') or 'inbox'}"],
        }
    }


def _render_notification_payload(preview: Mapping[str, Any]) -> dict[str, Any]:
    ticket = _render_ticket_payload(preview)
    return {
        "title": ticket.get("title"),
        "channel": "trust-ops",
        "severity": "high" if "Trust inbox" in str(ticket.get("title") or "") else "info",
        "body_markdown": ticket.get("body_markdown"),
    }


def _webhook_headers(output_format: str, body: str, *, webhook_secret: str | None = None) -> dict[str, str]:
    headers = {"Content-Type": "application/json" if output_format == "json" else "text/markdown"}
    if webhook_secret:
        signature = hmac.new(
            webhook_secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers["X-Autodev-Signature"] = f"sha256={signature}"
    return headers


def _attempt_number(rows: list[dict[str, Any]], *, target: str, dedupe_key: str) -> int:
    latest = 0
    for row in rows:
        if str(row.get("target") or "") != target:
            continue
        if str(row.get("dedupe_key") or "") != dedupe_key:
            continue
        latest = max(latest, int(row.get("attempt") or 0))
    return latest + 1


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


def load_trust_delivery_audit(
    runs_root: str | Path,
    *,
    window: int = 20,
    mode: str | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    root = Path(runs_root).expanduser().resolve()
    audit_path = root / TRUST_DELIVERY_AUDIT_JSONL
    if not audit_path.exists() or not audit_path.is_file():
        return {
            "empty": True,
            "message": "No trust delivery activity recorded yet.",
            "summary": {"events_total": 0, "sent_count": 0, "dry_run_count": 0, "failed_count": 0},
            "events": [],
            "audit_log_path": str(audit_path),
        }

    mode_filter = str(mode or "").strip().lower()
    target_filter = str(target or "").strip().lower()
    rows: list[dict[str, Any]] = []
    for raw_line in audit_path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        row_mode = str(row.get("mode") or "").strip().lower()
        targets = [str(item or "").strip() for item in row.get("targets", []) if str(item or "").strip()]
        if mode_filter and row_mode != mode_filter:
            continue
        if target_filter and target_filter not in {item.lower() for item in targets}:
            continue
        rows.append(row)

    rows.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    limited = rows[: max(int(window or 20), 1)]
    summary = {
        "events_total": len(limited),
        "sent_count": sum(1 for row in limited if row.get("dry_run") is False),
        "dry_run_count": sum(1 for row in limited if row.get("dry_run") is True),
        "failed_count": sum(
            1
            for row in limited
            if any(str(item.get("status") or "") == "failed" for item in (row.get("outcomes") or []) if isinstance(item, dict))
        ),
        "latest_at": limited[0].get("timestamp") if limited else "",
        "modes": sorted({str(row.get("mode") or "") for row in limited if str(row.get("mode") or "").strip()}),
        "targets": sorted(
            {
                str(item or "")
                for row in limited
                for item in (row.get("targets") or [])
                if str(item or "").strip()
            }
        ),
    }
    return {
        "empty": len(limited) == 0,
        "message": "No trust delivery activity matched the filter." if rows and not limited else "",
        "summary": summary,
        "events": limited,
        "audit_log_path": str(audit_path),
    }


def load_trust_delivery_state(
    runs_root: str | Path,
    *,
    window: int = 20,
    status: str | None = None,
) -> dict[str, Any]:
    root = Path(runs_root).expanduser().resolve()
    rows = _load_delivery_state_rows(root)
    status_filter = str(status or "").strip().lower()
    if status_filter:
        rows = [row for row in rows if str(row.get("status") or "").strip().lower() == status_filter]
    rows.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    limited = rows[: max(int(window or 20), 1)]
    return {
        "empty": len(limited) == 0,
        "message": "No trust delivery state recorded yet." if not limited else "",
        "summary": {
            "events_total": len(limited),
            "failed_count": sum(1 for row in limited if str(row.get("status") or "") == "failed"),
            "sent_count": sum(1 for row in limited if str(row.get("status") or "") == "sent"),
            "dry_run_count": sum(1 for row in limited if str(row.get("status") or "") == "dry_run"),
            "retry_count": sum(1 for row in limited if str(row.get("retry_of") or "").strip()),
            "latest_at": limited[0].get("timestamp") if limited else "",
        },
        "events": limited,
        "state_log_path": str(_delivery_state_path(root)),
    }


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
    delivery_id: str | None = None,
    retry_of: str | None = None,
    webhook_secret: str | None = None,
    webhook_retry_limit: int = 0,
    webhook_timeout_sec: float = 5.0,
) -> dict[str, Any]:
    root = Path(runs_root).expanduser().resolve()
    preview = preview_trust_delivery(root, mode=mode, run_id=run_id, window=window, output_format=output_format)
    if preview.get("error"):
        return preview

    normalized_targets = _normalize_targets(targets)
    text_payload = preview.get("markdown") if str(output_format or "json").lower() == "markdown" else json.dumps(preview, indent=2)
    json_payload = json.dumps(preview, indent=2)
    ticket_payload = _render_ticket_payload(preview)
    github_payload = _render_github_issue_payload(preview)
    jira_payload = _render_jira_ticket_payload(preview)
    notification_payload = _render_notification_payload(preview)
    current_delivery_id = str(delivery_id or uuid4().hex[:12])
    prior_rows = _load_delivery_state_rows(root)
    outcomes: list[dict[str, Any]] = []

    for target in normalized_targets:
        target_text = str(target)
        adapter, destination = _normalize_adapter_target(target_text)
        dedupe_key = hashlib.sha256(f"{adapter}|{destination}|{mode}|{run_id or ''}|{output_format}|{json_payload}".encode("utf-8")).hexdigest()
        attempt = _attempt_number(prior_rows, target=target_text, dedupe_key=dedupe_key)
        outcome = {
            "delivery_id": current_delivery_id,
            "retry_of": str(retry_of or ""),
            "target": target_text,
            "adapter": adapter,
            "status": "dry_run" if dry_run else "sent",
            "attempt": attempt,
            "dedupe_key": dedupe_key,
        }
        try:
            if not dry_run:
                if target_text == "stdout":
                    print(text_payload)
                elif target_text.startswith("log:"):
                    dest = Path(target_text.split(":", 1)[1]).expanduser()
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(text_payload, encoding="utf-8")
                    outcome["path"] = str(dest)
                elif target_text.startswith("webhook:"):
                    url = target_text.split(":", 1)[1]
                    for webhook_attempt in range(1, int(webhook_retry_limit or 0) + 2):
                        try:
                            req = request.Request(
                                url=url,
                                data=text_payload.encode("utf-8"),
                                method="POST",
                                headers=_webhook_headers(
                                    str(output_format or "json").lower(),
                                    text_payload,
                                    webhook_secret=str(webhook_secret or "").strip() or None,
                                ),
                            )
                            with request.urlopen(req, timeout=float(webhook_timeout_sec or 5.0)):  # noqa: S310
                                pass
                            outcome["webhook_attempts"] = webhook_attempt
                            break
                        except Exception as exc:  # noqa: BLE001
                            outcome["webhook_attempts"] = webhook_attempt
                            if webhook_attempt > int(webhook_retry_limit or 0):
                                raise exc
                    outcome["url"] = url
                elif target_text.startswith("webhook-signed:"):
                    if not str(webhook_secret or "").strip():
                        raise ValueError("webhook_secret is required for webhook-signed targets")
                    url = target_text.split(":", 1)[1]
                    for webhook_attempt in range(1, int(webhook_retry_limit or 0) + 2):
                        try:
                            req = request.Request(
                                url=url,
                                data=text_payload.encode("utf-8"),
                                method="POST",
                                headers=_webhook_headers(
                                    str(output_format or "json").lower(),
                                    text_payload,
                                    webhook_secret=str(webhook_secret or "").strip(),
                                ),
                            )
                            with request.urlopen(req, timeout=float(webhook_timeout_sec or 5.0)):  # noqa: S310
                                pass
                            outcome["webhook_attempts"] = webhook_attempt
                            break
                        except Exception as exc:  # noqa: BLE001
                            outcome["webhook_attempts"] = webhook_attempt
                            if webhook_attempt > int(webhook_retry_limit or 0):
                                raise exc
                    outcome["url"] = url
                elif target_text.startswith("ticket-json:"):
                    dest = Path(destination).expanduser()
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(json.dumps(ticket_payload, indent=2), encoding="utf-8")
                    outcome["path"] = str(dest)
                elif target_text.startswith("ticket-md:"):
                    dest = Path(destination).expanduser()
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(str(preview.get("markdown") or ""), encoding="utf-8")
                    outcome["path"] = str(dest)
                elif target_text.startswith("bundle-dir:"):
                    dest_dir = Path(destination).expanduser()
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    base = str(run_id or mode or "trust-delivery").replace("/", "-")
                    json_path = dest_dir / f"{base}.json"
                    md_path = dest_dir / f"{base}.md"
                    ticket_path = dest_dir / f"{base}.ticket.json"
                    json_path.write_text(json_payload, encoding="utf-8")
                    md_path.write_text(str(preview.get("markdown") or ""), encoding="utf-8")
                    ticket_path.write_text(json.dumps(ticket_payload, indent=2), encoding="utf-8")
                    outcome["paths"] = [str(json_path), str(md_path), str(ticket_path)]
                elif target_text.startswith("github-issue-json:"):
                    dest = Path(destination).expanduser()
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(json.dumps(github_payload, indent=2), encoding="utf-8")
                    outcome["path"] = str(dest)
                elif target_text.startswith("jira-ticket-json:"):
                    dest = Path(destination).expanduser()
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(json.dumps(jira_payload, indent=2), encoding="utf-8")
                    outcome["path"] = str(dest)
                elif target_text.startswith("notify-inbox-json:"):
                    dest = Path(destination).expanduser()
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(json.dumps(notification_payload, indent=2), encoding="utf-8")
                    outcome["path"] = str(dest)
                else:
                    outcome["status"] = "failed"
                    outcome["error"] = f"unsupported target: {target_text}"
            outcomes.append(outcome)
        except Exception as exc:  # noqa: BLE001
            outcome["status"] = "failed"
            outcome["error"] = str(exc)
            outcomes.append(outcome)

        state_row = {
            "timestamp": _utc_now(),
            "delivery_id": current_delivery_id,
            "retry_of": str(retry_of or ""),
            "source": source,
            "mode": str(mode or "inbox"),
            "run_id": run_id,
            "window": int(window),
            "format": output_format,
            "target": target_text,
            "adapter": adapter,
            "dry_run": bool(dry_run),
            "attempt": attempt,
            "status": outcome.get("status"),
            "error": outcome.get("error"),
            "dedupe_key": dedupe_key,
            "webhook_retry_limit": int(webhook_retry_limit or 0),
            "webhook_timeout_sec": float(webhook_timeout_sec or 5.0),
        }
        _append_delivery_state(root, state_row)
        prior_rows.append(state_row)

    audit_row = {
        "timestamp": _utc_now(),
        "delivery_id": current_delivery_id,
        "retry_of": str(retry_of or ""),
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
        "delivery_id": current_delivery_id,
        "retry_of": str(retry_of or ""),
        "preview": preview,
        "dry_run": bool(dry_run),
        "targets": normalized_targets,
        "outcomes": outcomes,
        "audit_log_path": audit_path,
        "state_log_path": str(_delivery_state_path(root)),
    }


def retry_trust_delivery(
    runs_root: str | Path,
    *,
    delivery_id: str,
    dry_run: bool = False,
    source: str = "api-retry",
    webhook_secret: str | None = None,
) -> dict[str, Any]:
    root = Path(runs_root).expanduser().resolve()
    rows = _load_delivery_state_rows(root)
    matching = [row for row in rows if str(row.get("delivery_id") or "") == str(delivery_id or "").strip()]
    if not matching:
        return {"error": {"code": "delivery_not_found", "message": f"delivery not found: {delivery_id}"}}
    failed = [row for row in matching if str(row.get("status") or "") == "failed"]
    if not failed:
        return {
            "error": {
                "code": "no_failed_targets",
                "message": f"delivery has no failed targets to retry: {delivery_id}",
            }
        }
    latest = failed[-1]
    targets = [str(row.get("target") or "") for row in failed if str(row.get("target") or "").strip()]
    return send_trust_delivery(
        root,
        mode=str(latest.get("mode") or "inbox"),
        run_id=str(latest.get("run_id") or "").strip() or None,
        window=int(latest.get("window") or 10),
        output_format=str(latest.get("format") or "json"),
        targets=targets,
        dry_run=bool(dry_run),
        source=source,
        retry_of=str(delivery_id),
        webhook_secret=webhook_secret,
        webhook_retry_limit=int(latest.get("webhook_retry_limit") or 0),
        webhook_timeout_sec=float(latest.get("webhook_timeout_sec") or 5.0),
    )
