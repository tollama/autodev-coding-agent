"""Validator dependency graph — early-exit on prerequisite failures.

Defines dependencies between validators (e.g. ruff → mypy → pytest) and
provides:

* **Topological execution order** with speed-based tie-breaking.
* **Skip check** — if a prerequisite failed, downstream validators are
  skipped with ``status="skipped_dependency"``.
* **Skipped result factory** — produces Validation-compatible dicts.

Pure function module — no side effects, no file writes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Tuple


# ---------------------------------------------------------------------------
# Static dependency map: dependent → [prerequisites]
# ---------------------------------------------------------------------------

_DEPENDENCY_EDGES: Dict[str, List[str]] = {
    "mypy": ["ruff"],            # syntax errors break type checking
    "pytest": ["ruff", "mypy"],  # syntax / type errors break tests
    "bandit": ["ruff"],          # syntax errors break security analysis
}

_VALID_MODES = frozenset({"strict", "relaxed"})


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidatorGraphConfig:
    """Configuration for dependency-aware validator execution."""

    enabled: bool = False
    mode: str = "strict"  # "strict" | "relaxed"
    skip_on_soft_fail: bool = False
    custom_edges: Dict[str, List[str]] = field(default_factory=dict)


def resolve_validator_graph_config(
    quality_profile: Dict[str, Any] | None,
) -> ValidatorGraphConfig:
    """Extract validator graph config from *quality_profile*."""
    if not isinstance(quality_profile, dict):
        return ValidatorGraphConfig()

    raw = quality_profile.get("validator_graph")
    if not isinstance(raw, dict):
        return ValidatorGraphConfig()

    enabled = raw.get("enabled", False) is True
    if not enabled:
        return ValidatorGraphConfig()

    mode = str(raw.get("mode", "strict"))
    if mode not in _VALID_MODES:
        mode = "strict"

    skip_on_soft = raw.get("skip_on_soft_fail", False) is True

    custom_raw = raw.get("custom_edges", {})
    custom: Dict[str, List[str]] = {}
    if isinstance(custom_raw, dict):
        for k, v in custom_raw.items():
            if isinstance(v, list):
                custom[str(k)] = [str(d) for d in v if isinstance(d, str)]

    return ValidatorGraphConfig(
        enabled=True,
        mode=mode,
        skip_on_soft_fail=skip_on_soft,
        custom_edges=custom,
    )


# ---------------------------------------------------------------------------
# Edge merging
# ---------------------------------------------------------------------------


def _merged_edges(config: ValidatorGraphConfig) -> Dict[str, List[str]]:
    """Merge static edges with ``config.custom_edges``."""
    edges: Dict[str, List[str]] = {}
    for name, deps in _DEPENDENCY_EDGES.items():
        edges[name] = list(deps)
    for name, deps in config.custom_edges.items():
        existing = edges.get(name, [])
        for d in deps:
            if d not in existing:
                existing.append(d)
        edges[name] = existing
    return edges


# ---------------------------------------------------------------------------
# Topological execution order (Kahn's algorithm)
# ---------------------------------------------------------------------------


def resolve_execution_order(
    run_set: List[str],
    stats: Dict[str, Any] | None,
    config: ValidatorGraphConfig,
) -> List[str]:
    """Return *run_set* in topological order with speed tie-breaking.

    Among validators at the same dependency level, those with lower
    ``avg_duration_ms`` run first.  If *config* is disabled, returns
    *run_set* unchanged.  Falls back to *run_set* on cycle detection.
    """
    if not config.enabled or len(run_set) <= 1:
        return list(run_set)

    members = set(run_set)
    edges = _merged_edges(config)

    # Build adjacency: prerequisite → [dependents], filtered to run_set
    adj: Dict[str, List[str]] = {v: [] for v in run_set}
    in_degree: Dict[str, int] = {v: 0 for v in run_set}

    for dependent, prereqs in edges.items():
        if dependent not in members:
            continue
        for prereq in prereqs:
            if prereq not in members:
                continue
            adj.setdefault(prereq, []).append(dependent)
            in_degree[dependent] = in_degree.get(dependent, 0) + 1

    # Seed queue with zero in-degree nodes, sorted by speed
    safe_stats = stats if isinstance(stats, dict) else {}
    queue: List[str] = sorted(
        [v for v in run_set if in_degree.get(v, 0) == 0],
        key=lambda v: _avg_duration(safe_stats, v),
    )

    result: List[str] = []
    while queue:
        node = queue.pop(0)
        result.append(node)
        for neighbour in adj.get(node, []):
            in_degree[neighbour] -= 1
            if in_degree[neighbour] == 0:
                # Insert sorted by speed among pending zero-degree nodes
                queue.append(neighbour)
                queue.sort(key=lambda v: _avg_duration(safe_stats, v))

    # Cycle detection: if not all nodes visited, fall back
    if len(result) != len(run_set):
        return list(run_set)

    return result


def _avg_duration(stats: Dict[str, Any], name: str) -> int:
    """Extract avg_duration_ms from stats, defaulting to 0."""
    entry = stats.get(name)
    if isinstance(entry, dict):
        return _safe_int(entry.get("avg_duration_ms", 0))
    if hasattr(entry, "avg_duration_ms"):
        return _safe_int(getattr(entry, "avg_duration_ms", 0))
    return 0


# ---------------------------------------------------------------------------
# Skip check
# ---------------------------------------------------------------------------


def should_skip(
    name: str,
    completed_results: Dict[str, Dict[str, Any]],
    config: ValidatorGraphConfig,
    soft_validators: Set[str] | None = None,
) -> Tuple[bool, str]:
    """Check if *name* should be skipped due to prerequisite failure.

    Returns ``(True, reason)`` if skipped, ``(False, "")`` otherwise.
    """
    if not config.enabled:
        return False, ""

    edges = _merged_edges(config)
    prereqs = edges.get(name)
    if not prereqs:
        return False, ""

    soft_set = soft_validators or set()

    for prereq in prereqs:
        result = completed_results.get(prereq)
        if result is None:
            # Prerequisite not in run_set → no dependency applies
            continue

        if result.get("ok", True):
            continue

        # Prerequisite failed — decide whether to skip
        prereq_is_soft = prereq in soft_set

        if prereq_is_soft and not config.skip_on_soft_fail:
            continue

        # Relaxed mode: tool_unavailable does not trigger skip
        if config.mode == "relaxed":
            ec = result.get("error_classification", "")
            if ec == "tool_unavailable":
                continue

        return True, f"prerequisite '{prereq}' failed"

    return False, ""


# ---------------------------------------------------------------------------
# Skipped result factory
# ---------------------------------------------------------------------------


def make_skipped_result(
    name: str,
    reason: str,
    failed_prerequisite: str,
) -> Dict[str, Any]:
    """Create a Validation-compatible dict for a skipped validator."""
    return {
        "name": name,
        "ok": False,
        "status": "skipped_dependency",
        "phase": "per_task",
        "cmd": [],
        "returncode": -1,
        "duration_ms": 0,
        "tool_version": "n/a",
        "error_classification": "skipped_dependency",
        "stdout": "",
        "stderr": f"Skipped: {reason}",
        "note": f"Dependency skip: {failed_prerequisite} failed",
        "diagnostics": {
            "skip_reason": reason,
            "failed_prerequisite": failed_prerequisite,
        },
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_int(value: object) -> int:
    """Coerce to int, returning 0 on failure."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
