"""Tests for autodev.validator_graph module."""

from __future__ import annotations

from autodev.validator_graph import (
    ValidatorGraphConfig,
    make_skipped_result,
    resolve_execution_order,
    resolve_validator_graph_config,
    should_skip,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    enabled: bool = True,
    mode: str = "strict",
    skip_on_soft_fail: bool = False,
    custom_edges: dict | None = None,
) -> ValidatorGraphConfig:
    return ValidatorGraphConfig(
        enabled=enabled,
        mode=mode,
        skip_on_soft_fail=skip_on_soft_fail,
        custom_edges=custom_edges or {},
    )


def _make_stats(name: str, avg_duration_ms: int = 1000) -> dict:
    return {"avg_duration_ms": avg_duration_ms}


def _make_result(
    name: str,
    ok: bool = True,
    status: str = "passed",
    error_classification: str | None = None,
) -> dict:
    return {
        "name": name,
        "ok": ok,
        "status": status,
        "error_classification": error_classification,
    }


# ---------------------------------------------------------------------------
# Test 1-3: resolve_validator_graph_config
# ---------------------------------------------------------------------------


def test_resolve_config_disabled_default():
    """None/{}/missing key → disabled config."""
    assert resolve_validator_graph_config(None).enabled is False
    assert resolve_validator_graph_config({}).enabled is False
    assert resolve_validator_graph_config({"validator_graph": "bad"}).enabled is False
    assert resolve_validator_graph_config(
        {"validator_graph": {"enabled": False}},
    ).enabled is False


def test_resolve_config_enabled():
    """All fields parsed correctly."""
    cfg = resolve_validator_graph_config({
        "validator_graph": {
            "enabled": True,
            "mode": "relaxed",
            "skip_on_soft_fail": True,
            "custom_edges": {"semgrep": ["ruff"]},
        },
    })
    assert cfg.enabled is True
    assert cfg.mode == "relaxed"
    assert cfg.skip_on_soft_fail is True
    assert cfg.custom_edges == {"semgrep": ["ruff"]}


def test_resolve_config_invalid_mode():
    """Invalid mode → 'strict' fallback."""
    cfg = resolve_validator_graph_config({
        "validator_graph": {"enabled": True, "mode": "turbo"},
    })
    assert cfg.mode == "strict"


# ---------------------------------------------------------------------------
# Test 4-8: resolve_execution_order
# ---------------------------------------------------------------------------


def test_execution_order_basic():
    """ruff → mypy → pytest topological order."""
    cfg = _make_config()
    order = resolve_execution_order(
        ["pytest", "mypy", "ruff"], {}, cfg,
    )
    assert order.index("ruff") < order.index("mypy")
    assert order.index("mypy") < order.index("pytest")


def test_execution_order_speed_tiebreak():
    """Independent validators sorted by avg_duration_ms ascending."""
    cfg = _make_config()
    stats = {
        "pip_audit": _make_stats("pip_audit", avg_duration_ms=500),
        "semgrep": _make_stats("semgrep", avg_duration_ms=200),
        "sbom": _make_stats("sbom", avg_duration_ms=800),
    }
    order = resolve_execution_order(
        ["sbom", "pip_audit", "semgrep"], stats, cfg,
    )
    # All independent → sorted by speed: semgrep(200) < pip_audit(500) < sbom(800)
    assert order == ["semgrep", "pip_audit", "sbom"]


def test_execution_order_mixed():
    """Full set: ruff before mypy/bandit, mypy before pytest."""
    cfg = _make_config()
    run_set = ["pytest", "bandit", "mypy", "ruff", "pip_audit", "semgrep"]
    order = resolve_execution_order(run_set, {}, cfg)

    assert order.index("ruff") < order.index("mypy")
    assert order.index("ruff") < order.index("bandit")
    assert order.index("mypy") < order.index("pytest")
    assert len(order) == 6


def test_execution_order_disabled():
    """Disabled config → original order preserved."""
    cfg = _make_config(enabled=False)
    run_set = ["pytest", "mypy", "ruff"]
    order = resolve_execution_order(run_set, {}, cfg)
    assert order == ["pytest", "mypy", "ruff"]


def test_execution_order_subset():
    """Subset without ruff → mypy has no in-set prerequisite."""
    cfg = _make_config()
    stats = {
        "mypy": _make_stats("mypy", avg_duration_ms=300),
        "pytest": _make_stats("pytest", avg_duration_ms=500),
    }
    order = resolve_execution_order(["mypy", "pytest"], stats, cfg)
    # mypy depends on ruff, but ruff is not in set → no edge
    # mypy → pytest edge still exists → mypy before pytest
    assert order.index("mypy") < order.index("pytest")


# ---------------------------------------------------------------------------
# Test 9-15: should_skip
# ---------------------------------------------------------------------------


def test_should_skip_prerequisite_failed():
    """ruff failed → mypy skipped."""
    cfg = _make_config()
    completed = {"ruff": _make_result("ruff", ok=False, status="failed")}
    skip, reason = should_skip("mypy", completed, cfg)
    assert skip is True
    assert "ruff" in reason


def test_should_skip_prerequisite_passed():
    """ruff passed → mypy runs."""
    cfg = _make_config()
    completed = {"ruff": _make_result("ruff", ok=True)}
    skip, reason = should_skip("mypy", completed, cfg)
    assert skip is False
    assert reason == ""


def test_should_skip_no_dependency():
    """pip_audit has no prerequisites → never skipped."""
    cfg = _make_config()
    completed = {"ruff": _make_result("ruff", ok=False, status="failed")}
    skip, _ = should_skip("pip_audit", completed, cfg)
    assert skip is False


def test_should_skip_transitive():
    """ruff failed → mypy skipped → pytest also skipped (ruff is direct prereq)."""
    cfg = _make_config()
    completed = {
        "ruff": _make_result("ruff", ok=False, status="failed"),
        "mypy": _make_result("mypy", ok=False, status="skipped_dependency"),
    }
    skip, reason = should_skip("pytest", completed, cfg)
    assert skip is True
    # pytest depends on [ruff, mypy] — ruff failed
    assert "ruff" in reason


def test_should_skip_soft_fail_modes():
    """skip_on_soft_fail controls whether soft-fail prerequisite triggers skip."""
    completed = {
        "ruff": _make_result("ruff", ok=False, status="soft_fail"),
    }

    # skip_on_soft_fail=False, ruff is soft → do NOT skip
    cfg_no = _make_config(skip_on_soft_fail=False)
    skip, _ = should_skip("mypy", completed, cfg_no, soft_validators={"ruff"})
    assert skip is False

    # skip_on_soft_fail=True, ruff is soft → skip
    cfg_yes = _make_config(skip_on_soft_fail=True)
    skip, _ = should_skip("mypy", completed, cfg_yes, soft_validators={"ruff"})
    assert skip is True


def test_should_skip_relaxed_tool_unavailable():
    """Relaxed mode: tool_unavailable does NOT trigger skip."""
    cfg = _make_config(mode="relaxed")
    completed = {
        "ruff": _make_result(
            "ruff", ok=False, status="failed",
            error_classification="tool_unavailable",
        ),
    }
    skip, _ = should_skip("mypy", completed, cfg)
    assert skip is False


def test_should_skip_disabled():
    """Disabled config → always (False, '')."""
    cfg = _make_config(enabled=False)
    completed = {"ruff": _make_result("ruff", ok=False, status="failed")}
    skip, reason = should_skip("mypy", completed, cfg)
    assert skip is False
    assert reason == ""


# ---------------------------------------------------------------------------
# Test 16-17: make_skipped_result
# ---------------------------------------------------------------------------


def test_make_skipped_result_shape():
    """All expected keys present and correct types."""
    result = make_skipped_result("mypy", "prerequisite 'ruff' failed", "ruff")
    required_keys = {
        "name", "ok", "status", "phase", "cmd", "returncode",
        "duration_ms", "tool_version", "error_classification",
        "stdout", "stderr", "note", "diagnostics",
    }
    assert required_keys.issubset(set(result.keys()))
    assert isinstance(result["diagnostics"], dict)


def test_make_skipped_result_status():
    """status=skipped_dependency, ok=False, duration_ms=0."""
    result = make_skipped_result("pytest", "reason", "ruff")
    assert result["name"] == "pytest"
    assert result["ok"] is False
    assert result["status"] == "skipped_dependency"
    assert result["duration_ms"] == 0
    assert result["error_classification"] == "skipped_dependency"


# ---------------------------------------------------------------------------
# Test 18-19: Custom edges
# ---------------------------------------------------------------------------


def test_custom_edges_merge():
    """Custom edges merged with static edges."""
    cfg = _make_config(custom_edges={"semgrep": ["ruff"]})
    completed = {"ruff": _make_result("ruff", ok=False, status="failed")}
    skip, reason = should_skip("semgrep", completed, cfg)
    assert skip is True
    assert "ruff" in reason


def test_custom_edges_only():
    """Validator with only custom dependencies works."""
    cfg = _make_config(custom_edges={"my_lint": ["ruff"]})
    order = resolve_execution_order(["my_lint", "ruff"], {}, cfg)
    assert order.index("ruff") < order.index("my_lint")


# ---------------------------------------------------------------------------
# Test 20: Single validator
# ---------------------------------------------------------------------------


def test_execution_order_single():
    """Single-element run_set → returned unchanged."""
    cfg = _make_config()
    order = resolve_execution_order(["ruff"], {}, cfg)
    assert order == ["ruff"]
