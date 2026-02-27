"""Tests for autodev.json_utils module."""

from __future__ import annotations

import pytest

from autodev.json_utils import json_dumps, strict_json_loads


# ---------------------------------------------------------------------------
# strict_json_loads tests
# ---------------------------------------------------------------------------


def test_parses_valid_json():
    """Should parse standard JSON."""
    result = strict_json_loads('{"key": "value", "num": 42}')
    assert result == {"key": "value", "num": 42}


def test_extracts_embedded_json():
    """Should extract JSON from surrounding prose."""
    text = 'Here is the result: {"status": "ok"} hope this helps!'
    result = strict_json_loads(text)
    assert result == {"status": "ok"}


def test_raises_on_garbage():
    """Should raise on input with no JSON at all."""
    with pytest.raises(Exception):
        strict_json_loads("this is not json at all")


def test_handles_whitespace():
    """Should handle whitespace-wrapped JSON."""
    result = strict_json_loads('   \n  {"a": 1}  \n  ')
    assert result == {"a": 1}


def test_handles_nested_braces():
    """Should handle JSON with nested objects."""
    text = '{"outer": {"inner": [1, 2, 3]}}'
    result = strict_json_loads(text)
    assert result["outer"]["inner"] == [1, 2, 3]


# ---------------------------------------------------------------------------
# json_dumps tests
# ---------------------------------------------------------------------------


def test_json_dumps_indented():
    """json_dumps should produce indented output."""
    result = json_dumps({"a": 1, "b": [2, 3]})
    assert "  " in result  # indented
    assert '"a": 1' in result


def test_json_dumps_utf8():
    """json_dumps should handle non-ASCII characters."""
    result = json_dumps({"name": "한글테스트"})
    assert "한글테스트" in result  # ensure_ascii=False
