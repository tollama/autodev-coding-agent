from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import autodev.autonomous_mode as autonomous_mode  # noqa: E402
from autodev.autonomous_ticket_draft import (  # noqa: E402
    AUTONOMOUS_TICKET_DRAFT_JSON,
    AUTONOMOUS_TICKET_DRAFT_MD,
    build_autonomous_ticket_draft,
    write_ticket_draft,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_ticket_draft_includes_required_triage_fields(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-ticket"
    artifacts = run_dir / ".autodev"

    _write_json(
        artifacts / "autonomous_report.json",
        {
            "ok": False,
            "run_id": "run-ticket",
            "incident_routing": {
                "primary": {
                    "owner_team": "Feature Engineering",
                    "severity": "high",
                    "target_sla": "4h",
                }
            },
            "operator_guidance": {
                "top": [
                    {
                        "actions": ["Inspect failing tests and patch deterministic assertions first."],
                    }
                ]
            },
        },
    )
    _write_json(
        artifacts / "autonomous_incident_packet.json",
        {
            "run_summary": {
                "run_id": "run-ticket",
                "status": "failed",
                "failure_reason": "autonomous_guard_stop",
            },
            "failure_codes": {
                "typed_codes": ["tests.min_pass_rate_not_met"],
            },
            "incident_routing": {
                "primary": {
                    "owner_team": "Feature Engineering",
                    "severity": "high",
                    "target_sla": "4h",
                }
            },
            "reproduction": {
                "artifact_paths": {
                    "report_json": ".autodev/autonomous_report.json",
                    "incident_packet": ".autodev/autonomous_incident_packet.json",
                }
            },
            "operator_guidance": {
                "top_actions": [
                    {
                        "action": "Inspect failing tests and patch deterministic assertions first.",
                    }
                ]
            },
        },
    )

    draft = build_autonomous_ticket_draft(run_dir)

    assert "run-ticket" in draft["title"]
    assert draft["severity"] == "high"
    assert draft["owner_team"] == "Feature Engineering"
    assert draft["target_sla"] == "4h"
    assert draft["repro_steps"]
    assert any(item["path"] == ".autodev/autonomous_incident_packet.json" for item in draft["evidence"])
    assert draft["suggested_next_actions"]


def test_ticket_draft_gracefully_handles_missing_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "run-ticket-missing"
    run_dir.mkdir(parents=True)

    draft, out_path, rendered = write_ticket_draft(run_dir, "markdown")

    assert out_path == run_dir / AUTONOMOUS_TICKET_DRAFT_MD
    assert out_path.exists()
    assert "## Diagnostics" in rendered
    assert any(item["code"] == "ticket_draft.incident_packet_unavailable" for item in draft["diagnostics"])
    assert any(item["code"] == "ticket_draft.report_unavailable" for item in draft["diagnostics"])


def test_ticket_draft_cli_outputs_and_persists_json(tmp_path: Path, capsys) -> None:
    run_dir = tmp_path / "run-ticket-cli"
    artifacts = run_dir / ".autodev"

    _write_json(
        artifacts / "autonomous_report.json",
        {
            "ok": False,
            "run_id": "run-ticket-cli",
            "incident_routing": {
                "primary": {
                    "owner_team": "Platform Operations",
                    "severity": "high",
                    "target_sla": "4h",
                }
            },
        },
    )

    autonomous_mode.cli(["ticket-draft", "--run-dir", str(run_dir), "--format", "json"])
    out = capsys.readouterr().out

    payload = json.loads(out)
    assert payload["run_dir"] == str(run_dir.resolve())
    assert payload["severity"] == "high"
    assert (run_dir / AUTONOMOUS_TICKET_DRAFT_JSON).exists()
