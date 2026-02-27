"""Self-Healing Pipeline: failure categorization, repair strategy selection, and escalation."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PERSISTENT_ERROR_STRIKE_THRESHOLD = 3


# ---------------------------------------------------------------------------
# Failure categories
# ---------------------------------------------------------------------------


class FailureCategory(str, Enum):
    """Actionable failure categories ordered by fix priority (lower = fix first)."""

    SYNTAX_ERROR = "syntax_error"
    IMPORT_ERROR = "import_error"
    MISSING_DEPENDENCY = "missing_dependency"
    TYPE_ERROR = "type_error"
    LINT_ERROR = "lint_error"
    TEST_RUNTIME_ERROR = "test_runtime_error"
    TEST_LOGIC_ERROR = "test_logic_error"
    SECURITY_FINDING = "security_finding"
    TOOL_UNAVAILABLE = "tool_unavailable"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Analysis result
# ---------------------------------------------------------------------------


@dataclass
class FailureAnalysis:
    """Structured analysis of a single validation failure."""

    validator_name: str
    category: FailureCategory
    raw_error_classification: str | None
    summary: str
    failing_files: List[str]
    failing_lines: List[str]
    confidence: float  # 0.0-1.0


# ---------------------------------------------------------------------------
# Error fingerprinting
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ErrorFingerprint:
    """Stable identity for a single error instance.

    Two errors with the same file, line, error_type, and normalised text
    produce the same *digest*, enabling deduplication and persistence tracking.
    """

    file: str
    line: str        # "42" or "" if unknown
    error_type: str  # e.g. "F401", "SyntaxError", "import_error"
    key_text: str    # normalised short error snippet (120 chars max)
    digest: str      # hex digest of the above fields (16 chars)

    def __hash__(self) -> int:
        return hash(self.digest)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ErrorFingerprint):
            return NotImplemented
        return self.digest == other.digest


@dataclass
class FingerprintedFailure:
    """A :class:`FailureAnalysis` enriched with per-error fingerprints."""

    analysis: FailureAnalysis
    fingerprints: List[ErrorFingerprint]
    deduplicated_count: int  # total errors before dedup

    @property
    def unique_count(self) -> int:
        return len(self.fingerprints)


# -- Fingerprint helpers ----------------------------------------------------

_RUFF_RULE_RE = re.compile(r"([A-Z]+\d{3,4})")
_EXCEPTION_CLASS_RE = re.compile(
    r"((?:[A-Z][a-z]+)+Error|(?:[A-Z][a-z]+)+Exception)"
)


def _normalize_error_text(text: str) -> str:
    """Normalise error text for stable fingerprinting.

    Strips whitespace, lowercases, removes object-id hex addresses,
    normalises line-number references, and truncates to 120 characters.
    """
    text = text.strip().lower()
    text = re.sub(r"0x[0-9a-f]+", "<addr>", text)
    text = re.sub(r"line \d+", "line <N>", text)
    return text[:120]


def _extract_error_type_from_text(row: Dict[str, Any], text: str) -> str:
    """Extract a short error-type label from a validation row."""
    name = row.get("name", "")
    if name == "ruff":
        match = _RUFF_RULE_RE.search(text)
        if match:
            return match.group(1)
        return "ruff_error"
    if name == "mypy":
        code_match = re.search(r"\[([a-z-]+)\]", text)
        if code_match:
            return f"mypy_{code_match.group(1)}"
        return "mypy_error"
    exc_match = _EXCEPTION_CLASS_RE.search(text)
    if exc_match:
        return exc_match.group(1)
    error_class = row.get("error_classification") or ""
    if error_class:
        return error_class
    return "unknown"


def fingerprint_error(
    file: str,
    line: str,
    error_type: str,
    raw_text: str,
) -> ErrorFingerprint:
    """Create a stable fingerprint for a single error instance.

    Pure function. No LLM calls. Deterministic: same inputs → same digest.
    """
    key_text = _normalize_error_text(raw_text)
    payload = f"{file}|{line}|{error_type}|{key_text}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return ErrorFingerprint(
        file=file,
        line=line,
        error_type=error_type,
        key_text=key_text,
        digest=digest,
    )


def fingerprint_validation_row(row: Dict[str, Any]) -> List[ErrorFingerprint]:
    """Extract all individual error fingerprints from one validation row.

    Parses ``diagnostics.locations``, ``diagnostics.failed_tests``, and
    ``stdout``/``stderr`` to identify individual error instances.  Returns
    one fingerprint per distinct error location (max 20).
    """
    if row.get("ok"):
        return []

    text = _extract_error_text(row)
    diag = row.get("diagnostics") or {}
    fingerprints: List[ErrorFingerprint] = []
    seen_digests: set[str] = set()

    def _add(fp: ErrorFingerprint) -> None:
        if fp.digest not in seen_digests:
            seen_digests.add(fp.digest)
            fingerprints.append(fp)

    # Strategy 1: diagnostics locations
    locations = diag.get("locations", []) if isinstance(diag, dict) else []
    if locations:
        for loc in locations:
            if not isinstance(loc, str):
                continue
            parts = loc.split(":")
            file = parts[0] if parts else row.get("name", "")
            line_no = parts[1] if len(parts) > 1 else ""
            loc_text = ""
            for text_line in text.splitlines():
                if loc in text_line:
                    loc_text = text_line
                    break
            error_type = _extract_error_type_from_text(row, loc_text or text)
            _add(fingerprint_error(file, line_no, error_type, loc_text or text))

    # Strategy 2: pytest failed_tests
    if not fingerprints:
        failed_tests = diag.get("failed_tests", []) if isinstance(diag, dict) else []
        for ft in failed_tests:
            if not isinstance(ft, dict):
                continue
            test_name = ft.get("test", "")
            message = ft.get("message", "")
            file = test_name.split("::")[0] if "::" in test_name else row.get("name", "")
            error_type = _extract_error_type_from_text(row, message or text)
            _add(fingerprint_error(file, "", error_type, message or text))

    # Strategy 3: scan stdout/stderr for file:line patterns
    if not fingerprints:
        for match in _FILE_LOCATION_RE.finditer(text):
            file = match.group(1)
            line_no = match.group(2)
            start = text.rfind("\n", 0, match.start()) + 1
            end = text.find("\n", match.end())
            if end == -1:
                end = len(text)
            line_text = text[start:end]
            error_type = _extract_error_type_from_text(row, line_text)
            _add(fingerprint_error(file, line_no, error_type, line_text))

    # Fallback: single fingerprint for the whole row
    if not fingerprints:
        name = row.get("name", "")
        error_type = _extract_error_type_from_text(row, text)
        _add(fingerprint_error(name, "", error_type, text[:200]))

    return fingerprints[:20]


def fingerprint_failures(
    validation_rows: List[Dict[str, Any]],
) -> List[FingerprintedFailure]:
    """Analyse and fingerprint all failed validation rows.

    Each failed row is converted to a :class:`FingerprintedFailure`
    grouping a :class:`FailureAnalysis` with its per-error fingerprints.
    """
    results: List[FingerprintedFailure] = []
    for row in validation_rows:
        if row.get("ok"):
            continue
        analysis = categorize_failure(row)
        all_fps = fingerprint_validation_row(row)
        seen: dict[str, ErrorFingerprint] = {}
        for fp in all_fps:
            if fp.digest not in seen:
                seen[fp.digest] = fp
        results.append(FingerprintedFailure(
            analysis=analysis,
            fingerprints=list(seen.values()),
            deduplicated_count=len(all_fps),
        ))
    return results


# ---------------------------------------------------------------------------
# Regex patterns (compiled once)
# ---------------------------------------------------------------------------

_IMPORT_ERROR_RE = re.compile(
    r"(ModuleNotFoundError|ImportError|No module named|cannot import name)",
    re.IGNORECASE,
)
_TYPE_ERROR_RE = re.compile(
    r"(TypeError|Incompatible|has no attribute|mypy.*error|"
    r"Argument.*has incompatible type|Missing return statement|"
    r"incompatible type|Return type)",
    re.IGNORECASE,
)
_SYNTAX_ERROR_RE = re.compile(
    r"(SyntaxError|IndentationError|TabError|invalid syntax|unexpected indent)",
    re.IGNORECASE,
)
_ASSERTION_RE = re.compile(
    r"(AssertionError|assert\s|assertEqual|assertTrue|FAILED)",
    re.IGNORECASE,
)
_RUNTIME_ERROR_RE = re.compile(
    r"(RuntimeError|KeyError|ValueError|IndexError|AttributeError|"
    r"ZeroDivisionError|NameError|FileNotFoundError|OSError|"
    r"PermissionError|RecursionError|StopIteration)",
    re.IGNORECASE,
)
_SECURITY_RE = re.compile(
    r"(bandit|semgrep|hardcoded.*secret|sql.*injection|B\d{3}:|severity:)",
    re.IGNORECASE,
)
_FILE_LOCATION_RE = re.compile(r"([a-zA-Z0-9_/\\.-]+\.py):(\d+)")


# ---------------------------------------------------------------------------
# Categorization
# ---------------------------------------------------------------------------


def _extract_error_text(row: Dict[str, Any]) -> str:
    """Combine stdout + stderr for pattern matching."""
    stdout = row.get("stdout", "") or ""
    stderr = row.get("stderr", "") or ""
    return f"{stdout}\n{stderr}"


def _extract_locations(row: Dict[str, Any]) -> tuple[List[str], List[str]]:
    """Extract failing file paths and line locations from diagnostics/output."""
    files: List[str] = []
    lines: List[str] = []

    diag = row.get("diagnostics")
    if isinstance(diag, dict):
        for loc in diag.get("locations", []):
            if isinstance(loc, str):
                lines.append(loc)
                parts = loc.split(":")
                if parts:
                    files.append(parts[0])
        for test in diag.get("failed_tests", []):
            if isinstance(test, dict):
                test_name = test.get("test", "")
                if "::" in test_name:
                    fpath = test_name.split("::")[0]
                    if fpath not in files:
                        files.append(fpath)

    # Fallback: scan stdout/stderr for file:line patterns
    if not lines:
        text = _extract_error_text(row)
        for match in _FILE_LOCATION_RE.finditer(text):
            loc = f"{match.group(1)}:{match.group(2)}"
            lines.append(loc)
            if match.group(1) not in files:
                files.append(match.group(1))

    return files[:10], lines[:10]


def categorize_failure(row: Dict[str, Any]) -> FailureAnalysis:
    """Categorize a single serialized validation row into a FailureAnalysis.

    Pure function. No LLM calls. Works on the dict output of Validators.serialize().
    """
    name = row.get("name", "")
    error_class = row.get("error_classification")
    text = _extract_error_text(row)
    failing_files, failing_lines = _extract_locations(row)

    # 1. Tool unavailable (highest confidence, from existing classification)
    if error_class == "tool_unavailable":
        return FailureAnalysis(
            validator_name=name,
            category=FailureCategory.TOOL_UNAVAILABLE,
            raw_error_classification=error_class,
            summary=f"{name} tool is not available in the environment.",
            failing_files=failing_files,
            failing_lines=failing_lines,
            confidence=1.0,
        )

    # 2. Validator-name-based fast path
    if name == "mypy":
        return FailureAnalysis(
            validator_name=name,
            category=FailureCategory.TYPE_ERROR,
            raw_error_classification=error_class,
            summary="mypy type checking failed.",
            failing_files=failing_files,
            failing_lines=failing_lines,
            confidence=0.9,
        )

    if name == "ruff":
        return FailureAnalysis(
            validator_name=name,
            category=FailureCategory.LINT_ERROR,
            raw_error_classification=error_class,
            summary="ruff linting failed.",
            failing_files=failing_files,
            failing_lines=failing_lines,
            confidence=0.9,
        )

    if name in {"bandit", "semgrep"} or error_class == "policy_violation":
        return FailureAnalysis(
            validator_name=name,
            category=FailureCategory.SECURITY_FINDING,
            raw_error_classification=error_class,
            summary=f"{name} security scan found violations.",
            failing_files=failing_files,
            failing_lines=failing_lines,
            confidence=0.9,
        )

    if name == "pip_audit" or error_class == "warning_offline_or_vulnerable":
        return FailureAnalysis(
            validator_name=name,
            category=FailureCategory.MISSING_DEPENDENCY,
            raw_error_classification=error_class,
            summary="pip_audit found vulnerable or missing dependencies.",
            failing_files=failing_files,
            failing_lines=failing_lines,
            confidence=0.8,
        )

    if name == "dependency_lock":
        return FailureAnalysis(
            validator_name=name,
            category=FailureCategory.MISSING_DEPENDENCY,
            raw_error_classification=error_class,
            summary="Dependency lock check failed.",
            failing_files=failing_files,
            failing_lines=failing_lines,
            confidence=0.85,
        )

    # 3. Pytest sub-classification
    if name == "pytest":
        return _categorize_pytest(row, text, error_class, failing_files, failing_lines)

    # 4. Generic: scan text against patterns (priority order)
    return _categorize_by_text(name, text, error_class, failing_files, failing_lines)


def _categorize_pytest(
    row: Dict[str, Any],
    text: str,
    error_class: str | None,
    failing_files: List[str],
    failing_lines: List[str],
) -> FailureAnalysis:
    """Sub-classify pytest failures using diagnostics + output text."""
    diag = row.get("diagnostics") or {}

    # Priority-ordered text checks
    if _SYNTAX_ERROR_RE.search(text):
        return FailureAnalysis(
            validator_name="pytest",
            category=FailureCategory.SYNTAX_ERROR,
            raw_error_classification=error_class,
            summary="Syntax error detected in test collection or execution.",
            failing_files=failing_files,
            failing_lines=failing_lines,
            confidence=0.95,
        )

    if _IMPORT_ERROR_RE.search(text):
        return FailureAnalysis(
            validator_name="pytest",
            category=FailureCategory.IMPORT_ERROR,
            raw_error_classification=error_class,
            summary="Import error: a module or name could not be found.",
            failing_files=failing_files,
            failing_lines=failing_lines,
            confidence=0.9,
        )

    if _TYPE_ERROR_RE.search(text):
        return FailureAnalysis(
            validator_name="pytest",
            category=FailureCategory.TYPE_ERROR,
            raw_error_classification=error_class,
            summary="Type error in test execution.",
            failing_files=failing_files,
            failing_lines=failing_lines,
            confidence=0.8,
        )

    # Diagnostics-based classification
    summary = diag.get("summary", {}) if isinstance(diag, dict) else {}
    assertions = diag.get("assertions", []) if isinstance(diag, dict) else []
    failed_count = summary.get("failed", 0) if isinstance(summary, dict) else 0
    errors_count = summary.get("errors", 0) if isinstance(summary, dict) else 0

    if failed_count > 0 and assertions:
        return FailureAnalysis(
            validator_name="pytest",
            category=FailureCategory.TEST_LOGIC_ERROR,
            raw_error_classification=error_class,
            summary=f"Test assertions failed ({failed_count} test(s)).",
            failing_files=failing_files,
            failing_lines=failing_lines,
            confidence=0.85,
        )

    if errors_count > 0:
        return FailureAnalysis(
            validator_name="pytest",
            category=FailureCategory.TEST_RUNTIME_ERROR,
            raw_error_classification=error_class,
            summary=f"Test collection/runtime errors ({errors_count} error(s)).",
            failing_files=failing_files,
            failing_lines=failing_lines,
            confidence=0.8,
        )

    # Fallback: check if there are runtime errors in text
    if _RUNTIME_ERROR_RE.search(text):
        return FailureAnalysis(
            validator_name="pytest",
            category=FailureCategory.TEST_RUNTIME_ERROR,
            raw_error_classification=error_class,
            summary="Runtime error during test execution.",
            failing_files=failing_files,
            failing_lines=failing_lines,
            confidence=0.7,
        )

    # Default for pytest
    return FailureAnalysis(
        validator_name="pytest",
        category=FailureCategory.TEST_LOGIC_ERROR,
        raw_error_classification=error_class,
        summary="Test failures detected.",
        failing_files=failing_files,
        failing_lines=failing_lines,
        confidence=0.6,
    )


def _categorize_by_text(
    name: str,
    text: str,
    error_class: str | None,
    failing_files: List[str],
    failing_lines: List[str],
) -> FailureAnalysis:
    """Categorize a generic validator failure by scanning output text."""
    checks: list[tuple[re.Pattern[str], FailureCategory, str, float]] = [
        (_SYNTAX_ERROR_RE, FailureCategory.SYNTAX_ERROR, "Syntax error detected.", 0.8),
        (_IMPORT_ERROR_RE, FailureCategory.IMPORT_ERROR, "Import error detected.", 0.7),
        (_TYPE_ERROR_RE, FailureCategory.TYPE_ERROR, "Type error detected.", 0.7),
        (_SECURITY_RE, FailureCategory.SECURITY_FINDING, "Security finding detected.", 0.7),
        (_ASSERTION_RE, FailureCategory.TEST_LOGIC_ERROR, "Assertion failure detected.", 0.6),
        (_RUNTIME_ERROR_RE, FailureCategory.TEST_RUNTIME_ERROR, "Runtime error detected.", 0.6),
    ]

    for pattern, category, summary, confidence in checks:
        if pattern.search(text):
            return FailureAnalysis(
                validator_name=name,
                category=category,
                raw_error_classification=error_class,
                summary=summary,
                failing_files=failing_files,
                failing_lines=failing_lines,
                confidence=confidence,
            )

    return FailureAnalysis(
        validator_name=name,
        category=FailureCategory.UNKNOWN,
        raw_error_classification=error_class,
        summary=f"{name} validation failed.",
        failing_files=failing_files,
        failing_lines=failing_lines,
        confidence=0.3,
    )


# ---------------------------------------------------------------------------
# Batch analysis
# ---------------------------------------------------------------------------


def analyze_failures(validation_rows: List[Dict[str, Any]]) -> List[FailureAnalysis]:
    """Analyze all failed validation rows and return categorized analyses.

    Only processes rows where row["ok"] is False.
    """
    return [categorize_failure(row) for row in validation_rows if not row.get("ok")]


# ---------------------------------------------------------------------------
# Repair strategies
# ---------------------------------------------------------------------------

# Maps FailureCategory -> (guidance_string, priority)
REPAIR_STRATEGIES: Dict[FailureCategory, tuple[str, int]] = {
    FailureCategory.SYNTAX_ERROR: (
        "Fix syntax errors first. Check for unclosed brackets, missing colons, "
        "invalid indentation, and unterminated strings.",
        0,
    ),
    FailureCategory.IMPORT_ERROR: (
        "Check imports. Ensure all referenced modules exist in the project and are "
        "properly imported. Verify file/module paths match the project structure.",
        1,
    ),
    FailureCategory.MISSING_DEPENDENCY: (
        "Add missing dependencies to requirements.txt with pinned versions. "
        "Ensure all imports correspond to installed packages.",
        2,
    ),
    FailureCategory.TYPE_ERROR: (
        "Fix type annotations and type mismatches. Check function signatures, "
        "return types, and ensure argument types match parameter declarations.",
        3,
    ),
    FailureCategory.LINT_ERROR: (
        "Fix linting issues. Focus on unused imports, formatting, naming conventions, "
        "and code style. Prefer auto-fixable changes where possible.",
        4,
    ),
    FailureCategory.TEST_RUNTIME_ERROR: (
        "Tests crash before assertions. Fix the runtime error first -- check for "
        "missing fixtures, incorrect setup, or exceptions in test helpers.",
        5,
    ),
    FailureCategory.TEST_LOGIC_ERROR: (
        "Test assertions are failing. Review the implementation logic, not the test "
        "expectations. The test defines the correct behavior.",
        6,
    ),
    FailureCategory.SECURITY_FINDING: (
        "Address security findings: avoid hardcoded secrets, use parameterized queries, "
        "sanitize user inputs, and follow secure coding defaults.",
        7,
    ),
    FailureCategory.TOOL_UNAVAILABLE: (
        "A required tool is not available in the environment. Check that the tool "
        "is installed and the command path is correct.",
        8,
    ),
    FailureCategory.UNKNOWN: (
        "Fix the validation failures based on the error output. Focus on the root cause.",
        9,
    ),
}


def select_repair_strategy(analyses: List[FailureAnalysis]) -> str:
    """Select the best composite guidance string for the fixer.

    Deduplicates categories (keeping highest confidence), sorts by priority,
    and composes guidance from the top-3 categories.
    """
    if not analyses:
        return ""

    # Deduplicate: keep highest-confidence per category
    by_category: Dict[FailureCategory, FailureAnalysis] = {}
    for a in analyses:
        existing = by_category.get(a.category)
        if existing is None or a.confidence > existing.confidence:
            by_category[a.category] = a

    # Sort by priority
    sorted_cats = sorted(
        by_category.keys(),
        key=lambda c: REPAIR_STRATEGIES.get(c, ("", 99))[1],
    )

    # Top 3
    top = sorted_cats[:3]
    parts: List[str] = []
    for cat in top:
        guidance, _ = REPAIR_STRATEGIES[cat]
        analysis = by_category[cat]
        line = f"[{cat.value}] {guidance}"
        if analysis.failing_files:
            line += f" Affected files: {', '.join(analysis.failing_files[:5])}"
        parts.append(line)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Progressive escalation
# ---------------------------------------------------------------------------


def determine_escalation_level(
    repeat_failure_count: int,
    max_retries_before_targeted: int,
    repeat_guard_enabled: bool,
) -> int:
    """Determine the escalation level (0/1/2) based on repeat failure count.

    Backward-compatible with existing repeat_failure_guard:
    - Guard disabled → always 0
    - count < max_retries → 0 (normal)
    - count == max_retries → 1 (targeted)
    - count > max_retries → 2 (surgical)
    """
    if not repeat_guard_enabled:
        return 0
    if repeat_failure_count < max_retries_before_targeted:
        return 0
    if repeat_failure_count == max_retries_before_targeted:
        return 1
    return 2


def build_escalated_guidance(
    level: int,
    analyses: List[FailureAnalysis],
    base_guidance: str,
    validation_rows: List[Dict[str, Any]],
) -> str:
    """Build guidance string appropriate for the escalation level.

    Level 0: base guidance + category-specific strategy
    Level 1: base + "TARGETED FIX" + analysis summary + strategy
    Level 2: base + "SURGICAL FIX" + analysis + line diagnostics + assertions
    """
    strategy_guidance = select_repair_strategy(analyses)

    if level == 0:
        if strategy_guidance:
            return f"{base_guidance}\n\nFailure-specific guidance:\n{strategy_guidance}"
        return base_guidance

    # Build analysis summary for level 1+
    summary_parts: List[str] = []
    for a in analyses:
        summary_parts.append(
            f"- {a.validator_name}: {a.category.value} "
            f"(confidence={a.confidence:.1f}) -- {a.summary}"
        )
    analysis_summary = "\n".join(summary_parts) if summary_parts else "No specific analysis available."

    if level == 1:
        return (
            f"{base_guidance}\n\n"
            f"TARGETED FIX -- Failure analysis:\n{analysis_summary}\n\n"
            f"Repair strategy:\n{strategy_guidance}"
        )

    # Level 2: surgical
    file_diagnostics: List[str] = []
    for a in analyses:
        for loc in a.failing_lines[:5]:
            file_diagnostics.append(f"  {loc}: {a.category.value}")
    diag_text = "\n".join(file_diagnostics) if file_diagnostics else "No line-level diagnostics available."

    # Extract assertion text from pytest diagnostics
    assertion_hints: List[str] = []
    for row in validation_rows:
        diag = row.get("diagnostics")
        if isinstance(diag, dict):
            for assertion in diag.get("assertions", [])[:5]:
                assertion_hints.append(f"  E {assertion}")
    assertion_text = "\n".join(assertion_hints) if assertion_hints else ""

    surgical_guidance = (
        f"{base_guidance}\n\n"
        f"SURGICAL FIX -- This is the highest escalation level.\n"
        f"Failure analysis:\n{analysis_summary}\n\n"
        f"Line-level diagnostics:\n{diag_text}\n"
    )
    if assertion_text:
        surgical_guidance += f"\nFailing assertions:\n{assertion_text}\n"
    surgical_guidance += f"\nRepair strategy:\n{strategy_guidance}"

    return surgical_guidance


# ---------------------------------------------------------------------------
# Repair history (cross-task learning)
# ---------------------------------------------------------------------------


@dataclass
class RepairOutcome:
    """Records a single repair attempt outcome."""

    task_id: str
    category: FailureCategory
    escalation_level: int
    resolved: bool
    fingerprints: List[str] = field(default_factory=list)  # digest strings


@dataclass
class RepairHistory:
    """Tracks repair outcomes across tasks within a single run.

    Provides cross-task hints when a similar failure category recurs.
    """

    outcomes: List[RepairOutcome] = field(default_factory=list)

    def record(
        self,
        task_id: str,
        category: FailureCategory,
        level: int,
        resolved: bool,
        fingerprints: List[str] | None = None,
    ) -> None:
        """Record a repair attempt outcome."""
        self.outcomes.append(
            RepairOutcome(
                task_id=task_id,
                category=category,
                escalation_level=level,
                resolved=resolved,
                fingerprints=fingerprints or [],
            )
        )

    def get_hints_for_category(self, category: FailureCategory) -> List[str]:
        """Return hints from previously resolved failures of the same category."""
        resolved = [o for o in self.outcomes if o.category == category and o.resolved]
        if not resolved:
            return []
        hints: List[str] = []
        for o in resolved:
            hints.append(
                f"Previously resolved {category.value} in task '{o.task_id}' "
                f"at escalation level {o.escalation_level}."
            )
        return hints[:3]

    def get_hints_for_fingerprint(self, digest: str) -> List[str]:
        """Return hints from previously resolved failures matching *digest*."""
        resolved = [
            o for o in self.outcomes
            if o.resolved and digest in o.fingerprints
        ]
        if not resolved:
            return []
        hints: List[str] = []
        for o in resolved:
            hints.append(
                f"Previously resolved error fingerprint {digest[:8]}... "
                f"({o.category.value}) in task '{o.task_id}' "
                f"at escalation level {o.escalation_level}."
            )
        return hints[:3]

    def has_prior_resolution(self, category: FailureCategory) -> bool:
        """Check if this failure category has been resolved before in this run."""
        return any(o.category == category and o.resolved for o in self.outcomes)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a dict for JSON persistence."""
        return {
            "outcomes": [
                {
                    "task_id": o.task_id,
                    "category": o.category.value,
                    "escalation_level": o.escalation_level,
                    "resolved": o.resolved,
                    "fingerprints": o.fingerprints,
                }
                for o in self.outcomes
            ],
            "summary": self._summary(),
        }

    def _summary(self) -> Dict[str, Dict[str, int]]:
        """Per-category resolution rates."""
        by_cat: Dict[str, Dict[str, int]] = {}
        for o in self.outcomes:
            cat = o.category.value
            if cat not in by_cat:
                by_cat[cat] = {"total": 0, "resolved": 0}
            by_cat[cat]["total"] += 1
            if o.resolved:
                by_cat[cat]["resolved"] += 1
        return by_cat


# ---------------------------------------------------------------------------
# Persistent error warnings & deduplication
# ---------------------------------------------------------------------------


def build_persistent_error_warnings(
    fingerprint_history: Dict[str, int],
    threshold: int = _PERSISTENT_ERROR_STRIKE_THRESHOLD,
) -> str:
    """Build warning text for fingerprints that exceeded the persistence threshold.

    *fingerprint_history* maps ``digest → count`` of consecutive iterations
    where this fingerprint appeared unresolved.
    """
    persistent = {
        digest: count
        for digest, count in fingerprint_history.items()
        if count >= threshold
    }
    if not persistent:
        return ""

    lines = [
        f"PERSISTENT ERROR WARNING: {len(persistent)} error(s) have reappeared "
        f"{threshold}+ times without being resolved. These require special attention:"
    ]
    for digest, count in sorted(persistent.items(), key=lambda x: -x[1]):
        lines.append(f"  - Fingerprint {digest[:8]}... ({count} consecutive appearances)")
    lines.append(
        "Consider a fundamentally different approach for these errors. "
        "The previous fix strategy is not working."
    )
    return "\n".join(lines)


def deduplicate_for_guidance(
    fingerprinted: List[FingerprintedFailure],
) -> str:
    """Produce a deduplicated summary of errors for inclusion in fixer guidance.

    Groups errors by fingerprint across validators and reports counts
    instead of repeating identical errors.
    """
    if not fingerprinted:
        return ""

    groups: Dict[str, List[tuple[str, str]]] = {}  # digest → [(validator, file)]
    digest_meta: Dict[str, tuple[str, str]] = {}    # digest → (error_type, key_text)

    for ff in fingerprinted:
        for fp in ff.fingerprints:
            if fp.digest not in digest_meta:
                digest_meta[fp.digest] = (fp.error_type, fp.key_text)
            groups.setdefault(fp.digest, []).append(
                (ff.analysis.validator_name, fp.file)
            )

    lines: List[str] = []
    for digest, entries in groups.items():
        error_type, key_text = digest_meta[digest]
        files = sorted(set(e[1] for e in entries))
        total = len(entries)
        if total > 1:
            file_list = ", ".join(files[:5])
            suffix = f" (+{len(files) - 5} more)" if len(files) > 5 else ""
            lines.append(
                f"[{error_type}] {key_text[:80]} -- {total} occurrences in: "
                f"{file_list}{suffix}"
            )
        else:
            lines.append(f"[{error_type}] {key_text[:80]} in {files[0]}")

    return "Deduplicated errors:\n" + "\n".join(lines)
