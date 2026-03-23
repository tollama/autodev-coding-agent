from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent.parent


def _run_checker(target_file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [
            sys.executable,
            "scripts/check_av6_backlog_schema.py",
            "--file",
            str(target_file),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_av6_backlog_schema_passes_for_repo_backlog() -> None:
    proc = _run_checker(ROOT / "docs" / "AUTONOMOUS_V6_BACKLOG.md")

    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    assert "[PASS] AV6 backlog metadata schema check passed" in proc.stdout


def test_check_av6_backlog_schema_fails_on_duplicate_id(tmp_path: Path) -> None:
    md = tmp_path / "duplicate_backlog.md"
    md.write_text(
        "\n".join(
            [
                "| ID | Priority | Effort | Status | Ticket | Definition of Done (DoD) | Test plan | PR split |",
                "|---|---|---:|---|---|---|---|---|",
                "| AV6-001 | P0 | S | planned | First ticket | Example DoD | Example test | 1 PR |",
                "| AV6-001 | P1 | M | merged | Duplicate ticket | Example DoD | Example test | 1 PR |",
            ]
        ),
        encoding="utf-8",
    )

    proc = _run_checker(md)

    assert proc.returncode == 1
    assert "duplicate ID 'AV6-001'" in proc.stdout


def test_check_av6_backlog_schema_fails_on_invalid_id_prefix(tmp_path: Path) -> None:
    md = tmp_path / "bad_id_backlog.md"
    md.write_text(
        "\n".join(
            [
                "| ID | Priority | Effort | Status | Ticket | Definition of Done (DoD) | Test plan | PR split |",
                "|---|---|---:|---|---|---|---|---|",
                "| AV5-001 | P1 | S | planned | Wrong wave ticket | Example DoD | Example test | 1 PR |",
            ]
        ),
        encoding="utf-8",
    )

    proc = _run_checker(md)

    assert proc.returncode == 1
    assert "invalid ID 'AV5-001'" in proc.stdout
