"""Tests for autodev.quality_score — composite quality scoring."""

from __future__ import annotations

import pytest

from autodev.quality_score import (
    DEFAULT_WEIGHTS,
    HARD_BLOCKER_CLASSIFICATIONS,
    HARD_BLOCKER_VALIDATORS,
    QualityScore,
    ScoreWeights,
    compute_quality_score,
    _check_hard_blockers,
    _extract_lint_error_count,
    _extract_pytest_counts,
    _extract_security_findings,
    _extract_type_health,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_row(name: str, ok: bool, **extra) -> dict:
    row = {"name": name, "ok": ok, "status": "done"}
    row.update(extra)
    return row


def _passing_suite() -> list[dict]:
    """All validators passing."""
    return [
        _make_row("ruff", True),
        _make_row("mypy", True),
        _make_row("pytest", True, diagnostics={"passed": 10, "failed": 0, "errors": 0}),
        _make_row("bandit", True, diagnostics={"finding_count": 0, "critical_count": 0}),
    ]


def _failing_suite() -> list[dict]:
    """Mix of failures."""
    return [
        _make_row("ruff", False, diagnostics={"error_count": 3}),
        _make_row("mypy", False, diagnostics={"error_count": 4}),
        _make_row("pytest", False, diagnostics={"passed": 6, "failed": 4, "errors": 0}),
        _make_row("bandit", True, diagnostics={"finding_count": 0, "critical_count": 0}),
    ]


# ---------------------------------------------------------------------------
# ScoreWeights tests
# ---------------------------------------------------------------------------


class TestScoreWeights:
    def test_default_sums_to_one(self):
        w = DEFAULT_WEIGHTS
        total = w.tests + w.lint + w.type_health + w.security + w.simplicity
        assert abs(total - 1.0) < 0.001

    def test_invalid_weights_raises(self):
        with pytest.raises(ValueError, match="must sum to 1.0"):
            ScoreWeights(tests=0.5, lint=0.5, type_health=0.5, security=0.0, simplicity=0.0)


# ---------------------------------------------------------------------------
# Extraction helper tests
# ---------------------------------------------------------------------------


class TestExtractPytestCounts:
    def test_with_diagnostics(self):
        rows = [_make_row("pytest", True, diagnostics={"passed": 8, "failed": 2, "errors": 1})]
        assert _extract_pytest_counts(rows) == (8, 3)

    def test_without_diagnostics_ok(self):
        rows = [_make_row("pytest", True)]
        assert _extract_pytest_counts(rows) == (1, 0)

    def test_without_diagnostics_fail(self):
        rows = [_make_row("pytest", False)]
        assert _extract_pytest_counts(rows) == (0, 1)

    def test_no_pytest(self):
        rows = [_make_row("ruff", True)]
        assert _extract_pytest_counts(rows) == (0, 0)


class TestExtractLintErrorCount:
    def test_with_diagnostics(self):
        rows = [_make_row("ruff", False, diagnostics={"error_count": 5})]
        assert _extract_lint_error_count(rows) == 5

    def test_failed_no_diagnostics(self):
        rows = [_make_row("ruff", False)]
        assert _extract_lint_error_count(rows) == 1

    def test_passing(self):
        rows = [_make_row("ruff", True)]
        assert _extract_lint_error_count(rows) == 0


class TestExtractTypeHealth:
    def test_passing(self):
        rows = [_make_row("mypy", True)]
        assert _extract_type_health(rows) == (True, 0)

    def test_failing_with_errors(self):
        rows = [_make_row("mypy", False, diagnostics={"error_count": 7})]
        assert _extract_type_health(rows) == (False, 7)

    def test_not_run(self):
        rows = [_make_row("ruff", True)]
        assert _extract_type_health(rows) == (True, 0)


class TestExtractSecurityFindings:
    def test_no_findings(self):
        rows = [_make_row("bandit", True, diagnostics={"finding_count": 0, "critical_count": 0})]
        assert _extract_security_findings(rows) == (0, 0)

    def test_with_findings(self):
        rows = [
            _make_row("bandit", False, diagnostics={"finding_count": 3, "critical_count": 1}),
            _make_row("pip_audit", True, diagnostics={"finding_count": 0, "critical_count": 0}),
        ]
        assert _extract_security_findings(rows) == (3, 1)


# ---------------------------------------------------------------------------
# Hard blocker tests
# ---------------------------------------------------------------------------


class TestHardBlockers:
    def test_no_blockers_on_passing(self):
        assert _check_hard_blockers(_passing_suite()) == []

    def test_pytest_failure_is_hard_blocker(self):
        rows = [_make_row("pytest", False)]
        blockers = _check_hard_blockers(rows)
        assert len(blockers) == 1
        assert "pytest" in blockers[0]

    def test_ruff_failure_is_hard_blocker(self):
        rows = [_make_row("ruff", False)]
        blockers = _check_hard_blockers(rows)
        assert len(blockers) == 1

    def test_soft_validator_not_hard_blocker(self):
        rows = [_make_row("pytest", False)]
        blockers = _check_hard_blockers(rows, soft_validators={"pytest"})
        assert blockers == []

    def test_security_critical_classification(self):
        rows = [_make_row("bandit", False, error_classification="security_critical")]
        blockers = _check_hard_blockers(rows)
        assert any("security_critical" in b for b in blockers)


# ---------------------------------------------------------------------------
# Composite score tests
# ---------------------------------------------------------------------------


class TestComputeQualityScore:
    def test_perfect_score(self):
        qs = compute_quality_score(_passing_suite())
        assert qs.composite == pytest.approx(100.0, abs=0.1)
        assert not qs.hard_blocked
        assert qs.hard_blockers == []

    def test_failing_reduces_score(self):
        qs = compute_quality_score(_failing_suite())
        assert qs.composite < 100.0
        assert qs.tests_score == pytest.approx(60.0, abs=0.1)  # 6/10
        assert qs.lint_score == pytest.approx(70.0, abs=0.1)  # 100 - 3*10

    def test_hard_blocked_when_pytest_fails(self):
        rows = [_make_row("pytest", False, diagnostics={"passed": 0, "failed": 5, "errors": 0})]
        qs = compute_quality_score(rows)
        assert qs.hard_blocked

    def test_soft_validator_not_blocking(self):
        rows = [_make_row("pytest", False, diagnostics={"passed": 0, "failed": 5, "errors": 0})]
        qs = compute_quality_score(rows, soft_validators={"pytest"})
        assert not qs.hard_blocked

    def test_loc_delta_positive_penalty(self):
        qs = compute_quality_score(_passing_suite(), loc_delta=100)
        assert qs.simplicity_score < 100.0

    def test_loc_delta_negative_reward(self):
        qs = compute_quality_score(_passing_suite(), loc_delta=-20)
        assert qs.simplicity_score >= 100.0

    def test_loc_penalty_capped(self):
        qs1 = compute_quality_score(_passing_suite(), loc_delta=100, loc_penalty_cap=10.0)
        qs2 = compute_quality_score(_passing_suite(), loc_delta=1000, loc_penalty_cap=10.0)
        assert qs1.simplicity_score == qs2.simplicity_score

    def test_security_critical_zeros_security_score(self):
        rows = [
            _make_row("pytest", True, diagnostics={"passed": 1, "failed": 0, "errors": 0}),
            _make_row("ruff", True),
            _make_row("bandit", False, diagnostics={"finding_count": 1, "critical_count": 1}),
        ]
        qs = compute_quality_score(rows)
        assert qs.security_score == 0.0

    def test_to_dict(self):
        qs = compute_quality_score(_passing_suite())
        d = qs.to_dict()
        assert "composite" in d
        assert "hard_blocked" in d
        assert "components" in d
        assert "raw" in d
        assert d["composite"] == pytest.approx(100.0, abs=0.1)

    def test_empty_validation_rows(self):
        qs = compute_quality_score([])
        assert qs.composite == pytest.approx(100.0, abs=0.1)
        assert not qs.hard_blocked
