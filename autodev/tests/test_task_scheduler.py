"""Tests for autodev.task_scheduler module."""

from __future__ import annotations

from autodev.task_scheduler import (
    DEFAULT_TASK_ESTIMATE_MS,
    TaskTiming,
    TaskTimingStore,
    _title_hash,
    collect_task_timings,
    schedule_batch_chunks,
    schedule_level_tasks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_baseline(task_timings: list | None = None) -> dict:
    """Build a minimal perf_baseline dict with one run."""
    return {
        "schema_version": 1,
        "runs": [
            {
                "run_id": "prev-run",
                "task_timings": task_timings or [],
            }
        ],
    }


def _make_task(
    task_id: str = "T-001",
    title: str = "Fix authentication bug",
    files: list | None = None,
) -> dict:
    return {"id": task_id, "title": title, "files": files or []}


# ---------------------------------------------------------------------------
# Test 1-2: _title_hash
# ---------------------------------------------------------------------------


def test_title_hash_deterministic():
    """Same title should always produce the same hash."""
    h1 = _title_hash("Fix authentication bug")
    h2 = _title_hash("Fix authentication bug")
    assert h1 == h2
    assert len(h1) == 8  # first 8 hex chars of SHA-256


def test_title_hash_normalizes():
    """Title hash should normalize case and whitespace."""
    h1 = _title_hash("Fix  Authentication  Bug")
    h2 = _title_hash("fix authentication bug")
    h3 = _title_hash("FIX AUTHENTICATION BUG")
    assert h1 == h2 == h3

    # Different titles should differ
    h4 = _title_hash("Add logging support")
    assert h4 != h1


# ---------------------------------------------------------------------------
# Test 3-4: TaskTimingStore construction
# ---------------------------------------------------------------------------


def test_task_timing_store_from_baseline():
    """Build store from a perf_baseline dict with task timings."""
    baseline = _make_baseline(
        task_timings=[
            {
                "task_id": "T-001",
                "title_hash": "abc12345",
                "duration_ms": 5000,
                "attempts": 2,
                "file_count": 3,
            },
            {
                "task_id": "T-002",
                "title_hash": "def67890",
                "duration_ms": 15000,
                "attempts": 1,
                "file_count": 5,
            },
        ]
    )
    store = TaskTimingStore.from_baseline(baseline)
    assert store.task_count == 2


def test_task_timing_store_from_empty():
    """Empty or missing baseline should produce empty store."""
    store1 = TaskTimingStore.from_baseline({})
    assert store1.task_count == 0

    store2 = TaskTimingStore.from_baseline({"runs": []})
    assert store2.task_count == 0

    store3 = TaskTimingStore.from_baseline({"runs": [{}]})
    assert store3.task_count == 0


# ---------------------------------------------------------------------------
# Test 5-8: estimate_ms fallback levels
# ---------------------------------------------------------------------------


def test_estimate_ms_exact_id_match():
    """Level 1: exact task_id match returns stored duration."""
    store = TaskTimingStore(
        {
            "T-001": TaskTiming(
                task_id="T-001",
                title_hash="abc12345",
                duration_ms=7500,
                attempts=1,
                file_count=2,
            )
        }
    )
    task = _make_task(task_id="T-001", title="Something else")
    assert store.estimate_ms(task) == 7500


def test_estimate_ms_title_hash_fallback():
    """Level 2: title_hash match when task_id doesn't match."""
    title = "Fix authentication bug"
    th = _title_hash(title)
    store = TaskTimingStore(
        {
            "T-OLD": TaskTiming(
                task_id="T-OLD",
                title_hash=th,
                duration_ms=9000,
                attempts=1,
                file_count=2,
            )
        }
    )
    # Different ID, same title
    task = _make_task(task_id="T-NEW", title=title)
    assert store.estimate_ms(task) == 9000


def test_estimate_ms_file_count_heuristic():
    """Level 3: file count heuristic when no ID or title match."""
    store = TaskTimingStore({})  # empty store
    task = _make_task(
        task_id="T-UNKNOWN",
        title="Completely new task",
        files=["a.py", "b.py", "c.py"],
    )
    # 3 files * 20_000 = 60_000
    assert store.estimate_ms(task) == 60_000


def test_estimate_ms_default_fallback():
    """Level 4: default when no matches and no files."""
    store = TaskTimingStore({})
    task = _make_task(task_id="T-UNKNOWN", title="New task", files=[])
    assert store.estimate_ms(task) == DEFAULT_TASK_ESTIMATE_MS


# ---------------------------------------------------------------------------
# Test 9-10: schedule_level_tasks
# ---------------------------------------------------------------------------


def test_schedule_level_tasks_lpt():
    """Tasks should be sorted longest-first (LPT)."""
    store = TaskTimingStore(
        {
            "T-A": TaskTiming("T-A", "", 30_000, 1, 1),
            "T-B": TaskTiming("T-B", "", 60_000, 1, 1),
            "T-C": TaskTiming("T-C", "", 20_000, 1, 1),
        }
    )
    tasks = [
        _make_task(task_id="T-A"),
        _make_task(task_id="T-B"),
        _make_task(task_id="T-C"),
    ]
    result = schedule_level_tasks(tasks, store)

    # Order should be: T-B(60s), T-A(30s), T-C(20s)
    assert result[0]["id"] == "T-B"
    assert result[1]["id"] == "T-A"
    assert result[2]["id"] == "T-C"


def test_schedule_level_tasks_no_store():
    """Without timing store, original order preserved."""
    tasks = [
        _make_task(task_id="T-A"),
        _make_task(task_id="T-B"),
        _make_task(task_id="T-C"),
    ]
    result = schedule_level_tasks(tasks, timing_store=None)
    assert [t["id"] for t in result] == ["T-A", "T-B", "T-C"]


# ---------------------------------------------------------------------------
# Test 11-12: schedule_batch_chunks
# ---------------------------------------------------------------------------


def test_schedule_batch_chunks_balanced():
    """LPT load-balancing should produce balanced slot assignment.

    With effective_parallel=2 (two worker slots) and tasks:
    T1(60s), T2(50s), T3(40s), T4(30s)

    LPT assigns: T1→slot0, T2→slot1, T3→slot1, T4→slot0
    slot0=[T1, T4] (load 90s), slot1=[T2, T3] (load 90s)
    Transposed chunks: [T1, T2], [T4, T3]
    """
    store = TaskTimingStore(
        {
            "T1": TaskTiming("T1", "", 60_000, 1, 1),
            "T2": TaskTiming("T2", "", 50_000, 1, 1),
            "T3": TaskTiming("T3", "", 40_000, 1, 1),
            "T4": TaskTiming("T4", "", 30_000, 1, 1),
        }
    )
    runnable = [
        (_make_task(task_id="T1"), 0, []),
        (_make_task(task_id="T2"), 1, []),
        (_make_task(task_id="T3"), 2, []),
        (_make_task(task_id="T4"), 3, []),
    ]

    chunks = schedule_batch_chunks(runnable, effective_parallel=2, timing_store=store)

    # Two slots with 2 tasks each → 2 chunks of 2
    assert len(chunks) == 2
    assert len(chunks[0]) == 2
    assert len(chunks[1]) == 2

    # Collect all task IDs to verify all tasks are present
    all_ids = set()
    for chunk in chunks:
        for item in chunk:
            all_ids.add(item[0]["id"])
    assert all_ids == {"T1", "T2", "T3", "T4"}

    # First chunk runs T1 and T2 concurrently (longest first)
    first_chunk_ids = {item[0]["id"] for item in chunks[0]}
    assert "T1" in first_chunk_ids
    assert "T2" in first_chunk_ids


def test_schedule_batch_chunks_no_store():
    """Without timing store, fall back to sequential chunking."""
    runnable = [
        (_make_task(task_id="T1"), 0, []),
        (_make_task(task_id="T2"), 1, []),
        (_make_task(task_id="T3"), 2, []),
        (_make_task(task_id="T4"), 3, []),
    ]
    chunks = schedule_batch_chunks(runnable, effective_parallel=2, timing_store=None)

    assert len(chunks) == 2
    # Sequential: [T1, T2], [T3, T4]
    assert chunks[0][0][0]["id"] == "T1"
    assert chunks[0][1][0]["id"] == "T2"
    assert chunks[1][0][0]["id"] == "T3"
    assert chunks[1][1][0]["id"] == "T4"


def test_schedule_batch_chunks_single_chunk():
    """When all tasks fit in one chunk, no splitting needed."""
    store = TaskTimingStore(
        {
            "T1": TaskTiming("T1", "", 60_000, 1, 1),
            "T2": TaskTiming("T2", "", 30_000, 1, 1),
        }
    )
    runnable = [
        (_make_task(task_id="T1"), 0, []),
        (_make_task(task_id="T2"), 1, []),
    ]
    chunks = schedule_batch_chunks(runnable, effective_parallel=3, timing_store=store)

    assert len(chunks) == 1
    assert len(chunks[0]) == 2


def test_schedule_batch_chunks_empty():
    """Empty runnable returns empty list."""
    chunks = schedule_batch_chunks([], effective_parallel=2)
    assert chunks == []


# ---------------------------------------------------------------------------
# Test 13: collect_task_timings
# ---------------------------------------------------------------------------


def test_collect_task_timings():
    """Should extract per-task timing data from quality_summary."""
    quality_summary = {
        "tasks": [
            {
                "task_id": "T-001",
                "title": "Fix auth bug",
                "status": "passed",
                "attempts": 2,
                "validator_focus": ["auth.py", "login.py", "session.py"],
                "attempt_trend": [
                    {"attempt": 1, "status": "failed", "duration_ms": 3000},
                    {"attempt": 2, "status": "passed", "duration_ms": 5000},
                ],
            },
            {
                "task_id": "T-002",
                "title": "Add logging",
                "status": "passed",
                "attempts": 1,
                "validator_focus": ["logger.py"],
                "attempt_trend": [
                    {"attempt": 1, "status": "passed", "duration_ms": 2000},
                ],
            },
        ]
    }

    timings = collect_task_timings(quality_summary)

    assert len(timings) == 2

    # T-001: last attempt duration = 5000, 2 attempts, 3 files
    t1 = next(t for t in timings if t["task_id"] == "T-001")
    assert t1["duration_ms"] == 5000
    assert t1["attempts"] == 2
    assert t1["file_count"] == 3
    assert t1["title_hash"] == _title_hash("Fix auth bug")

    # T-002: last attempt duration = 2000, 1 attempt, 1 file
    t2 = next(t for t in timings if t["task_id"] == "T-002")
    assert t2["duration_ms"] == 2000
    assert t2["attempts"] == 1
    assert t2["file_count"] == 1
    assert t2["title_hash"] == _title_hash("Add logging")


def test_collect_task_timings_empty():
    """Empty or missing tasks should return empty list."""
    assert collect_task_timings({}) == []
    assert collect_task_timings({"tasks": []}) == []
    assert collect_task_timings({"tasks": "not a list"}) == []


# ---------------------------------------------------------------------------
# Test: TaskTimingStore.estimate_ms returns at least 1
# ---------------------------------------------------------------------------


def test_estimate_ms_zero_duration_returns_one():
    """Duration of 0 from history should be clamped to 1."""
    store = TaskTimingStore(
        {
            "T-ZERO": TaskTiming("T-ZERO", "", 0, 1, 1),
        }
    )
    task = _make_task(task_id="T-ZERO")
    assert store.estimate_ms(task) == 1
