"""Tests for _dynamic_concurrency in autodev.loop."""

from __future__ import annotations

from autodev.loop import _dynamic_concurrency


def test_returns_base_when_no_budget():
    """No budget configured → return base_max unchanged."""
    usage = {"remaining_tokens": None, "max_total_tokens": None}
    assert _dynamic_concurrency(3, usage, 10) == 3


def test_returns_base_when_plenty_budget():
    """More than 50% budget remaining → return base_max."""
    usage = {"remaining_tokens": 80000, "max_total_tokens": 100000}
    assert _dynamic_concurrency(3, usage, 10) == 3


def test_reduces_by_one_below_50_percent():
    """Between 25% and 50% → reduce by 1."""
    usage = {"remaining_tokens": 40000, "max_total_tokens": 100000}
    assert _dynamic_concurrency(3, usage, 10) == 2


def test_reduces_to_one_below_25_percent():
    """Below 25% → reduce to 1."""
    usage = {"remaining_tokens": 20000, "max_total_tokens": 100000}
    assert _dynamic_concurrency(3, usage, 10) == 1


def test_minimum_is_one():
    """base_max of 1 with low budget should stay at 1."""
    usage = {"remaining_tokens": 30000, "max_total_tokens": 100000}
    assert _dynamic_concurrency(1, usage, 5) == 1


def test_handles_zero_max_total():
    """max_total_tokens=0 → return base_max (avoid division by zero)."""
    usage = {"remaining_tokens": 0, "max_total_tokens": 0}
    assert _dynamic_concurrency(3, usage, 5) == 3


def test_handles_empty_usage_dict():
    """Empty usage dict → return base_max."""
    assert _dynamic_concurrency(2, {}, 5) == 2


def test_exactly_50_percent():
    """Exactly 50% → return base_max (threshold is strict <)."""
    usage = {"remaining_tokens": 50000, "max_total_tokens": 100000}
    assert _dynamic_concurrency(3, usage, 10) == 3


def test_exactly_25_percent():
    """Exactly 25% → reduce by 1 (not to 1, since threshold is strict <)."""
    usage = {"remaining_tokens": 25000, "max_total_tokens": 100000}
    assert _dynamic_concurrency(3, usage, 10) == 2
