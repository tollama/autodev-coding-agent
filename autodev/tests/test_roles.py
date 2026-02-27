"""Tests for autodev.roles module."""

from __future__ import annotations

from autodev.roles import (
    COMMON_RULES,
    INCREMENTAL_FIXER_ADDENDUM,
    INCREMENTAL_IMPLEMENTER_ADDENDUM,
    INCREMENTAL_PLANNER_ADDENDUM,
    RoleSpec,
    _ROLE_REGISTRY,
    get_role,
    prompts,
    register_role,
    registered_role_names,
)


# ---------------------------------------------------------------------------
# prompts() backward compatibility
# ---------------------------------------------------------------------------

EXPECTED_ROLES = {
    "prd_analyst",
    "prd_normalizer",
    "planner",
    "acceptance_test_generator",
    "implementer",
    "fixer",
    "architect",
    "api_spec_generator",
    "reviewer",
    "db_schema_generator",
}


def test_prompts_returns_all_expected_roles():
    """prompts() should include all built-in roles."""
    p = prompts()
    assert EXPECTED_ROLES.issubset(set(p.keys()))


def test_prompts_each_role_has_system_and_task():
    """Each role should have 'system' and 'task' keys."""
    p = prompts()
    for name, spec in p.items():
        assert "system" in spec, f"{name} missing 'system'"
        assert "task" in spec, f"{name} missing 'task'"


def test_prompts_system_nonempty():
    """System prompts should be non-empty strings."""
    p = prompts()
    for name, spec in p.items():
        assert isinstance(spec["system"], str), f"{name} system not str"
        assert len(spec["system"]) > 10, f"{name} system too short"


def test_prompts_task_nonempty():
    """Task prompts should be non-empty strings."""
    p = prompts()
    for name, spec in p.items():
        assert isinstance(spec["task"], str), f"{name} task not str"
        assert len(spec["task"]) > 10, f"{name} task too short"


# ---------------------------------------------------------------------------
# Role registry
# ---------------------------------------------------------------------------


def test_register_role_adds_to_registry():
    """register_role should add a new role."""
    name = "_test_custom_role"
    try:
        spec = register_role(name, system="sys", task="tsk")
        assert isinstance(spec, RoleSpec)
        assert spec.name == name
        assert spec.system == "sys"
        assert spec.task == "tsk"
    finally:
        _ROLE_REGISTRY.pop(name, None)


def test_get_role_returns_registered():
    """get_role should return a previously registered role."""
    name = "_test_get_role"
    try:
        register_role(name, system="s", task="t")
        r = get_role(name)
        assert r is not None
        assert r.name == name
    finally:
        _ROLE_REGISTRY.pop(name, None)


def test_get_role_none_for_unknown():
    """get_role should return None for unknown role."""
    assert get_role("_nonexistent_role_xyz") is None


def test_registered_role_names_sorted():
    """registered_role_names should return sorted list."""
    names = registered_role_names()
    assert names == sorted(names)
    assert len(names) >= len(EXPECTED_ROLES)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_incremental_addendums_nonempty():
    """Incremental addendum constants should be non-empty."""
    assert len(INCREMENTAL_PLANNER_ADDENDUM.strip()) > 20
    assert len(INCREMENTAL_IMPLEMENTER_ADDENDUM.strip()) > 20
    assert len(INCREMENTAL_FIXER_ADDENDUM.strip()) > 20


def test_common_rules_nonempty():
    """COMMON_RULES should contain key instructions."""
    assert "JSON" in COMMON_RULES
    assert "op=" in COMMON_RULES
