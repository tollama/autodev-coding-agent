"""Adaptive quality gate — smart per-task validator selection.

Selects validators based on:
1. **File-type relevance**: Only run validators relevant to the files being
   modified (e.g. ``ruff``/``mypy`` for ``.py`` files, ``docker_build`` for
   ``Dockerfile``).
2. **Historical pass-rate**: Validators with many consecutive passes can be
   promoted to soft-fail (balanced mode) or skipped entirely (aggressive mode).
3. **Priority ordering**: Recently-failed validators run first, then by failure
   rate descending, then by speed ascending.

Controlled via ``quality_profile["adaptive_gate"]``.  When disabled (default),
the existing behaviour is preserved exactly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALIDATOR_FILE_RELEVANCE: Dict[str, Set[str]] = {
    "ruff": {".py"},
    "mypy": {".py"},
    "pytest": {".py"},
    "bandit": {".py"},
    "pip_audit": {"requirements.txt", "setup.py", "pyproject.toml", "setup.cfg"},
    "semgrep": {".py", ".js", ".ts", ".go", ".yml", ".yaml"},
    "docker_build": {"Dockerfile", "docker-compose.yml", "docker-compose.yaml"},
    "sbom": {"requirements.txt", "package.json", "pyproject.toml"},
    "dependency_lock": {"requirements.txt", "requirements-dev.txt", "pyproject.toml"},
}

_MINIMUM_VALIDATORS: List[str] = ["ruff"]
_DEFAULT_CONSECUTIVE_PASS_THRESHOLD = 5
_DEFAULT_HISTORY_WINDOW = 5
_VALID_MODES = {"conservative", "balanced", "aggressive"}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ValidatorStats:
    """Aggregated statistics for a single validator across recent runs."""

    name: str
    total_runs: int = 0
    total_passes: int = 0
    total_failures: int = 0
    consecutive_passes: int = 0  # reset on any failure
    avg_duration_ms: int = 0

    @property
    def pass_rate(self) -> float:
        if self.total_runs <= 0:
            return 0.0
        return self.total_passes / self.total_runs


@dataclass(frozen=True)
class AdaptiveGateConfig:
    """Configuration for the adaptive quality gate."""

    enabled: bool = False
    mode: str = "balanced"  # "conservative" | "balanced" | "aggressive"
    consecutive_pass_threshold: int = _DEFAULT_CONSECUTIVE_PASS_THRESHOLD
    history_window: int = _DEFAULT_HISTORY_WINDOW
    never_skip: frozenset[str] = field(default_factory=frozenset)


# ---------------------------------------------------------------------------
# Configuration resolution
# ---------------------------------------------------------------------------


def resolve_adaptive_gate_config(
    quality_profile: Dict[str, Any] | None,
) -> AdaptiveGateConfig:
    """Extract :class:`AdaptiveGateConfig` from *quality_profile*.

    Returns a disabled config when ``quality_profile`` is ``None`` or the
    ``adaptive_gate`` key is missing/invalid.
    """
    if not isinstance(quality_profile, dict):
        return AdaptiveGateConfig()

    raw = quality_profile.get("adaptive_gate")
    if not isinstance(raw, dict):
        return AdaptiveGateConfig()

    enabled = raw.get("enabled", False) is True
    if not enabled:
        return AdaptiveGateConfig()

    mode = str(raw.get("mode", "balanced"))
    if mode not in _VALID_MODES:
        mode = "balanced"

    threshold = _safe_int(raw.get("consecutive_pass_threshold", _DEFAULT_CONSECUTIVE_PASS_THRESHOLD))
    if threshold < 1:
        threshold = _DEFAULT_CONSECUTIVE_PASS_THRESHOLD

    window = _safe_int(raw.get("history_window", _DEFAULT_HISTORY_WINDOW))
    if window < 1:
        window = _DEFAULT_HISTORY_WINDOW

    never_skip_raw = raw.get("never_skip", [])
    if isinstance(never_skip_raw, list):
        never_skip = frozenset(str(v) for v in never_skip_raw)
    else:
        never_skip = frozenset()

    return AdaptiveGateConfig(
        enabled=True,
        mode=mode,
        consecutive_pass_threshold=threshold,
        history_window=window,
        never_skip=never_skip,
    )


# ---------------------------------------------------------------------------
# Validator stats loading from perf_baseline.json
# ---------------------------------------------------------------------------


def load_validator_stats(
    perf_baseline: Dict[str, Any],
    window: int = _DEFAULT_HISTORY_WINDOW,
) -> Dict[str, ValidatorStats]:
    """Build per-validator stats from the most recent *window* runs.

    Each run entry is expected to have a ``validator_stats`` list of dicts
    with keys ``name``, ``passed`` (bool), ``duration_ms``.
    """
    runs = perf_baseline.get("runs", [])
    if not isinstance(runs, list) or not runs:
        return {}

    recent = runs[-window:] if len(runs) > window else runs

    # Accumulate per-validator data
    acc: Dict[str, Dict[str, Any]] = {}  # name → {passes, failures, durations, consecutive}
    for run in recent:
        if not isinstance(run, dict):
            continue
        vstats = run.get("validator_stats", [])
        if not isinstance(vstats, list):
            continue
        for entry in vstats:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", ""))
            if not name:
                continue
            if name not in acc:
                acc[name] = {"passes": 0, "failures": 0, "durations": [], "consecutive": 0}
            passed = entry.get("passed", False) is True
            if passed:
                acc[name]["passes"] += 1
                acc[name]["consecutive"] += 1
            else:
                acc[name]["failures"] += 1
                acc[name]["consecutive"] = 0
            dur = _safe_int(entry.get("duration_ms", 0))
            if dur > 0:
                acc[name]["durations"].append(dur)

    result: Dict[str, ValidatorStats] = {}
    for name, data in acc.items():
        total = data["passes"] + data["failures"]
        durations = data["durations"]
        avg_dur = int(sum(durations) / len(durations)) if durations else 0
        result[name] = ValidatorStats(
            name=name,
            total_runs=total,
            total_passes=data["passes"],
            total_failures=data["failures"],
            consecutive_passes=data["consecutive"],
            avg_duration_ms=avg_dur,
        )
    return result


# ---------------------------------------------------------------------------
# File-type relevance
# ---------------------------------------------------------------------------


def _is_validator_relevant(validator_name: str, task_files: List[str]) -> bool:
    """Check if *validator_name* is relevant to the given *task_files*.

    A validator is relevant if any task file's extension or basename appears in
    the validator's relevance set.  Validators not registered in
    ``_VALIDATOR_FILE_RELEVANCE`` are **always** considered relevant (safe
    fallback).
    """
    relevance = _VALIDATOR_FILE_RELEVANCE.get(validator_name)
    if relevance is None:
        return True  # unknown validator → always relevant

    for fpath in task_files:
        basename = os.path.basename(fpath)
        _, ext = os.path.splitext(fpath)
        if basename in relevance or ext.lower() in relevance:
            return True
    return False


# ---------------------------------------------------------------------------
# Priority sorting
# ---------------------------------------------------------------------------


def _priority_sort(
    validators: List[str],
    stats: Dict[str, ValidatorStats],
) -> List[str]:
    """Sort validators by signal priority.

    Order:
    1. Recently failed (consecutive_passes == 0) first.
    2. Higher failure rate first.
    3. Faster (lower avg_duration_ms) first.
    """
    def _sort_key(name: str) -> tuple:
        st = stats.get(name)
        if st is None:
            # Unknown stats → middle priority
            return (1, 0.5, 0)
        recently_failed = 0 if st.consecutive_passes == 0 and st.total_failures > 0 else 1
        return (recently_failed, st.pass_rate, st.avg_duration_ms)

    return sorted(validators, key=_sort_key)


# ---------------------------------------------------------------------------
# Main selection function
# ---------------------------------------------------------------------------


def select_validators(
    task_files: List[str],
    resolved_validators: List[str],
    has_validator_focus: bool,
    config: AdaptiveGateConfig,
    stats: Dict[str, ValidatorStats],
    per_task_soft: Set[str],
) -> Tuple[List[str], Set[str]]:
    """Select validators adaptively for a single task.

    Parameters
    ----------
    task_files:
        Files modified by the task (paths).
    resolved_validators:
        Validators already resolved by ``_resolve_validators()``.
    has_validator_focus:
        ``True`` if the task has an explicit ``validator_focus``.
    config:
        Adaptive gate configuration.
    stats:
        Historical validator statistics.
    per_task_soft:
        Current set of soft-fail validators for the task.

    Returns
    -------
    (selected_validators, promoted_to_soft)
        ``selected_validators``: ordered list of validators to run.
        ``promoted_to_soft``: validators promoted from hard → soft-fail
        based on historical pass rate.
    """
    promoted: Set[str] = set()

    # 1. Disabled → passthrough
    if not config.enabled:
        return list(resolved_validators), promoted

    # 2. validator_focus present → no filtering, only priority sort
    if has_validator_focus:
        sorted_validators = _priority_sort(resolved_validators, stats)
        return sorted_validators, promoted

    # 3. File-type filtering
    if task_files:
        filtered = [
            v for v in resolved_validators
            if _is_validator_relevant(v, task_files)
        ]
    else:
        filtered = list(resolved_validators)

    # 4. History-based filtering/promotion
    if config.mode in ("balanced", "aggressive") and stats:
        still_selected: List[str] = []
        for v in filtered:
            st = stats.get(v)
            if st is None:
                still_selected.append(v)
                continue
            # Check consecutive pass threshold
            if st.consecutive_passes >= config.consecutive_pass_threshold:
                # Never skip protected validators
                if v in config.never_skip:
                    still_selected.append(v)
                    continue
                if config.mode == "aggressive":
                    # Skip entirely (don't add to still_selected)
                    continue
                else:
                    # Balanced: promote to soft-fail
                    still_selected.append(v)
                    if v not in per_task_soft:
                        promoted.add(v)
            else:
                still_selected.append(v)
        filtered = still_selected

    # 5. Minimum validator guarantee
    if not filtered:
        for fallback in _MINIMUM_VALIDATORS:
            if fallback in resolved_validators:
                filtered.append(fallback)
                break
        if not filtered and resolved_validators:
            filtered.append(resolved_validators[0])

    # 6. Priority sort
    result = _priority_sort(filtered, stats)
    return result, promoted


# ---------------------------------------------------------------------------
# Validator stats collection (end-of-run)
# ---------------------------------------------------------------------------


def collect_validator_stats(
    quality_summary: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Extract per-validator pass/fail/duration from *quality_summary*.

    Aggregates across all tasks in the run.  Returns a list of dicts with
    keys ``name``, ``passed`` (bool — True if passed in all tasks),
    ``duration_ms`` (total across tasks), ``task_count``.

    These records are stored in ``perf_baseline.json`` for use by
    ``load_validator_stats`` in subsequent runs.
    """
    tasks = quality_summary.get("tasks", [])
    if not isinstance(tasks, list):
        return []

    # Aggregate per-validator: {name: {passed: int, failed: int, duration: int, tasks: int}}
    agg: Dict[str, Dict[str, int]] = {}

    for task in tasks:
        if not isinstance(task, dict):
            continue
        # Use last_validation or attempt_trend's last validation
        last_val = task.get("last_validation", [])
        if not isinstance(last_val, list):
            continue
        for row in last_val:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name", ""))
            if not name:
                continue
            if name not in agg:
                agg[name] = {"passed": 0, "failed": 0, "duration": 0, "tasks": 0}
            agg[name]["tasks"] += 1
            ok = row.get("ok", False) is True
            if ok:
                agg[name]["passed"] += 1
            else:
                agg[name]["failed"] += 1
            agg[name]["duration"] += _safe_int(row.get("duration_ms", 0))

    result: List[Dict[str, Any]] = []
    for name, data in sorted(agg.items()):
        result.append({
            "name": name,
            "passed": data["failed"] == 0,  # passed in ALL tasks
            "duration_ms": data["duration"],
            "task_count": data["tasks"],
        })
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_int(value: object) -> int:
    """Coerce to int, returning 0 on failure."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
