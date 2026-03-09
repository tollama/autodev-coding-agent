"""Composite quality score computation inspired by autoresearch's single-metric approach.

Computes a normalized 0-100 score from validator results, while respecting
hard blockers that cause immediate failure regardless of score.

Design principles (from user review):
- Composite score is for *ranking and comparison*, not sole gating.
- Hard blockers (tests failing, security critical, schema failure) => immediate fail.
- Type coverage uses binary health (pass/fail + error count trend), not % coverage.
- Complexity/LOC penalty is capped and rewards simplification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


# ---------------------------------------------------------------------------
# Hard blocker definitions
# ---------------------------------------------------------------------------

#: Validator names that trigger immediate failure regardless of composite score.
HARD_BLOCKER_VALIDATORS: Set[str] = {"pytest", "ruff"}

#: Error classifications that are always hard blockers.
HARD_BLOCKER_CLASSIFICATIONS: Set[str] = {
    "security_critical",
    "schema_failure",
    "drift_check_fail",
}


# ---------------------------------------------------------------------------
# Weight configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScoreWeights:
    """Configurable weights for composite score components.  Must sum to 1.0."""

    tests: float = 0.40
    lint: float = 0.20
    type_health: float = 0.20
    security: float = 0.15
    simplicity: float = 0.05

    def __post_init__(self) -> None:
        total = self.tests + self.lint + self.type_health + self.security + self.simplicity
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"ScoreWeights must sum to 1.0, got {total:.3f}")


DEFAULT_WEIGHTS = ScoreWeights()


# ---------------------------------------------------------------------------
# Score result
# ---------------------------------------------------------------------------

@dataclass
class QualityScore:
    """Result of a composite quality score computation."""

    composite: float  # 0-100 normalized
    hard_blocked: bool  # True if any hard blocker triggered
    hard_blockers: List[str]  # list of blocker descriptions

    # Per-component sub-scores (0-100 each)
    tests_score: float = 0.0
    lint_score: float = 0.0
    type_health_score: float = 0.0
    security_score: float = 0.0
    simplicity_score: float = 100.0  # default: no penalty

    # Raw counts for diagnostics
    tests_passed: int = 0
    tests_failed: int = 0
    lint_errors: int = 0
    type_errors: int = 0
    security_findings: int = 0
    security_critical: int = 0
    loc_delta: int = 0

    weights: ScoreWeights = field(default_factory=lambda: DEFAULT_WEIGHTS)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "composite": round(self.composite, 2),
            "hard_blocked": self.hard_blocked,
            "hard_blockers": self.hard_blockers,
            "components": {
                "tests": round(self.tests_score, 2),
                "lint": round(self.lint_score, 2),
                "type_health": round(self.type_health_score, 2),
                "security": round(self.security_score, 2),
                "simplicity": round(self.simplicity_score, 2),
            },
            "raw": {
                "tests_passed": self.tests_passed,
                "tests_failed": self.tests_failed,
                "lint_errors": self.lint_errors,
                "type_errors": self.type_errors,
                "security_findings": self.security_findings,
                "security_critical": self.security_critical,
                "loc_delta": self.loc_delta,
            },
        }


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def _extract_pytest_counts(validation_rows: List[Dict[str, Any]]) -> tuple[int, int]:
    """Extract (passed, failed) test counts from pytest validator results."""
    for row in validation_rows:
        if row.get("name") != "pytest":
            continue
        diag = row.get("diagnostics") or {}
        passed = diag.get("passed", 0)
        failed = diag.get("failed", 0)
        errors = diag.get("errors", 0)
        # If no diagnostics, fall back to ok flag
        if passed == 0 and failed == 0 and errors == 0:
            return (1, 0) if row.get("ok") else (0, 1)
        return (passed, failed + errors)
    return (0, 0)  # pytest not run


def _extract_lint_error_count(validation_rows: List[Dict[str, Any]]) -> int:
    """Extract total lint error count from ruff validator results."""
    for row in validation_rows:
        if row.get("name") != "ruff":
            continue
        diag = row.get("diagnostics") or {}
        count = diag.get("error_count", 0)
        if count == 0 and not row.get("ok"):
            return 1  # at least one error
        return count
    return 0


def _extract_type_health(validation_rows: List[Dict[str, Any]]) -> tuple[bool, int]:
    """Extract (passed: bool, error_count: int) from mypy validator results."""
    for row in validation_rows:
        if row.get("name") != "mypy":
            continue
        diag = row.get("diagnostics") or {}
        error_count = diag.get("error_count", 0)
        ok = row.get("ok", False)
        if error_count == 0 and not ok:
            error_count = 1
        return (ok, error_count)
    return (True, 0)  # mypy not run => healthy


def _extract_security_findings(
    validation_rows: List[Dict[str, Any]],
) -> tuple[int, int]:
    """Extract (total_findings, critical_findings) from security validators."""
    total = 0
    critical = 0
    for row in validation_rows:
        if row.get("name") not in ("bandit", "pip_audit", "semgrep"):
            continue
        diag = row.get("diagnostics") or {}
        findings = diag.get("finding_count", 0)
        crit = diag.get("critical_count", 0)
        if findings == 0 and not row.get("ok"):
            findings = 1
        total += findings
        critical += crit
        # Check error classification for critical security
        ec = row.get("error_classification") or ""
        if "critical" in ec.lower() or "high" in ec.lower():
            critical = max(critical, 1)
    return (total, critical)


def _check_hard_blockers(
    validation_rows: List[Dict[str, Any]],
    soft_validators: Optional[Set[str]] = None,
) -> List[str]:
    """Return list of hard blocker descriptions. Empty list means no blockers."""
    blockers: List[str] = []
    _soft = soft_validators or set()

    for row in validation_rows:
        name = row.get("name", "")
        ok = row.get("ok", True)
        ec = row.get("error_classification") or ""

        # Skip soft validators
        if name in _soft:
            continue

        # Hard blocker validator failed
        if not ok and name in HARD_BLOCKER_VALIDATORS:
            blockers.append(f"{name}: hard failure")

        # Hard blocker classification
        if ec in HARD_BLOCKER_CLASSIFICATIONS:
            blockers.append(f"{name}: {ec}")

    return blockers


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def compute_quality_score(
    validation_rows: List[Dict[str, Any]],
    *,
    soft_validators: Optional[Set[str]] = None,
    weights: Optional[ScoreWeights] = None,
    loc_delta: int = 0,
    loc_penalty_cap: float = 10.0,
) -> QualityScore:
    """Compute composite quality score from validator results.

    Parameters
    ----------
    validation_rows:
        List of validator result dicts (as produced by ``validators.run_all``).
    soft_validators:
        Set of validator names whose failures are advisory (not blocking).
    weights:
        Custom score weights.  Defaults to ``DEFAULT_WEIGHTS``.
    loc_delta:
        Net lines-of-code change.  Positive = added, negative = removed.
        Used for simplicity scoring.
    loc_penalty_cap:
        Maximum simplicity penalty in score points (default 10).

    Returns
    -------
    QualityScore with composite 0-100 and hard_blocked flag.
    """
    w = weights or DEFAULT_WEIGHTS

    # --- Hard blockers (immediate fail, independent of score) ---
    hard_blockers = _check_hard_blockers(validation_rows, soft_validators)

    # --- Tests sub-score (0-100) ---
    tests_passed, tests_failed = _extract_pytest_counts(validation_rows)
    total_tests = tests_passed + tests_failed
    if total_tests > 0:
        tests_score = (tests_passed / total_tests) * 100.0
    else:
        tests_score = 100.0  # no tests run => neutral

    # --- Lint sub-score (0-100) ---
    lint_errors = _extract_lint_error_count(validation_rows)
    if lint_errors == 0:
        lint_score = 100.0
    else:
        # Diminishing penalty: 100 -> ~0 as errors increase
        lint_score = max(0.0, 100.0 - (lint_errors * 10.0))

    # --- Type health sub-score (binary health + error count trend) ---
    type_ok, type_errors = _extract_type_health(validation_rows)
    if type_ok:
        type_health_score = 100.0
    elif type_errors <= 2:
        type_health_score = 70.0
    elif type_errors <= 5:
        type_health_score = 40.0
    else:
        type_health_score = max(0.0, 100.0 - (type_errors * 8.0))

    # --- Security sub-score (0-100) ---
    security_findings, security_critical = _extract_security_findings(validation_rows)
    if security_critical > 0:
        security_score = 0.0  # critical findings => zero security score
    elif security_findings == 0:
        security_score = 100.0
    else:
        security_score = max(0.0, 100.0 - (security_findings * 20.0))

    # --- Simplicity sub-score (capped penalty + reward for simplification) ---
    if loc_delta < 0:
        # Net removal => reward (up to +10 bonus, capped at 100)
        simplicity_score = min(100.0, 100.0 + min(abs(loc_delta) * 0.5, 10.0))
    elif loc_delta == 0:
        simplicity_score = 100.0
    else:
        # Penalty for LOC growth, capped
        penalty = min(loc_delta * 0.5, loc_penalty_cap)
        simplicity_score = max(0.0, 100.0 - penalty)

    # --- Composite ---
    composite = (
        w.tests * tests_score
        + w.lint * lint_score
        + w.type_health * type_health_score
        + w.security * security_score
        + w.simplicity * simplicity_score
    )

    return QualityScore(
        composite=composite,
        hard_blocked=len(hard_blockers) > 0,
        hard_blockers=hard_blockers,
        tests_score=tests_score,
        lint_score=lint_score,
        type_health_score=type_health_score,
        security_score=security_score,
        simplicity_score=simplicity_score,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        lint_errors=lint_errors,
        type_errors=type_errors,
        security_findings=security_findings,
        security_critical=security_critical,
        loc_delta=loc_delta,
        weights=w,
    )
