"""Tests for autodev.failure_analyzer module."""

from __future__ import annotations

from autodev.failure_analyzer import (
    FailureAnalysis,
    FailureCategory,
    RepairHistory,
    analyze_failures,
    build_escalated_guidance,
    build_persistent_error_warnings,
    deduplicate_for_guidance,
    determine_escalation_level,
    fingerprint_error,
    fingerprint_failures,
    fingerprint_validation_row,
    select_repair_strategy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_row(
    name: str,
    *,
    ok: bool = False,
    status: str = "failed",
    error_classification: str | None = None,
    stdout: str = "",
    stderr: str = "",
    diagnostics: dict | None = None,
) -> dict:
    return {
        "name": name,
        "ok": ok,
        "status": status,
        "returncode": 0 if ok else 1,
        "error_classification": error_classification,
        "stdout": stdout,
        "stderr": stderr,
        "diagnostics": diagnostics or {},
        "duration_ms": 100,
        "tool_version": "1.0",
        "note": "",
    }


# ---------------------------------------------------------------------------
# categorize_failure tests
# ---------------------------------------------------------------------------


def test_categorize_import_error():
    """Pytest stdout with ModuleNotFoundError → IMPORT_ERROR."""
    row = _make_row("pytest", stdout="ModuleNotFoundError: No module named 'fastapi'")
    from autodev.failure_analyzer import categorize_failure

    result = categorize_failure(row)
    assert result.category == FailureCategory.IMPORT_ERROR
    assert result.confidence >= 0.9


def test_categorize_type_error_mypy():
    """mypy validator failure → TYPE_ERROR."""
    row = _make_row("mypy", stderr="src/main.py:10: error: Incompatible return type")
    from autodev.failure_analyzer import categorize_failure

    result = categorize_failure(row)
    assert result.category == FailureCategory.TYPE_ERROR
    assert result.confidence >= 0.9


def test_categorize_lint_error_ruff():
    """ruff validator failure → LINT_ERROR."""
    row = _make_row("ruff", stdout="src/main.py:5:1: F401 unused import")
    from autodev.failure_analyzer import categorize_failure

    result = categorize_failure(row)
    assert result.category == FailureCategory.LINT_ERROR
    assert result.confidence >= 0.9


def test_categorize_security_semgrep():
    """semgrep + policy_violation → SECURITY_FINDING."""
    row = _make_row(
        "semgrep",
        error_classification="policy_violation",
        stdout="severity: high - SQL injection detected",
    )
    from autodev.failure_analyzer import categorize_failure

    result = categorize_failure(row)
    assert result.category == FailureCategory.SECURITY_FINDING
    assert result.confidence >= 0.9


def test_categorize_syntax_error():
    """pytest with SyntaxError → SYNTAX_ERROR."""
    row = _make_row("pytest", stdout="SyntaxError: invalid syntax\n  File 'src/main.py', line 10")
    from autodev.failure_analyzer import categorize_failure

    result = categorize_failure(row)
    assert result.category == FailureCategory.SYNTAX_ERROR
    assert result.confidence >= 0.9


def test_categorize_test_logic_error():
    """pytest with assertion diagnostics → TEST_LOGIC_ERROR."""
    row = _make_row(
        "pytest",
        stdout="FAILED tests/test_main.py::test_add",
        diagnostics={
            "summary": {"failed": 1, "passed": 2, "errors": 0, "skipped": 0},
            "assertions": ["assert 3 == 4"],
            "failed_tests": [{"test": "tests/test_main.py::test_add", "message": "assert 3 == 4"}],
            "locations": ["tests/test_main.py:15"],
        },
    )
    from autodev.failure_analyzer import categorize_failure

    result = categorize_failure(row)
    assert result.category == FailureCategory.TEST_LOGIC_ERROR
    assert result.confidence >= 0.8
    assert "tests/test_main.py" in result.failing_files


def test_categorize_test_runtime_error():
    """pytest with errors > 0 → TEST_RUNTIME_ERROR."""
    row = _make_row(
        "pytest",
        stdout="ERROR tests/test_main.py - fixture 'db_session' not found",
        diagnostics={
            "summary": {"failed": 0, "passed": 0, "errors": 2, "skipped": 0},
        },
    )
    from autodev.failure_analyzer import categorize_failure

    result = categorize_failure(row)
    assert result.category == FailureCategory.TEST_RUNTIME_ERROR
    assert result.confidence >= 0.7


def test_categorize_tool_unavailable():
    """error_classification=tool_unavailable → TOOL_UNAVAILABLE."""
    row = _make_row("semgrep", error_classification="tool_unavailable", stderr="command not found")
    from autodev.failure_analyzer import categorize_failure

    result = categorize_failure(row)
    assert result.category == FailureCategory.TOOL_UNAVAILABLE
    assert result.confidence == 1.0


# ---------------------------------------------------------------------------
# analyze_failures tests
# ---------------------------------------------------------------------------


def test_analyze_failures_skips_passing():
    """Only failed rows should be analyzed."""
    rows = [
        _make_row("ruff", ok=True, status="passed"),
        _make_row("pytest", ok=False, stdout="FAILED test_foo"),
    ]
    results = analyze_failures(rows)
    assert len(results) == 1
    assert results[0].validator_name == "pytest"


def test_analyze_failures_empty():
    """Empty input → empty result."""
    assert analyze_failures([]) == []


# ---------------------------------------------------------------------------
# select_repair_strategy tests
# ---------------------------------------------------------------------------


def test_select_strategy_priority_order():
    """Syntax errors should appear before logic errors in strategy."""
    analyses = [
        FailureAnalysis("pytest", FailureCategory.TEST_LOGIC_ERROR, None, "logic", [], [], 0.8),
        FailureAnalysis("pytest", FailureCategory.SYNTAX_ERROR, None, "syntax", [], [], 0.9),
    ]
    result = select_repair_strategy(analyses)
    # SYNTAX_ERROR has priority 0, TEST_LOGIC_ERROR has priority 6
    lines = result.strip().split("\n")
    assert lines[0].startswith("[syntax_error]")
    assert lines[1].startswith("[test_logic_error]")


def test_select_strategy_max_three():
    """Only top-3 categories should appear in strategy."""
    analyses = [
        FailureAnalysis("v1", FailureCategory.SYNTAX_ERROR, None, "", [], [], 0.9),
        FailureAnalysis("v2", FailureCategory.IMPORT_ERROR, None, "", [], [], 0.9),
        FailureAnalysis("v3", FailureCategory.TYPE_ERROR, None, "", [], [], 0.9),
        FailureAnalysis("v4", FailureCategory.LINT_ERROR, None, "", [], [], 0.9),
        FailureAnalysis("v5", FailureCategory.SECURITY_FINDING, None, "", [], [], 0.9),
    ]
    result = select_repair_strategy(analyses)
    lines = [ln for ln in result.strip().split("\n") if ln.strip()]
    assert len(lines) == 3


def test_select_strategy_empty():
    """Empty analyses → empty string."""
    assert select_repair_strategy([]) == ""


# ---------------------------------------------------------------------------
# determine_escalation_level tests
# ---------------------------------------------------------------------------


def test_escalation_disabled_returns_zero():
    """Guard disabled → always level 0."""
    assert determine_escalation_level(0, 1, False) == 0
    assert determine_escalation_level(5, 1, False) == 0
    assert determine_escalation_level(100, 1, False) == 0


def test_escalation_levels_progress():
    """Escalation level increases with repeat count."""
    # max_retries=1: count 0→level 0, count 1→level 1, count 2→level 2
    assert determine_escalation_level(0, 1, True) == 0
    assert determine_escalation_level(1, 1, True) == 1
    assert determine_escalation_level(2, 1, True) == 2
    assert determine_escalation_level(5, 1, True) == 2


def test_build_guidance_levels():
    """Each level should include appropriate keywords."""
    analyses = [
        FailureAnalysis("ruff", FailureCategory.LINT_ERROR, None, "ruff failed", [], [], 0.9),
    ]
    base = "Fix failures."
    rows: list[dict] = []

    g0 = build_escalated_guidance(0, analyses, base, rows)
    assert "Failure-specific guidance:" in g0
    assert "Fix failures." in g0

    g1 = build_escalated_guidance(1, analyses, base, rows)
    assert "TARGETED FIX" in g1
    assert "Failure analysis:" in g1

    g2 = build_escalated_guidance(2, analyses, base, rows)
    assert "SURGICAL FIX" in g2
    assert "highest escalation level" in g2


# ---------------------------------------------------------------------------
# RepairHistory tests
# ---------------------------------------------------------------------------


def test_repair_history_cross_task_hints():
    """Record resolved outcomes and get hints for same category."""
    history = RepairHistory()
    history.record("task1", FailureCategory.IMPORT_ERROR, 1, resolved=True)
    history.record("task2", FailureCategory.LINT_ERROR, 0, resolved=True)

    hints = history.get_hints_for_category(FailureCategory.IMPORT_ERROR)
    assert len(hints) == 1
    assert "task1" in hints[0]
    assert "import_error" in hints[0]

    # No hints for unresolved category
    history.record("task3", FailureCategory.TYPE_ERROR, 0, resolved=False)
    assert history.get_hints_for_category(FailureCategory.TYPE_ERROR) == []

    assert history.has_prior_resolution(FailureCategory.IMPORT_ERROR) is True
    assert history.has_prior_resolution(FailureCategory.TYPE_ERROR) is False


def test_repair_history_to_dict():
    """Serialization format should include outcomes and summary."""
    history = RepairHistory()
    history.record("t1", FailureCategory.LINT_ERROR, 0, resolved=True)
    history.record("t1", FailureCategory.LINT_ERROR, 1, resolved=False)

    data = history.to_dict()
    assert len(data["outcomes"]) == 2
    assert data["outcomes"][0]["task_id"] == "t1"
    assert data["outcomes"][0]["category"] == "lint_error"
    assert data["outcomes"][0]["resolved"] is True

    summary = data["summary"]
    assert "lint_error" in summary
    assert summary["lint_error"]["total"] == 2
    assert summary["lint_error"]["resolved"] == 1


# ---------------------------------------------------------------------------
# Fingerprint generation tests
# ---------------------------------------------------------------------------


def test_fingerprint_error_deterministic():
    """Same inputs must produce the same digest."""
    fp1 = fingerprint_error("src/main.py", "10", "F401", "F401 'os' imported but unused")
    fp2 = fingerprint_error("src/main.py", "10", "F401", "F401 'os' imported but unused")
    assert fp1.digest == fp2.digest
    assert fp1 == fp2


def test_fingerprint_error_different_for_different_files():
    """Different file should produce different digest."""
    fp1 = fingerprint_error("src/a.py", "10", "F401", "unused import")
    fp2 = fingerprint_error("src/b.py", "10", "F401", "unused import")
    assert fp1.digest != fp2.digest


def test_fingerprint_error_normalizes_text():
    """Fingerprint should normalise whitespace, case, and hex addresses."""
    fp1 = fingerprint_error("x.py", "1", "E", "  Error at 0x7fabcdef  ")
    fp2 = fingerprint_error("x.py", "1", "E", "error at 0x12345678")
    assert fp1.digest == fp2.digest


def test_fingerprint_error_normalizes_line_numbers():
    """Fingerprint should normalise 'line N' references."""
    fp1 = fingerprint_error("x.py", "1", "E", "error at line 42")
    fp2 = fingerprint_error("x.py", "1", "E", "error at line 99")
    assert fp1.digest == fp2.digest


def test_fingerprint_error_frozen():
    """ErrorFingerprint should be frozen (immutable and hashable)."""
    fp = fingerprint_error("a.py", "1", "E", "test")
    assert hash(fp) == hash(fp.digest)
    # Can be used in a set
    s = {fp}
    assert fp in s


def test_fingerprint_validation_row_ruff():
    """Ruff row with locations should produce per-file fingerprints."""
    row = _make_row(
        "ruff",
        stdout="src/a.py:5:1: F401 'os' imported but unused\nsrc/b.py:10:1: F401 'sys' imported but unused",
        diagnostics={"locations": ["src/a.py:5", "src/b.py:10"]},
    )
    fps = fingerprint_validation_row(row)
    assert len(fps) == 2
    digests = {fp.digest for fp in fps}
    assert len(digests) == 2  # two distinct fingerprints


def test_fingerprint_validation_row_pytest():
    """Pytest row with failed_tests should produce per-test fingerprints."""
    row = _make_row(
        "pytest",
        stdout="FAILED tests/test_main.py::test_add",
        diagnostics={
            "summary": {"failed": 2, "passed": 0, "errors": 0},
            "failed_tests": [
                {"test": "tests/test_main.py::test_add", "message": "assert 3 == 4"},
                {"test": "tests/test_utils.py::test_helper", "message": "assert True is False"},
            ],
        },
    )
    fps = fingerprint_validation_row(row)
    assert len(fps) == 2
    files = {fp.file for fp in fps}
    assert "tests/test_main.py" in files
    assert "tests/test_utils.py" in files


def test_fingerprint_validation_row_passing_returns_empty():
    """Passing rows should return no fingerprints."""
    row = _make_row("ruff", ok=True, status="passed")
    assert fingerprint_validation_row(row) == []


def test_fingerprint_validation_row_no_locations_fallback():
    """Row without locations should still produce a single fallback fingerprint."""
    row = _make_row("mypy", stderr="some type error")
    fps = fingerprint_validation_row(row)
    assert len(fps) >= 1


def test_fingerprint_validation_row_text_scan():
    """Row without diagnostics locations should extract from stdout text."""
    row = _make_row(
        "ruff",
        stdout="src/main.py:42:1: F401 'os' imported but unused",
        diagnostics={},
    )
    fps = fingerprint_validation_row(row)
    assert len(fps) >= 1
    assert any(fp.file == "src/main.py" for fp in fps)


# ---------------------------------------------------------------------------
# FingerprintedFailure / fingerprint_failures tests
# ---------------------------------------------------------------------------


def test_fingerprint_failures_deduplicates():
    """Identical errors within one row should be deduplicated."""
    row = _make_row(
        "ruff",
        stdout="src/a.py:5:1: F401 'os' unused\nsrc/a.py:5:1: F401 'os' unused",
        diagnostics={"locations": ["src/a.py:5", "src/a.py:5"]},
    )
    results = fingerprint_failures([row])
    assert len(results) == 1
    assert results[0].unique_count == 1
    assert results[0].deduplicated_count >= 1


def test_fingerprint_failures_skips_passing():
    """Only failed rows should produce FingerprintedFailure objects."""
    rows = [
        _make_row("ruff", ok=True, status="passed"),
        _make_row("pytest", stdout="FAILED test_foo"),
    ]
    results = fingerprint_failures(rows)
    assert len(results) == 1
    assert results[0].analysis.validator_name == "pytest"


def test_fingerprint_failures_multiple_validators():
    """Multiple failing validators should each get a FingerprintedFailure."""
    rows = [
        _make_row("ruff", stdout="src/a.py:1:1: F401 unused"),
        _make_row("mypy", stderr="src/b.py:10: error: wrong type [arg-type]"),
    ]
    results = fingerprint_failures(rows)
    assert len(results) == 2


# ---------------------------------------------------------------------------
# Deduplication guidance tests
# ---------------------------------------------------------------------------


def test_deduplicate_for_guidance_groups_same_error():
    """Multiple occurrences of same rule in different files should group."""
    row1 = _make_row(
        "ruff",
        stdout="src/a.py:5:1: F401 'os' unused",
        diagnostics={"locations": ["src/a.py:5"]},
    )
    row2 = _make_row(
        "ruff",
        stdout="src/b.py:10:1: F401 'sys' unused",
        diagnostics={"locations": ["src/b.py:10"]},
    )
    fingerprinted = fingerprint_failures([row1, row2])
    result = deduplicate_for_guidance(fingerprinted)
    assert "Deduplicated errors:" in result


def test_deduplicate_for_guidance_empty():
    """Empty input should return empty string."""
    assert deduplicate_for_guidance([]) == ""


# ---------------------------------------------------------------------------
# Persistent error warning tests
# ---------------------------------------------------------------------------


def test_build_persistent_error_warnings_below_threshold():
    """Below threshold: no warning."""
    history = {"abc1234567890123": 2, "def4567890123456": 1}
    assert build_persistent_error_warnings(history) == ""


def test_build_persistent_error_warnings_above_threshold():
    """At or above threshold: warning produced."""
    history = {"abc1234567890123": 3, "def4567890123456": 5}
    result = build_persistent_error_warnings(history)
    assert "PERSISTENT ERROR WARNING" in result
    assert "2 error(s)" in result
    assert "abc12345" in result  # first 8 chars


def test_build_persistent_error_warnings_custom_threshold():
    """Custom threshold is respected."""
    history = {"abc1234567890123": 2}
    assert build_persistent_error_warnings(history, threshold=2) != ""
    assert build_persistent_error_warnings(history, threshold=3) == ""


# ---------------------------------------------------------------------------
# Enhanced RepairHistory tests (fingerprint-level)
# ---------------------------------------------------------------------------


def test_repair_history_fingerprint_hints():
    """RepairHistory should provide hints at the fingerprint level."""
    history = RepairHistory()
    history.record("task1", FailureCategory.LINT_ERROR, 1, resolved=True, fingerprints=["abc123"])
    history.record("task2", FailureCategory.LINT_ERROR, 0, resolved=False, fingerprints=["abc123"])

    hints = history.get_hints_for_fingerprint("abc123")
    assert len(hints) == 1
    assert "task1" in hints[0]

    # No hints for unknown fingerprint
    assert history.get_hints_for_fingerprint("xyz999") == []


def test_repair_history_to_dict_includes_fingerprints():
    """Serialized RepairHistory should include fingerprint data."""
    history = RepairHistory()
    history.record("t1", FailureCategory.LINT_ERROR, 0, resolved=True, fingerprints=["fp1", "fp2"])

    data = history.to_dict()
    assert data["outcomes"][0]["fingerprints"] == ["fp1", "fp2"]


def test_repair_history_backward_compatible_record():
    """Calling record() without fingerprints should still work."""
    history = RepairHistory()
    history.record("t1", FailureCategory.LINT_ERROR, 0, resolved=True)
    assert history.outcomes[0].fingerprints == []
    # Existing get_hints_for_category should still work
    hints = history.get_hints_for_category(FailureCategory.LINT_ERROR)
    assert len(hints) == 1
