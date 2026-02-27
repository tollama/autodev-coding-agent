from jsonschema import validate  # type: ignore[import-untyped]
from autodev.schemas import CHANGESET_SCHEMA, PLAN_SCHEMA, PRD_SCHEMA, PRD_ANALYSIS_SCHEMA, OPENAPI_SPEC_SCHEMA, ACCEPTANCE_TEST_SCHEMA


def test_plan_schema_rejects_task_without_quality_expectations():
    invalid = {
        "project": {
            "type": "python_fastapi",
            "name": "x",
            "python_version": "3.11",
        },
        "tasks": [
            {
                "id": "task1",
                "title": "Build core API",
                "goal": "Build core API route",
                "acceptance": ["Add tests"],
                "files": ["src/app/main.py"],
                "depends_on": [],
                "validator_focus": ["ruff"],
            }
        ],
        "ci": {"enabled": True, "provider": "github_actions"},
        "docker": {"enabled": True},
        "security": {"enabled": True, "tools": ["pip_audit", "bandit", "semgrep"]},
        "observability": {"enabled": True},
    }

    try:
        validate(instance=invalid, schema=PLAN_SCHEMA)
    except Exception:
        pass
    else:
        assert False, "Expected PLAN_SCHEMA validation error"


def test_plan_schema_rejects_invalid_validator_focus():
    invalid = {
        "project": {
            "type": "python_fastapi",
            "name": "x",
            "python_version": "3.11",
        },
        "tasks": [
            {
                "id": "task1",
                "title": "Build core API",
                "goal": "Build core API route and tests",
                "acceptance": ["Add tests", "Handle typed input"],
                "files": ["src/app/main.py"],
                "depends_on": [],
                "quality_expectations": {
                    "requires_tests": True,
                    "requires_error_contract": True,
                    "touches_contract": True,
                },
                "validator_focus": ["not_a_validator"],
            }
        ],
        "ci": {"enabled": True, "provider": "github_actions"},
        "docker": {"enabled": True},
        "security": {"enabled": True, "tools": ["pip_audit", "bandit", "semgrep"]},
        "observability": {"enabled": True},
    }

    try:
        validate(instance=invalid, schema=PLAN_SCHEMA)
    except Exception:
        pass
    else:
        assert False, "Expected PLAN_SCHEMA validation error"


def test_plan_schema_rejects_quality_rich_acceptance_mismatch():
    invalid = {
        "project": {
            "type": "python_fastapi",
            "name": "x",
            "python_version": "3.11",
            "quality_gate_profile": "strict",
        },
        "tasks": [
            {
                "id": "task1",
                "title": "Build core API",
                "goal": "Build core API route and tests",
                "acceptance": [
                    "Update docs",
                    "Refactor import structure",
                ],
                "files": ["src/app/main.py", "tests/test_api_contract.py"],
                "depends_on": [],
                "quality_expectations": {
                    "requires_tests": True,
                    "requires_error_contract": True,
                    "touches_contract": True,
                },
                "validator_focus": ["ruff", "pytest"],
            }
        ],
        "ci": {"enabled": True, "provider": "github_actions"},
        "docker": {"enabled": True},
        "security": {"enabled": True, "tools": ["pip_audit", "bandit", "semgrep"]},
        "observability": {"enabled": True},
    }

    try:
        validate(instance=invalid, schema=PLAN_SCHEMA)
    except Exception:
        pass
    else:
        assert False, "Expected PLAN_SCHEMA validation error"


def test_plan_schema_accepts_strict_quality_fields():
    valid = {
        "project": {
            "type": "python_fastapi",
            "name": "x",
            "python_version": "3.11",
            "quality_level": "balanced",
            "quality_gate_profile": "strict",
        },
        "tasks": [
            {
                "id": "task1",
                "title": "Build core API",
                "goal": "Build core API route",
                "acceptance": ["Add unit tests for API", "Handle validation and error response paths"],
                "files": ["src/app/main.py", "tests/test_api_contract.py"],
                "depends_on": [],
                "quality_expectations": {
                    "requires_tests": True,
                    "requires_error_contract": True,
                    "touches_contract": True,
                },
                "validator_focus": ["ruff", "pytest"],
            }
        ],
        "ci": {"enabled": True, "provider": "github_actions"},
        "docker": {"enabled": True},
        "security": {"enabled": True, "tools": ["pip_audit", "bandit", "semgrep"]},
        "observability": {"enabled": True},
    }

    validate(instance=valid, schema=PLAN_SCHEMA)


def test_changeset_schema_keeps_quality_links_metadata_required_when_present():
    payload = {
        "role": "fixer",
        "summary": "Fixing lint",
        "changes": [
            {"op": "write", "path": "README.md", "content": "updated"}
        ],
        "notes": ["note-1"],
        "quality_notes": ["validator coverage updated"],
        "validation_links": {
            "acceptance": ["AC-1"],
            "tasks": ["task1"],
            "validators": ["ruff", "mypy"],
        },
        "handoff": {
            "Summary": "Fixed lint issues in README",
            "Changed Files": ["README.md"],
            "Commands": ["ruff check ."],
            "Evidence": ["ruff passes"],
            "Risks": ["none"],
            "Next Input": "ready for review",
        },
    }

    validate(instance=payload, schema=CHANGESET_SCHEMA)


def test_changeset_schema_rejects_unknown_validator_link():
    payload = {
        "role": "fixer",
        "summary": "Fixing lint",
        "changes": [],
        "notes": ["note-1"],
        "validation_links": {
            "acceptance": ["AC-1"],
            "tasks": ["task1"],
            "validators": ["unknown"],
        },
        "handoff": {
            "Summary": "Attempted fix",
            "Changed Files": [],
            "Commands": [],
            "Evidence": [],
            "Risks": [],
            "Next Input": "n/a",
        },
    }

    try:
        validate(instance=payload, schema=CHANGESET_SCHEMA)
    except Exception:
        pass
    else:
        assert False, "Expected CHANGESET_SCHEMA validation error"


def test_prd_schema_accepts_performance_fields_when_present():
    payload = {
        "title": "Perf-aware",
        "goals": ["Build low-latency API"],
        "non_goals": ["No migration"],
        "features": [
            {
                "name": "Forecast",
                "description": "P95 < 150ms",
                "requirements": ["Handle load"],
            }
        ],
        "acceptance_criteria": ["Handle 200 req/s"],
        "nfr": {"availability": "99.9%"},
        "constraints": ["Keep runtime low"],
        "performance_targets": {"p95_latency_ms": 150, "p99_latency_ms": 250},
        "expected_load": {"requests_per_second": 200, "concurrency": 64},
        "latency_sensitive_paths": ["/api/forecast"],
        "cost_priority": "cost_efficiency",
    }

    validate(instance=payload, schema=PRD_SCHEMA)


def test_prd_schema_remains_backward_compatible_without_performance_fields():
    payload = {
        "title": "Legacy PRD",
        "goals": [],
        "non_goals": [],
        "features": [],
        "acceptance_criteria": [],
        "nfr": {},
        "constraints": [],
    }

    validate(instance=payload, schema=PRD_SCHEMA)


def test_prd_analysis_schema_accepts_valid_analysis():
    payload = {
        "ambiguities": [
            {
                "location": "Features > Authentication",
                "description": "Vague requirement: 'fast login' without specific latency target",
                "suggestion": "Define target latency, e.g., 'login completes within 500ms'",
                "severity": "medium",
            }
        ],
        "missing_requirements": [
            {
                "area": "Error Handling",
                "description": "No error handling specification for API endpoints",
                "impact": "significant",
            }
        ],
        "contradictions": [
            {
                "items": ["Goal: minimize latency", "Constraint: use synchronous processing only"],
                "description": "Synchronous processing contradicts low-latency goal for I/O-bound operations",
            }
        ],
        "risks": [
            {
                "description": "No authentication mechanism specified for public API",
                "mitigation": "Add OAuth2 or API key authentication requirement",
                "likelihood": "high",
            }
        ],
        "completeness_score": 62,
        "clarification_questions": [
            "What authentication method should be used?",
            "What is the target response latency?",
        ],
        "summary": "PRD has significant gaps in error handling and security requirements.",
    }

    validate(instance=payload, schema=PRD_ANALYSIS_SCHEMA)


def test_prd_analysis_schema_accepts_clean_analysis():
    payload = {
        "ambiguities": [],
        "missing_requirements": [],
        "contradictions": [],
        "risks": [],
        "completeness_score": 95,
        "clarification_questions": [],
        "summary": "PRD is well-structured with clear requirements and acceptance criteria.",
    }

    validate(instance=payload, schema=PRD_ANALYSIS_SCHEMA)


def test_prd_analysis_schema_rejects_missing_required():
    payload = {
        "ambiguities": [],
        "risks": [],
        "summary": "Incomplete payload",
    }

    try:
        validate(instance=payload, schema=PRD_ANALYSIS_SCHEMA)
    except Exception:
        pass
    else:
        assert False, "Expected PRD_ANALYSIS_SCHEMA validation error"


def test_acceptance_test_schema_accepts_valid_scaffold():
    payload = {
        "test_file": "tests/test_forecast_api.py",
        "test_cases": [
            {
                "name": "test_forecast_returns_200_for_valid_input",
                "description": "Verify forecast endpoint returns 200 with valid JSON body",
                "acceptance_ref": "API returns 200 for valid forecast request",
                "test_type": "integration",
            },
            {
                "name": "test_forecast_returns_400_for_invalid_input",
                "description": "Verify forecast endpoint returns 400 when required fields missing",
                "acceptance_ref": "Return error with 400 status on invalid input",
                "test_type": "error_path",
                "parameters": [
                    {"input": {}, "expected_status": 400},
                    {"input": {"value": "not_a_number"}, "expected_status": 400},
                ],
            },
        ],
        "imports": ["import pytest", "from httpx import AsyncClient"],
        "fixtures": [
            {
                "name": "client",
                "code": "@pytest.fixture\nasync def client():\n    yield AsyncClient()\n",
            }
        ],
        "source_code": "import pytest\n\ndef test_forecast_returns_200_for_valid_input():\n    pytest.skip('awaiting implementation')\n\ndef test_forecast_returns_400_for_invalid_input():\n    pytest.skip('awaiting implementation')\n",
    }

    validate(instance=payload, schema=ACCEPTANCE_TEST_SCHEMA)


def test_acceptance_test_schema_rejects_invalid_test_name():
    payload = {
        "test_file": "tests/test_foo.py",
        "test_cases": [
            {
                "name": "invalid_no_test_prefix",
                "description": "Missing test_ prefix in function name",
                "acceptance_ref": "AC-1",
                "test_type": "unit",
            }
        ],
        "source_code": "import pytest\n\ndef invalid_no_test_prefix():\n    pass\n",
    }

    try:
        validate(instance=payload, schema=ACCEPTANCE_TEST_SCHEMA)
    except Exception:
        pass
    else:
        assert False, "Expected ACCEPTANCE_TEST_SCHEMA validation error for invalid test name"


def test_acceptance_test_schema_rejects_missing_test_cases():
    payload = {
        "test_file": "tests/test_foo.py",
        "source_code": "import pytest\n\ndef test_placeholder():\n    pass\n",
    }

    try:
        validate(instance=payload, schema=ACCEPTANCE_TEST_SCHEMA)
    except Exception:
        pass
    else:
        assert False, "Expected ACCEPTANCE_TEST_SCHEMA validation error for missing test_cases"


def test_openapi_spec_schema_accepts_valid_spec():
    payload = {
        "openapi_version": "3.1.0",
        "info": {"title": "Forecast API", "version": "1.0.0", "description": "Forecast service"},
        "paths": [
            {
                "path": "/api/forecast",
                "method": "post",
                "summary": "Create forecast",
                "operation_id": "post_api_forecast",
                "request_body_schema": {"type": "object", "properties": {"value": {"type": "number"}}},
                "responses": [
                    {"status_code": 200, "description": "Forecast result"},
                    {"status_code": 400, "description": "Invalid input"},
                ],
                "tags": ["forecast"],
            }
        ],
        "components_schemas": [
            {
                "name": "ForecastRequest",
                "schema": {"type": "object", "properties": {"value": {"type": "number"}}},
            }
        ],
        "spec_yaml": "openapi: '3.1.0'\ninfo:\n  title: Forecast API\n  version: '1.0.0'\npaths:\n  /api/forecast:\n    post:\n      summary: Create forecast\n",
    }

    validate(instance=payload, schema=OPENAPI_SPEC_SCHEMA)


def test_openapi_spec_schema_accepts_empty_paths():
    payload = {
        "openapi_version": "3.1.0",
        "info": {"title": "Empty API", "version": "0.1.0"},
        "paths": [],
        "spec_yaml": "openapi: '3.1.0'\ninfo:\n  title: Empty API\n  version: '0.1.0'\npaths: {}\n",
    }

    validate(instance=payload, schema=OPENAPI_SPEC_SCHEMA)


def test_openapi_spec_schema_rejects_missing_spec_yaml():
    payload = {
        "openapi_version": "3.1.0",
        "info": {"title": "Incomplete", "version": "1.0.0"},
        "paths": [],
    }

    try:
        validate(instance=payload, schema=OPENAPI_SPEC_SCHEMA)
    except Exception:
        pass
    else:
        assert False, "Expected OPENAPI_SPEC_SCHEMA validation error for missing spec_yaml"
