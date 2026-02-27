"""Tests for autodev.report module."""

from __future__ import annotations

import json
import os

from autodev.report import (
    _build_phase_timeline,
    _build_task_trend_table,
    _build_validation_table,
    _derive_scorecard,
    write_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_json(root: str, rel: str, data) -> None:
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _read_report(root: str) -> str:
    with open(os.path.join(root, ".autodev", "REPORT.md"), "r") as f:
        return f.read()


def _read_html_report(root: str) -> str:
    with open(os.path.join(root, ".autodev", "REPORT.html"), "r") as f:
        return f.read()


# ---------------------------------------------------------------------------
# write_report tests
# ---------------------------------------------------------------------------


def test_write_report_creates_file(tmp_path):
    """write_report should create .autodev/REPORT.md."""
    write_report(
        str(tmp_path),
        prd_struct={"title": "Test Project"},
        plan={"project": {"type": "python_cli"}},
        final_validation=[],
        ok=True,
    )
    assert os.path.isfile(os.path.join(str(tmp_path), ".autodev", "REPORT.md"))


def test_write_report_includes_title(tmp_path):
    """Report should include project title."""
    write_report(
        str(tmp_path),
        prd_struct={"title": "My App"},
        plan={"project": {"type": "python_fastapi"}},
        final_validation=[],
        ok=True,
    )
    report = _read_report(str(tmp_path))
    assert "My App" in report
    assert "python_fastapi" in report


def test_write_report_includes_ok_status(tmp_path):
    """Report should show ok status."""
    write_report(
        str(tmp_path),
        prd_struct={"title": "T"},
        plan={"project": {}},
        final_validation=[],
        ok=False,
    )
    report = _read_report(str(tmp_path))
    assert "ok: False" in report


def test_write_report_with_quality_summary(tmp_path):
    """Quality scorecard should appear when summary exists."""
    _write_json(str(tmp_path), ".autodev/task_quality_index.json", {
        "tasks": [
            {"task_id": "t1", "status": "passed", "attempts": 1},
            {"task_id": "t2", "status": "failed", "attempts": 2},
        ],
        "final": {"status": "passed"},
        "totals": {
            "tasks": 2,
            "successful_tasks": 1,
            "total_task_attempts": 3,
            "hard_failures": 1,
            "soft_failures": 0,
            "repair_passes": 1,
        },
        "task_validation_trend": [],
        "unresolved_blockers": [],
    })

    write_report(
        str(tmp_path),
        prd_struct={"title": "T"},
        plan={"project": {}},
        final_validation=[],
        ok=True,
    )
    report = _read_report(str(tmp_path))
    assert "Quality Scorecard" in report
    assert "task_pass_rate_percent" in report


def test_write_report_omits_scorecard_when_no_summary(tmp_path):
    """Without quality summary file, scorecard should not appear."""
    write_report(
        str(tmp_path),
        prd_struct={"title": "T"},
        plan={"project": {}},
        final_validation=[],
        ok=True,
    )
    report = _read_report(str(tmp_path))
    assert "Quality Scorecard" not in report


def test_write_report_with_repair_history(tmp_path):
    """Repair Strategy Analysis should appear when repair history exists."""
    _write_json(str(tmp_path), ".autodev/repair_history.json", {
        "outcomes": [],
        "summary": {
            "lint_error": {"total": 5, "resolved": 4},
            "syntax_error": {"total": 2, "resolved": 2},
        },
    })

    write_report(
        str(tmp_path),
        prd_struct={"title": "T"},
        plan={"project": {}},
        final_validation=[],
        ok=True,
    )
    report = _read_report(str(tmp_path))
    assert "Repair Strategy Analysis" in report
    assert "lint_error" in report
    assert "4/5" in report


def test_write_report_with_change_summary(tmp_path):
    """Change Scope section should appear when change_summary exists."""
    _write_json(str(tmp_path), ".autodev/change_summary.json", {
        "incremental_mode": True,
        "files_added_count": 3,
        "files_possibly_modified_count": 2,
        "files_deleted_count": 1,
        "files_added": ["new1.py", "new2.py", "new3.py"],
    })

    write_report(
        str(tmp_path),
        prd_struct={"title": "T"},
        plan={"project": {}},
        final_validation=[],
        ok=True,
    )
    report = _read_report(str(tmp_path))
    assert "Change Scope (Incremental Mode)" in report
    assert "Files added: 3" in report


# ---------------------------------------------------------------------------
# _derive_scorecard tests
# ---------------------------------------------------------------------------


def test_derive_scorecard_pass_rate():
    """Scorecard should compute correct pass rate."""
    summary = {
        "tasks": [
            {"status": "passed"},
            {"status": "passed"},
            {"status": "failed"},
        ],
        "final": {"status": "passed"},
        "totals": {"total_task_attempts": 5, "hard_failures": 1, "soft_failures": 0, "repair_passes": 1},
    }
    card = _derive_scorecard(summary)
    assert card["task_pass_rate_percent"] == 66.7
    assert card["task_pass_count"] == 2
    assert card["task_total"] == 3


def test_derive_scorecard_empty_tasks():
    """Empty tasks list should produce 0% rate without error."""
    summary = {"tasks": [], "final": {}, "totals": {}}
    card = _derive_scorecard(summary)
    assert card["task_pass_rate_percent"] == 0.0
    assert card["task_total"] == 0


# ---------------------------------------------------------------------------
# HTML report tests
# ---------------------------------------------------------------------------


def test_write_report_creates_html_file(tmp_path):
    """write_report should also create .autodev/REPORT.html."""
    write_report(
        str(tmp_path),
        prd_struct={"title": "Test Project"},
        plan={"project": {"type": "python_cli"}},
        final_validation=[],
        ok=True,
    )
    assert os.path.isfile(os.path.join(str(tmp_path), ".autodev", "REPORT.html"))


def test_html_report_contains_project_title(tmp_path):
    """HTML report should include the project title."""
    write_report(
        str(tmp_path),
        prd_struct={"title": "My Web App"},
        plan={"project": {"type": "python_fastapi"}},
        final_validation=[],
        ok=True,
    )
    html = _read_html_report(str(tmp_path))
    assert "My Web App" in html
    assert "python_fastapi" in html


def test_html_report_contains_status_badge_passed(tmp_path):
    """HTML report should show PASSED badge when ok=True."""
    write_report(
        str(tmp_path),
        prd_struct={"title": "T"},
        plan={"project": {}},
        final_validation=[],
        ok=True,
    )
    html = _read_html_report(str(tmp_path))
    assert "PASSED" in html
    assert "badge-pass" in html


def test_html_report_contains_status_badge_failed(tmp_path):
    """HTML report should show FAILED badge when ok=False."""
    write_report(
        str(tmp_path),
        prd_struct={"title": "T"},
        plan={"project": {}},
        final_validation=[],
        ok=False,
    )
    html = _read_html_report(str(tmp_path))
    assert "FAILED" in html
    assert "badge-fail" in html


def test_html_report_phase_timeline(tmp_path):
    """HTML report should render phase timeline when run_trace exists."""
    _write_json(str(tmp_path), ".autodev/run_trace.json", {
        "run_id": "abc123",
        "request_id": "req1",
        "profile": "balanced",
        "total_elapsed_ms": 10000,
        "event_count": 2,
        "events": [],
        "phases": [
            {"phase": "planning", "start_ms": 0, "end_ms": 2000, "duration_ms": 2000, "status": "completed"},
            {"phase": "implementation", "start_ms": 2000, "end_ms": 8000, "duration_ms": 6000, "status": "completed"},
            {"phase": "final_validation", "start_ms": 8000, "end_ms": 10000, "duration_ms": 2000, "status": "completed"},
        ],
        "llm_metrics": {},
    })

    write_report(
        str(tmp_path),
        prd_struct={"title": "T"},
        plan={"project": {}},
        final_validation=[],
        ok=True,
    )
    html = _read_html_report(str(tmp_path))
    assert "Phase Timeline" in html
    assert "timeline" in html
    assert "Plan" in html  # phase label
    assert "Impl" in html  # phase label
    assert "Final" in html  # phase label


def test_html_report_scorecard_metrics(tmp_path):
    """HTML report should render scorecard cards with metrics."""
    _write_json(str(tmp_path), ".autodev/task_quality_index.json", {
        "tasks": [
            {"task_id": "t1", "status": "passed", "attempts": 1},
            {"task_id": "t2", "status": "passed", "attempts": 2},
        ],
        "final": {"status": "passed"},
        "totals": {
            "tasks": 2, "successful_tasks": 2,
            "total_task_attempts": 3, "hard_failures": 0,
            "soft_failures": 0, "repair_passes": 1,
        },
        "task_validation_trend": [],
        "unresolved_blockers": [],
    })

    write_report(
        str(tmp_path),
        prd_struct={"title": "T"},
        plan={"project": {}},
        final_validation=[],
        ok=True,
    )
    html = _read_html_report(str(tmp_path))
    assert "Quality Scorecard" in html
    assert "100.0%" in html  # pass rate
    assert "2/2" in html  # tasks passed


def test_html_report_task_trend_table(tmp_path):
    """HTML report should render a task quality trend table."""
    _write_json(str(tmp_path), ".autodev/task_quality_index.json", {
        "tasks": [
            {"task_id": "models", "status": "passed", "attempts": 1},
            {"task_id": "api", "status": "failed", "attempts": 3},
        ],
        "final": {"status": "failed"},
        "totals": {
            "tasks": 2, "successful_tasks": 1,
            "total_task_attempts": 4, "hard_failures": 2,
            "soft_failures": 0, "repair_passes": 0,
        },
        "task_validation_trend": [
            {"task_id": "models", "status": "passed", "attempts": 1, "hard_failures": 0, "soft_failures": 0},
            {"task_id": "api", "status": "failed", "attempts": 3, "hard_failures": 2, "soft_failures": 0},
        ],
        "unresolved_blockers": [],
    })

    write_report(
        str(tmp_path),
        prd_struct={"title": "T"},
        plan={"project": {}},
        final_validation=[],
        ok=False,
    )
    html = _read_html_report(str(tmp_path))
    assert "Task Quality Trend" in html
    assert "models" in html
    assert "api" in html
    assert "\u2713" in html  # checkmark for passed
    assert "\u2717" in html  # cross for failed


def test_html_report_final_validation_table(tmp_path):
    """HTML report should render final validation results table."""
    validation = [
        {"name": "ruff", "ok": True, "status": "passed", "returncode": 0, "duration_ms": 250},
        {"name": "pytest", "ok": False, "status": "failed", "returncode": 1, "duration_ms": 3200},
    ]
    write_report(
        str(tmp_path),
        prd_struct={"title": "T"},
        plan={"project": {}},
        final_validation=validation,
        ok=False,
    )
    html = _read_html_report(str(tmp_path))
    assert "Final Validation" in html
    assert "ruff" in html
    assert "pytest" in html
    assert "3.2s" in html  # duration formatted


def test_html_report_repair_section(tmp_path):
    """HTML report should render repair history table."""
    _write_json(str(tmp_path), ".autodev/repair_history.json", {
        "outcomes": [],
        "summary": {
            "lint_error": {"total": 5, "resolved": 4},
            "syntax_error": {"total": 2, "resolved": 2},
        },
    })

    write_report(
        str(tmp_path),
        prd_struct={"title": "T"},
        plan={"project": {}},
        final_validation=[],
        ok=True,
    )
    html = _read_html_report(str(tmp_path))
    assert "Repair Strategy" in html
    assert "lint_error" in html
    assert "syntax_error" in html


def test_html_report_change_scope(tmp_path):
    """HTML report should render change scope section."""
    _write_json(str(tmp_path), ".autodev/change_summary.json", {
        "incremental_mode": True,
        "files_added_count": 3,
        "files_possibly_modified_count": 2,
        "files_deleted_count": 0,
        "files_added": ["src/main.py", "src/utils.py", "tests/test_main.py"],
    })

    write_report(
        str(tmp_path),
        prd_struct={"title": "T"},
        plan={"project": {}},
        final_validation=[],
        ok=True,
    )
    html = _read_html_report(str(tmp_path))
    assert "Change Scope (Incremental Mode)" in html
    assert "src/main.py" in html


def test_html_report_no_quality_summary_graceful(tmp_path):
    """HTML report should render gracefully without quality_summary."""
    write_report(
        str(tmp_path),
        prd_struct={"title": "Minimal"},
        plan={"project": {"type": "python_cli"}},
        final_validation=[],
        ok=True,
    )
    html = _read_html_report(str(tmp_path))
    assert "Minimal" in html
    assert "PASSED" in html
    # No scorecard section
    assert "Quality Scorecard" not in html


# ---------------------------------------------------------------------------
# HTML builder unit tests
# ---------------------------------------------------------------------------


def test_build_phase_timeline_empty():
    """Empty phases should produce empty string."""
    assert _build_phase_timeline([]) == ""


def test_build_phase_timeline_renders_segments():
    """Phase timeline should produce div segments."""
    phases = [
        {"phase": "planning", "duration_ms": 1000},
        {"phase": "implementation", "duration_ms": 3000},
    ]
    html = _build_phase_timeline(phases)
    assert "timeline" in html
    assert "Plan" in html
    assert "Impl" in html


def test_build_task_trend_table_empty():
    """Empty trend should produce empty string."""
    assert _build_task_trend_table([]) == ""


def test_build_validation_table_empty():
    """Empty validation should produce fallback text."""
    html = _build_validation_table([])
    assert "No validation results" in html
