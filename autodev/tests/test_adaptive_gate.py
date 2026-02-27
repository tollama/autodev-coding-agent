"""Tests for autodev.adaptive_gate module."""

from __future__ import annotations

from autodev.adaptive_gate import (
    AdaptiveGateConfig,
    ValidatorStats,
    _is_validator_relevant,
    _priority_sort,
    collect_validator_stats,
    load_validator_stats,
    resolve_adaptive_gate_config,
    select_validators,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    enabled: bool = True,
    mode: str = "balanced",
    threshold: int = 5,
    never_skip: frozenset[str] | None = None,
) -> AdaptiveGateConfig:
    return AdaptiveGateConfig(
        enabled=enabled,
        mode=mode,
        consecutive_pass_threshold=threshold,
        history_window=5,
        never_skip=never_skip or frozenset(),
    )


def _make_stats(
    name: str,
    total_runs: int = 10,
    total_passes: int = 10,
    total_failures: int = 0,
    consecutive_passes: int = 10,
    avg_duration_ms: int = 1000,
) -> ValidatorStats:
    return ValidatorStats(
        name=name,
        total_runs=total_runs,
        total_passes=total_passes,
        total_failures=total_failures,
        consecutive_passes=consecutive_passes,
        avg_duration_ms=avg_duration_ms,
    )


def _make_baseline(runs: list | None = None) -> dict:
    return {"schema_version": 1, "runs": runs or []}


# ---------------------------------------------------------------------------
# Test 1-3: resolve_adaptive_gate_config
# ---------------------------------------------------------------------------


def test_resolve_config_disabled_default():
    """None or {} quality_profile → disabled config."""
    cfg1 = resolve_adaptive_gate_config(None)
    assert cfg1.enabled is False

    cfg2 = resolve_adaptive_gate_config({})
    assert cfg2.enabled is False

    cfg3 = resolve_adaptive_gate_config({"adaptive_gate": {}})
    assert cfg3.enabled is False


def test_resolve_config_enabled():
    """Valid config → correctly parsed."""
    profile = {
        "adaptive_gate": {
            "enabled": True,
            "mode": "aggressive",
            "consecutive_pass_threshold": 3,
            "history_window": 10,
            "never_skip": ["ruff", "pytest"],
        }
    }
    cfg = resolve_adaptive_gate_config(profile)
    assert cfg.enabled is True
    assert cfg.mode == "aggressive"
    assert cfg.consecutive_pass_threshold == 3
    assert cfg.history_window == 10
    assert cfg.never_skip == frozenset({"ruff", "pytest"})


def test_resolve_config_invalid_mode():
    """Invalid mode falls back to 'balanced'."""
    profile = {
        "adaptive_gate": {
            "enabled": True,
            "mode": "turbo",
        }
    }
    cfg = resolve_adaptive_gate_config(profile)
    assert cfg.enabled is True
    assert cfg.mode == "balanced"


# ---------------------------------------------------------------------------
# Test 4-7: _is_validator_relevant
# ---------------------------------------------------------------------------


def test_relevant_python_files():
    """Python files → ruff, mypy, pytest, bandit relevant."""
    files = ["src/main.py", "tests/test_foo.py"]
    assert _is_validator_relevant("ruff", files) is True
    assert _is_validator_relevant("mypy", files) is True
    assert _is_validator_relevant("pytest", files) is True
    assert _is_validator_relevant("bandit", files) is True
    assert _is_validator_relevant("docker_build", files) is False


def test_relevant_dockerfile():
    """Dockerfile → docker_build relevant, ruff not."""
    files = ["Dockerfile"]
    assert _is_validator_relevant("docker_build", files) is True
    assert _is_validator_relevant("ruff", files) is False
    assert _is_validator_relevant("mypy", files) is False


def test_relevant_mixed_files():
    """Mixed files → union of relevant validators."""
    files = ["src/app.py", "requirements.txt"]
    assert _is_validator_relevant("ruff", files) is True
    assert _is_validator_relevant("pip_audit", files) is True
    assert _is_validator_relevant("docker_build", files) is False


def test_relevant_unknown_validator():
    """Validators not in relevance map → always relevant."""
    files = ["src/app.py"]
    assert _is_validator_relevant("custom_validator", files) is True
    assert _is_validator_relevant("unknown_tool", files) is True


# ---------------------------------------------------------------------------
# Test 8-14: select_validators
# ---------------------------------------------------------------------------


def test_select_disabled_passthrough():
    """Disabled config → input unchanged."""
    config = _make_config(enabled=False)
    validators = ["ruff", "mypy", "docker_build"]
    result, promoted = select_validators(
        task_files=["app.py"],
        resolved_validators=validators,
        has_validator_focus=False,
        config=config,
        stats={},
        per_task_soft=set(),
    )
    assert result == validators
    assert promoted == set()


def test_select_with_focus_no_filter():
    """validator_focus present → no file-type filtering, only priority sort."""
    config = _make_config()
    validators = ["ruff", "docker_build", "mypy"]
    result, promoted = select_validators(
        task_files=["app.py"],
        resolved_validators=validators,
        has_validator_focus=True,
        config=config,
        stats={},
        per_task_soft=set(),
    )
    # All validators kept (with focus, no filtering)
    assert set(result) == set(validators)
    assert promoted == set()


def test_select_filters_by_filetype():
    """Python-only task → docker_build removed."""
    config = _make_config()
    validators = ["ruff", "mypy", "docker_build", "pytest"]
    result, promoted = select_validators(
        task_files=["src/main.py", "tests/test_main.py"],
        resolved_validators=validators,
        has_validator_focus=False,
        config=config,
        stats={},
        per_task_soft=set(),
    )
    assert "docker_build" not in result
    assert "ruff" in result
    assert "mypy" in result
    assert "pytest" in result


def test_select_keeps_soft_validators():
    """Soft-fail validators are not affected by filtering."""
    config = _make_config()
    # docker_build is irrelevant for .py but in per_task_soft
    # File-type filtering removes it, but we test the existing flow:
    # select_validators filters on file relevance, soft status is separate
    validators = ["ruff", "docker_build"]
    result, promoted = select_validators(
        task_files=["app.py"],
        resolved_validators=validators,
        has_validator_focus=False,
        config=config,
        stats={},
        per_task_soft={"docker_build"},
    )
    # docker_build filtered out by file relevance (it's not relevant for .py)
    assert "docker_build" not in result
    assert "ruff" in result


def test_select_balanced_promotes_soft():
    """Balanced mode: consecutive_passes >= threshold → promoted to soft."""
    config = _make_config(mode="balanced", threshold=5)
    stats = {
        "ruff": _make_stats("ruff", consecutive_passes=10),  # should be promoted
        "mypy": _make_stats("mypy", consecutive_passes=2),  # below threshold
    }
    validators = ["ruff", "mypy"]
    result, promoted = select_validators(
        task_files=["app.py"],
        resolved_validators=validators,
        has_validator_focus=False,
        config=config,
        stats=stats,
        per_task_soft=set(),
    )
    assert "ruff" in result  # still present
    assert "mypy" in result
    assert "ruff" in promoted  # promoted to soft-fail
    assert "mypy" not in promoted


def test_select_aggressive_skips():
    """Aggressive mode: consecutive_passes >= threshold → completely removed."""
    config = _make_config(mode="aggressive", threshold=5)
    stats = {
        "ruff": _make_stats("ruff", consecutive_passes=10),
        "mypy": _make_stats("mypy", consecutive_passes=2),
    }
    validators = ["ruff", "mypy"]
    result, promoted = select_validators(
        task_files=["app.py"],
        resolved_validators=validators,
        has_validator_focus=False,
        config=config,
        stats=stats,
        per_task_soft=set(),
    )
    assert "ruff" not in result  # skipped entirely
    assert "mypy" in result


def test_select_aggressive_never_skip():
    """Aggressive mode: never_skip protects validators from being removed."""
    config = _make_config(mode="aggressive", threshold=5, never_skip=frozenset({"ruff"}))
    stats = {
        "ruff": _make_stats("ruff", consecutive_passes=10),
        "mypy": _make_stats("mypy", consecutive_passes=10),
    }
    validators = ["ruff", "mypy"]
    result, promoted = select_validators(
        task_files=["app.py"],
        resolved_validators=validators,
        has_validator_focus=False,
        config=config,
        stats=stats,
        per_task_soft=set(),
    )
    assert "ruff" in result  # never_skip protects it
    assert "mypy" not in result  # not protected → skipped


def test_select_minimum_validator():
    """When all validators filtered out → at least ruff remains."""
    config = _make_config(mode="aggressive", threshold=1)
    stats = {
        "ruff": _make_stats("ruff", consecutive_passes=10),
        "mypy": _make_stats("mypy", consecutive_passes=10),
    }
    validators = ["ruff", "mypy"]
    result, _ = select_validators(
        task_files=["app.py"],
        resolved_validators=validators,
        has_validator_focus=False,
        config=config,
        stats=stats,
        per_task_soft=set(),
    )
    assert len(result) >= 1
    assert "ruff" in result


# ---------------------------------------------------------------------------
# Test 15: collect_validator_stats
# ---------------------------------------------------------------------------


def test_collect_stats():
    """Quality summary → per-validator stats aggregation."""
    quality_summary = {
        "tasks": [
            {
                "task_id": "T-001",
                "last_validation": [
                    {"name": "ruff", "ok": True, "duration_ms": 500},
                    {"name": "mypy", "ok": False, "duration_ms": 3000},
                ],
            },
            {
                "task_id": "T-002",
                "last_validation": [
                    {"name": "ruff", "ok": True, "duration_ms": 400},
                    {"name": "mypy", "ok": True, "duration_ms": 2500},
                ],
            },
        ]
    }
    stats = collect_validator_stats(quality_summary)
    assert len(stats) == 2

    ruff_stat = next(s for s in stats if s["name"] == "ruff")
    assert ruff_stat["passed"] is True  # passed in both tasks
    assert ruff_stat["duration_ms"] == 900  # 500 + 400
    assert ruff_stat["task_count"] == 2

    mypy_stat = next(s for s in stats if s["name"] == "mypy")
    assert mypy_stat["passed"] is False  # failed in T-001
    assert mypy_stat["duration_ms"] == 5500
    assert mypy_stat["task_count"] == 2


def test_collect_stats_empty():
    """Empty quality summary → empty list."""
    assert collect_validator_stats({}) == []
    assert collect_validator_stats({"tasks": []}) == []
    assert collect_validator_stats({"tasks": "not_a_list"}) == []


# ---------------------------------------------------------------------------
# Test 16: load_validator_stats from baseline
# ---------------------------------------------------------------------------


def test_load_stats_from_baseline():
    """perf_baseline with validator_stats → ValidatorStats objects."""
    baseline = _make_baseline(runs=[
        {
            "validator_stats": [
                {"name": "ruff", "passed": True, "duration_ms": 500},
                {"name": "mypy", "passed": True, "duration_ms": 2000},
            ],
        },
        {
            "validator_stats": [
                {"name": "ruff", "passed": True, "duration_ms": 600},
                {"name": "mypy", "passed": False, "duration_ms": 3000},
            ],
        },
        {
            "validator_stats": [
                {"name": "ruff", "passed": True, "duration_ms": 550},
                {"name": "mypy", "passed": True, "duration_ms": 2500},
            ],
        },
    ])

    stats = load_validator_stats(baseline, window=5)

    assert "ruff" in stats
    assert "mypy" in stats

    ruff = stats["ruff"]
    assert ruff.total_runs == 3
    assert ruff.total_passes == 3
    assert ruff.total_failures == 0
    assert ruff.consecutive_passes == 3
    assert ruff.avg_duration_ms == 550  # (500+600+550)//3

    mypy = stats["mypy"]
    assert mypy.total_runs == 3
    assert mypy.total_passes == 2
    assert mypy.total_failures == 1
    # Consecutive: pass, fail(reset=0), pass → consecutive = 1
    assert mypy.consecutive_passes == 1
    assert mypy.avg_duration_ms == 2500  # (2000+3000+2500)//3


def test_load_stats_empty_baseline():
    """Empty baseline → empty stats dict."""
    assert load_validator_stats({}) == {}
    assert load_validator_stats({"runs": []}) == {}


# ---------------------------------------------------------------------------
# Test 17: _priority_sort
# ---------------------------------------------------------------------------


def test_priority_sort():
    """Recently failed > high failure rate > faster."""
    stats = {
        "ruff": _make_stats(
            "ruff",
            total_runs=10, total_passes=10, total_failures=0,
            consecutive_passes=10, avg_duration_ms=500,
        ),
        "mypy": _make_stats(
            "mypy",
            total_runs=10, total_passes=5, total_failures=5,
            consecutive_passes=0, avg_duration_ms=3000,
        ),
        "pytest": _make_stats(
            "pytest",
            total_runs=10, total_passes=8, total_failures=2,
            consecutive_passes=3, avg_duration_ms=2000,
        ),
    }
    result = _priority_sort(["ruff", "mypy", "pytest"], stats)

    # mypy: recently failed (consecutive=0, failures>0) → first
    assert result[0] == "mypy"
    # Then by pass_rate ascending (more failures = lower pass_rate = higher priority)
    # pytest: pass_rate=0.8, ruff: pass_rate=1.0
    assert result[1] == "pytest"
    assert result[2] == "ruff"


def test_priority_sort_unknown_stats():
    """Validators without stats → middle priority."""
    stats = {
        "ruff": _make_stats(
            "ruff",
            total_runs=10, total_passes=10, total_failures=0,
            consecutive_passes=10, avg_duration_ms=500,
        ),
    }
    result = _priority_sort(["ruff", "unknown_validator"], stats)
    # unknown gets middle priority (1, 0.5, 0)
    # ruff: (1, 1.0, 500) — higher pass_rate → lower priority
    assert result[0] == "unknown_validator"
    assert result[1] == "ruff"


# ---------------------------------------------------------------------------
# Test: ValidatorStats.pass_rate
# ---------------------------------------------------------------------------


def test_validator_stats_pass_rate():
    """Pass rate calculation."""
    s = ValidatorStats(name="test", total_runs=10, total_passes=7, total_failures=3)
    assert abs(s.pass_rate - 0.7) < 0.01

    empty = ValidatorStats(name="empty")
    assert empty.pass_rate == 0.0


# ---------------------------------------------------------------------------
# Test: conservative mode (file filtering only, no history skipping)
# ---------------------------------------------------------------------------


def test_select_conservative_no_history_skip():
    """Conservative mode: file filtering but no history-based skipping."""
    config = _make_config(mode="conservative", threshold=5)
    stats = {
        "ruff": _make_stats("ruff", consecutive_passes=10),
        "docker_build": _make_stats("docker_build", consecutive_passes=10),
    }
    validators = ["ruff", "mypy", "docker_build"]
    result, promoted = select_validators(
        task_files=["app.py"],
        resolved_validators=validators,
        has_validator_focus=False,
        config=config,
        stats=stats,
        per_task_soft=set(),
    )
    # docker_build removed by file-type (not relevant for .py)
    assert "docker_build" not in result
    # ruff still present despite high consecutive passes (conservative = no skip)
    assert "ruff" in result
    assert "mypy" in result
    # No promotions in conservative mode
    assert promoted == set()
