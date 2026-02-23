# Tollama Forecast Service (v1)

## Goals
- Provide a simple HTTP API to run time-series forecasts against uploaded CSV.
- Support horizon up to 168.
- Return structured errors (JSON) with consistent error codes.
- Include tests, CI, Docker, security scanning, semgrep, and SBOM generation.

## Non-Goals
- Realtime streaming.
- Multi-tenant auth (v1 is public).

## Features
### Forecast Endpoint
- POST /forecast accepts CSV text or file upload.
- Request includes: model_name (string), horizon (int), optional frequency (string).
- Response includes: timestamps + forecast values.

### Model Abstraction
- A pluggable model interface.
- Provide at least one dummy model implementation for v1 to keep it runnable.

## Acceptance Criteria
- /health returns 200 with {"ok": true}.
- /forecast returns 200 with forecast JSON for valid input.
- /forecast returns 400 with structured error JSON for invalid horizon or invalid CSV.
- Unit tests cover success and key error cases.
- OpenAPI contract test validates presence of declared endpoints.
- ruff/mypy/pytest pass locally.
- Docker build succeeds.
- pip-audit, bandit, semgrep run in CI (audit may warn if offline).
- SBOM and license report are generated in CI.

## Non-Functional Requirements
- latency_ms: < 1000 for dummy model on small CSV
- observability: include request_id in logs; structured logging recommended
- reliability: handle invalid inputs gracefully

## Constraints
- Python 3.11+
- Use FastAPI for API
