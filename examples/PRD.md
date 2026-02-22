# Team Task API

## Goals
- Provide a REST API for creating and listing team tasks.
- Ensure basic input validation and deterministic error responses.
- Ship with tests and CI.

## Non-Goals
- Authentication and authorization.
- Multi-tenant data isolation.

## Features
### Create Task
- Endpoint `POST /tasks` creates a task with title and optional description.
- Title is required and max 120 chars.

### List Tasks
- Endpoint `GET /tasks` returns tasks sorted by creation order.

### Health Check
- Endpoint `GET /health` returns `{"ok": true}`.

## Non-Functional Requirements
Performance: P95 API latency under 200ms in local test setup.
Reliability: Unit tests must pass in CI.
Security: Dependency and static security scans must run in CI.

## Acceptance Criteria
- Creating a task with valid input returns 201.
- Creating a task with missing title returns 422.
- Listing tasks returns the created tasks.
- Health endpoint returns HTTP 200 and `ok=true`.

