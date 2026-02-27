"""Tests for autodev.plugin module."""

from __future__ import annotations

import os

import pytest

from autodev.plugin import (
    PluginSpec,
    discover_plugins,
    load_all_plugins,
    load_plugin,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_plugin(tmp_path, name: str, content: str) -> str:
    """Write a plugin .py file into tmp_path and return its path."""
    path = os.path.join(str(tmp_path), f"{name}.py")
    with open(path, "w") as f:
        f.write(content)
    return path


# ---------------------------------------------------------------------------
# discover_plugins tests
# ---------------------------------------------------------------------------


def test_discover_returns_empty_for_nonexistent_dir():
    """Nonexistent directory should produce empty list."""
    assert discover_plugins("/nonexistent/path/to/plugins") == []


def test_discover_finds_py_files(tmp_path):
    """Should discover .py files as plugins."""
    _write_plugin(tmp_path, "my_plugin", "def register(): pass")
    _write_plugin(tmp_path, "other", "def register(): pass")

    specs = discover_plugins(str(tmp_path))
    names = [s.name for s in specs]
    assert "my_plugin" in names
    assert "other" in names
    assert all(s.enabled for s in specs)


def test_discover_skips_underscore_files(tmp_path):
    """Files starting with _ should be skipped."""
    _write_plugin(tmp_path, "_private", "def register(): pass")
    _write_plugin(tmp_path, "__init__", "")
    _write_plugin(tmp_path, "public", "def register(): pass")

    specs = discover_plugins(str(tmp_path))
    names = [s.name for s in specs]
    assert "_private" not in names
    assert "__init__" not in names
    assert "public" in names


def test_discover_respects_enabled_list(tmp_path):
    """Only plugins in enabled_list should be marked enabled."""
    _write_plugin(tmp_path, "alpha", "def register(): pass")
    _write_plugin(tmp_path, "beta", "def register(): pass")
    _write_plugin(tmp_path, "gamma", "def register(): pass")

    specs = discover_plugins(str(tmp_path), enabled_list=["alpha", "gamma"])
    enabled = {s.name: s.enabled for s in specs}
    assert enabled["alpha"] is True
    assert enabled["beta"] is False
    assert enabled["gamma"] is True


def test_discover_all_enabled_when_no_list(tmp_path):
    """Without enabled_list, all discovered plugins are enabled."""
    _write_plugin(tmp_path, "p1", "def register(): pass")
    specs = discover_plugins(str(tmp_path))
    assert all(s.enabled for s in specs)


def test_discover_skips_non_py_files(tmp_path):
    """Non-.py files should be ignored."""
    with open(os.path.join(str(tmp_path), "readme.txt"), "w") as f:
        f.write("not a plugin")
    _write_plugin(tmp_path, "valid", "def register(): pass")

    specs = discover_plugins(str(tmp_path))
    assert len(specs) == 1
    assert specs[0].name == "valid"


# ---------------------------------------------------------------------------
# load_plugin tests
# ---------------------------------------------------------------------------


def test_load_plugin_calls_register(tmp_path):
    """load_plugin should execute register() from the plugin file."""
    _write_plugin(tmp_path, "tracker", """
import os
def register():
    os.environ["_AUTODEV_PLUGIN_LOADED"] = "yes"
""")

    specs = discover_plugins(str(tmp_path))
    result = load_plugin(specs[0])
    assert result.ok is True
    assert result.error is None
    assert os.environ.get("_AUTODEV_PLUGIN_LOADED") == "yes"
    # Cleanup
    os.environ.pop("_AUTODEV_PLUGIN_LOADED", None)


def test_load_plugin_returns_error_for_missing_register(tmp_path):
    """Plugin without register() should fail."""
    _write_plugin(tmp_path, "no_register", "x = 42")

    specs = discover_plugins(str(tmp_path))
    result = load_plugin(specs[0])
    assert result.ok is False
    assert "No callable register()" in (result.error or "")


def test_load_plugin_returns_error_on_exception(tmp_path):
    """Plugin whose register() raises should fail gracefully."""
    _write_plugin(tmp_path, "broken", """
def register():
    raise RuntimeError("something broke")
""")

    specs = discover_plugins(str(tmp_path))
    result = load_plugin(specs[0])
    assert result.ok is False
    assert "RuntimeError" in (result.error or "")
    assert "something broke" in (result.error or "")


def test_load_plugin_skips_disabled(tmp_path):
    """Disabled plugin should return ok=True with 'disabled' error."""
    _write_plugin(tmp_path, "skip_me", "def register(): pass")

    spec = PluginSpec(name="skip_me", path=os.path.join(str(tmp_path), "skip_me.py"), enabled=False)
    result = load_plugin(spec)
    assert result.ok is True
    assert result.error == "disabled"


# ---------------------------------------------------------------------------
# load_all_plugins tests
# ---------------------------------------------------------------------------


def test_load_all_combines_discover_and_load(tmp_path):
    """load_all_plugins should discover then load."""
    _write_plugin(tmp_path, "good", "def register(): pass")
    _write_plugin(tmp_path, "bad", "x = 1")

    results = load_all_plugins(str(tmp_path))
    assert len(results) == 2
    names = {r.spec.name: r.ok for r in results}
    assert names["good"] is True
    assert names["bad"] is False


# ---------------------------------------------------------------------------
# PluginSpec tests
# ---------------------------------------------------------------------------


def test_plugin_spec_is_frozen():
    """PluginSpec should be immutable."""
    spec = PluginSpec(name="test", path="/fake/path.py")
    with pytest.raises(AttributeError):
        spec.name = "other"  # type: ignore[misc]
