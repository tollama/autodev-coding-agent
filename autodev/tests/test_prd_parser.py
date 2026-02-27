"""Tests for autodev.prd_parser module."""

from __future__ import annotations

from autodev.prd_parser import parse_prd_markdown


# ---------------------------------------------------------------------------
# Full PRD parsing
# ---------------------------------------------------------------------------

SAMPLE_PRD = """
# My Awesome Project

## Goals
- Build a REST API for user management
- Support CRUD operations

## Non-Goals
- No mobile app
- No real-time features

## Features
### User Registration
- Email and password signup
- Email verification flow

### User Profile
- View and update profile
- Avatar upload support

## Acceptance Criteria
- All endpoints return proper HTTP status codes
- Input validation for all fields

## Non-Functional Requirements
- Response time: < 200ms
- Availability: 99.9%

## Performance Targets
- Throughput: 1000 req/s
- P99 latency: < 500ms

## Expected Load
- Concurrent users: 10000
- Daily requests: 1M

## Latency Sensitive Paths
- POST /api/auth/login
- GET /api/users/me

## Cost Priority
- Optimize for cost
"""


def test_parse_extracts_title():
    """Should extract H1 title."""
    result = parse_prd_markdown(SAMPLE_PRD)
    assert result.title == "My Awesome Project"


def test_parse_extracts_goals():
    """Should extract goals as list."""
    result = parse_prd_markdown(SAMPLE_PRD)
    assert len(result.goals) == 2
    assert "Build a REST API for user management" in result.goals


def test_parse_extracts_non_goals():
    """Should extract non-goals."""
    result = parse_prd_markdown(SAMPLE_PRD)
    assert len(result.non_goals) == 2
    assert "No mobile app" in result.non_goals


def test_parse_extracts_features():
    """Should extract features with subheadings."""
    result = parse_prd_markdown(SAMPLE_PRD)
    assert len(result.features) == 2
    names = [f["name"] for f in result.features]
    assert "User Registration" in names
    assert "User Profile" in names
    reg = [f for f in result.features if f["name"] == "User Registration"][0]
    assert "Email and password signup" in reg["bullets"]


def test_parse_extracts_acceptance_criteria():
    """Should extract acceptance criteria bullets."""
    result = parse_prd_markdown(SAMPLE_PRD)
    assert len(result.acceptance_criteria) == 2


def test_parse_extracts_nfr():
    """Should extract NFR as key-value dict."""
    result = parse_prd_markdown(SAMPLE_PRD)
    assert "Response time" in result.nfr or "- Response time" in result.nfr


def test_parse_extracts_performance_targets():
    """Should extract performance targets."""
    result = parse_prd_markdown(SAMPLE_PRD)
    assert len(result.performance_targets) >= 1


def test_parse_extracts_cost_priority():
    """Should extract cost priority."""
    result = parse_prd_markdown(SAMPLE_PRD)
    assert "cost" in result.cost_priority.lower()


def test_parse_extracts_latency_sensitive_paths():
    """Should extract latency sensitive paths."""
    result = parse_prd_markdown(SAMPLE_PRD)
    assert len(result.latency_sensitive_paths) == 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_parse_empty_input():
    """Empty string should produce PRDStruct with defaults."""
    result = parse_prd_markdown("")
    assert result.title == "PRD"
    assert result.goals == []
    assert result.features == []
    assert result.nfr == {}


def test_parse_missing_sections():
    """PRD with only a title should still parse without error."""
    result = parse_prd_markdown("# Simple Project\n\nJust a description.")
    assert result.title == "Simple Project"
    assert result.goals == []
    assert result.non_goals == []


def test_prd_struct_fields():
    """PRDStruct should have all expected fields."""
    result = parse_prd_markdown("")
    assert hasattr(result, "title")
    assert hasattr(result, "goals")
    assert hasattr(result, "non_goals")
    assert hasattr(result, "features")
    assert hasattr(result, "nfr")
    assert hasattr(result, "acceptance_criteria")
    assert hasattr(result, "performance_targets")
    assert hasattr(result, "expected_load")
    assert hasattr(result, "latency_sensitive_paths")
    assert hasattr(result, "cost_priority")
