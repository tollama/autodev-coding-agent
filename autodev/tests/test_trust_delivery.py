from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for name in list(sys.modules):
    if name == "autodev" or name.startswith("autodev."):
        sys.modules.pop(name, None)

from autodev.trust_delivery import load_trust_delivery_state, send_trust_delivery  # noqa: E402


def test_send_trust_delivery_supports_signed_webhook_retry(monkeypatch, tmp_path: Path) -> None:
    attempts = {"count": 0}
    captured_headers: list[dict[str, str]] = []

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(req, timeout=0):  # noqa: ANN001, ARG001
        attempts["count"] += 1
        captured_headers.append(dict(req.header_items()))
        if attempts["count"] == 1:
            raise OSError("transient webhook failure")
        return _Response()

    monkeypatch.setattr("autodev.trust_delivery.request.urlopen", _fake_urlopen)

    payload = send_trust_delivery(
        tmp_path,
        mode="inbox",
        dry_run=False,
        output_format="json",
        targets=["webhook-signed:https://example.invalid/trust"],
        webhook_secret="secret-token",
        webhook_retry_limit=1,
    )

    assert payload["outcomes"][0]["status"] == "sent"
    assert payload["outcomes"][0]["webhook_attempts"] == 2
    assert attempts["count"] == 2
    assert any(key.lower() == "x-autodev-signature" for headers in captured_headers for key in headers)

    state = load_trust_delivery_state(tmp_path, window=5)
    assert state["summary"]["sent_count"] >= 1


def test_send_trust_delivery_supports_external_payload_adapters(tmp_path: Path) -> None:
    github_path = tmp_path / "github-issue.json"
    jira_path = tmp_path / "jira-ticket.json"
    notify_path = tmp_path / "notify.json"
    bundle_dir = tmp_path / "bundle"

    payload = send_trust_delivery(
        tmp_path,
        mode="inbox",
        dry_run=False,
        output_format="json",
        targets=[
            f"github-issue-json:{github_path}",
            f"jira-ticket-json:{jira_path}",
            f"notify-inbox-json:{notify_path}",
            f"bundle-dir:{bundle_dir}",
        ],
    )

    assert all(row["status"] == "sent" for row in payload["outcomes"])
    github_issue = json.loads(github_path.read_text(encoding="utf-8"))
    jira_ticket = json.loads(jira_path.read_text(encoding="utf-8"))
    notification = json.loads(notify_path.read_text(encoding="utf-8"))

    assert "title" in github_issue
    assert "fields" in jira_ticket
    assert notification["channel"] == "trust-ops"
    assert any(path.name.endswith(".ticket.json") for path in bundle_dir.iterdir())
