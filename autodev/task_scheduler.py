"""Intelligent task scheduling with historical execution time hints.

Implements Longest-Processing-Time-first (LPT) scheduling within each
dependency level, using per-task timing data from previous runs stored
in ``.autodev/perf_baseline.json``.
"""

from __future__ import annotations

import hashlib
import heapq
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TASK_ESTIMATE_MS = 60_000  # 1 minute default estimate
_FILE_COUNT_FACTOR_MS = 20_000  # 20s per file when no timing history


# ---------------------------------------------------------------------------
# Title hashing — for matching similar tasks across runs
# ---------------------------------------------------------------------------


def _title_hash(title: str) -> str:
    """Compute a normalized hash of a task title.

    Lowercases, collapses whitespace, and returns the first 8 hex chars
    of a SHA-256 digest.  Two tasks with equivalent titles (modulo case
    and whitespace) will produce the same hash.
    """
    normalized = " ".join(title.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]


# ---------------------------------------------------------------------------
# TaskTiming + TaskTimingStore
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskTiming:
    """Timing record for a single task from a previous run."""

    task_id: str
    title_hash: str
    duration_ms: int
    attempts: int
    file_count: int


class TaskTimingStore:
    """Lookup store for historical task execution times.

    Supports three-level fallback when estimating a task's duration:
    1. Exact ``task_id`` match.
    2. ``title_hash`` match (same task title, different ID).
    3. File-count heuristic.
    4. Global default.
    """

    def __init__(self, timings: Dict[str, TaskTiming]) -> None:
        self._by_id = dict(timings)
        self._by_title_hash: Dict[str, TaskTiming] = {}
        for timing in timings.values():
            if timing.title_hash and timing.title_hash not in self._by_title_hash:
                self._by_title_hash[timing.title_hash] = timing

    @classmethod
    def from_baseline(cls, perf_baseline: Dict[str, Any]) -> TaskTimingStore:
        """Build store from ``perf_baseline.json`` content.

        Uses the most recent run's ``task_timings`` list.
        """
        runs = perf_baseline.get("runs", [])
        if not isinstance(runs, list) or not runs:
            return cls({})

        latest = runs[-1]
        if not isinstance(latest, dict):
            return cls({})

        raw_timings = latest.get("task_timings", [])
        if not isinstance(raw_timings, list):
            return cls({})

        timings: Dict[str, TaskTiming] = {}
        for entry in raw_timings:
            if not isinstance(entry, dict):
                continue
            task_id = str(entry.get("task_id", ""))
            if not task_id:
                continue
            timings[task_id] = TaskTiming(
                task_id=task_id,
                title_hash=str(entry.get("title_hash", "")),
                duration_ms=_safe_int(entry.get("duration_ms", 0)),
                attempts=_safe_int(entry.get("attempts", 0)),
                file_count=_safe_int(entry.get("file_count", 0)),
            )
        return cls(timings)

    def estimate_ms(self, task: Dict[str, Any]) -> int:
        """Estimate execution time for *task* in milliseconds.

        Lookup priority:
        1. Exact ``task["id"]`` match → stored ``duration_ms``.
        2. Title-hash match → stored ``duration_ms``.
        3. File-count heuristic: ``len(task["files"]) * 20_000``.
        4. ``DEFAULT_TASK_ESTIMATE_MS`` (60 s).
        """
        # 1. Exact ID match
        tid = str(task.get("id", ""))
        if tid in self._by_id:
            return max(1, self._by_id[tid].duration_ms)

        # 2. Title-hash match
        title = task.get("title", "")
        if title:
            th = _title_hash(title)
            if th in self._by_title_hash:
                return max(1, self._by_title_hash[th].duration_ms)

        # 3. File-count heuristic
        files = task.get("files", [])
        if isinstance(files, list) and files:
            return max(1, len(files) * _FILE_COUNT_FACTOR_MS)

        # 4. Default
        return DEFAULT_TASK_ESTIMATE_MS

    @property
    def task_count(self) -> int:
        return len(self._by_id)


# ---------------------------------------------------------------------------
# Scheduling functions
# ---------------------------------------------------------------------------


def schedule_level_tasks(
    level_tasks: List[Dict[str, Any]],
    timing_store: TaskTimingStore | None = None,
) -> List[Dict[str, Any]]:
    """Sort tasks within a level by estimated duration descending (LPT).

    Longest-Processing-Time-first ensures that the most time-consuming
    tasks start earliest, minimizing overall wall-clock time when tasks
    are executed in parallel with limited concurrency.

    When *timing_store* is ``None``, returns *level_tasks* unchanged
    (backward compatible).
    """
    if timing_store is None or not level_tasks:
        return level_tasks

    return sorted(
        level_tasks,
        key=lambda t: timing_store.estimate_ms(t),
        reverse=True,
    )


def schedule_batch_chunks(
    runnable: List[Tuple[Dict[str, Any], int, List[str]]],
    effective_parallel: int,
    timing_store: TaskTimingStore | None = None,
) -> List[List[Tuple[Dict[str, Any], int, List[str]]]]:
    """Partition *runnable* into chunks with LPT load-balancing.

    Instead of naively slicing into sequential chunks of size
    ``effective_parallel``, this assigns each task to the chunk (machine)
    with the smallest current load, producing a more balanced schedule.

    When *timing_store* is ``None``, falls back to simple sequential
    chunking (identical to the existing behaviour).

    Returns a list of chunks; each chunk contains tasks to run
    concurrently via ``asyncio.gather()``.
    """
    if not runnable:
        return []

    if effective_parallel <= 0:
        effective_parallel = 1

    # Fallback: sequential chunking (no timing data)
    if timing_store is None:
        return [
            runnable[i : i + effective_parallel]
            for i in range(0, len(runnable), effective_parallel)
        ]

    # If all tasks fit in one chunk, no need for load-balancing
    if len(runnable) <= effective_parallel:
        return [list(runnable)]

    # Sort tasks by estimated duration descending (LPT)
    sorted_tasks = sorted(
        runnable,
        key=lambda item: timing_store.estimate_ms(item[0]),
        reverse=True,
    )

    # LPT load-balancing: assign tasks round-robin to `effective_parallel`
    # worker slots, always picking the least-loaded slot.
    #
    # Each slot accumulates tasks that will run sequentially in that slot.
    # We then zip across slots to form chunks of up to `effective_parallel`
    # tasks that run concurrently via asyncio.gather().
    num_slots = min(effective_parallel, len(sorted_tasks))
    slots: List[List[Tuple[Dict[str, Any], int, List[str]]]] = [[] for _ in range(num_slots)]

    # Min-heap of (current_load, slot_index)
    machines: List[Tuple[int, int]] = [(0, i) for i in range(num_slots)]
    heapq.heapify(machines)

    for item in sorted_tasks:
        load, idx = heapq.heappop(machines)
        slots[idx].append(item)
        task_est = timing_store.estimate_ms(item[0])
        heapq.heappush(machines, (load + task_est, idx))

    # Transpose slots into chunks: chunk[i] = [slot_0[i], slot_1[i], ...]
    # This means each chunk has at most `effective_parallel` tasks.
    max_depth = max(len(s) for s in slots) if slots else 0
    result: List[List[Tuple[Dict[str, Any], int, List[str]]]] = []
    for depth in range(max_depth):
        chunk: List[Tuple[Dict[str, Any], int, List[str]]] = []
        for slot in slots:
            if depth < len(slot):
                chunk.append(slot[depth])
        if chunk:
            result.append(chunk)

    return result if result else [list(runnable)]


# ---------------------------------------------------------------------------
# Task timing collection (end-of-run)
# ---------------------------------------------------------------------------


def collect_task_timings(quality_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract per-task timing records from *quality_summary*.

    Each record contains:
    - ``task_id``: The task identifier.
    - ``title_hash``: Normalized title hash for cross-run matching.
    - ``duration_ms``: Last attempt duration (0 if unknown).
    - ``attempts``: Number of attempts.
    - ``file_count``: Number of files in the task.

    These records are stored in ``perf_baseline.json`` for use by
    ``TaskTimingStore`` in subsequent runs.
    """
    tasks = quality_summary.get("tasks", [])
    if not isinstance(tasks, list):
        return []

    result: List[Dict[str, Any]] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("task_id", ""))
        if not task_id:
            continue

        # Extract duration from last attempt_trend entry
        duration_ms = 0
        attempt_trend = task.get("attempt_trend", [])
        if isinstance(attempt_trend, list) and attempt_trend:
            last = attempt_trend[-1]
            if isinstance(last, dict):
                duration_ms = _safe_int(last.get("duration_ms", 0))

        # Extract title — may not always be in quality_summary
        # Use task_id as fallback for hashing
        title = str(task.get("title", task_id))

        # File count from validator_focus or direct files
        file_count = 0
        validator_focus = task.get("validator_focus", [])
        if isinstance(validator_focus, list):
            file_count = len(validator_focus)

        result.append({
            "task_id": task_id,
            "title_hash": _title_hash(title),
            "duration_ms": duration_ms,
            "attempts": _safe_int(task.get("attempts", 0)),
            "file_count": file_count,
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
