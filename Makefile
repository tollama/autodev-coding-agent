SHELL := /bin/bash

.PHONY: compile check check-untyped-defs tests ci release-check check-release check-release-gates check-template check-locks

# Reusable Python interpreter for consistency
PYTHON ?= python3

# Compile project packages to bytecode to catch syntax errors early.
compile:
	$(PYTHON) -m compileall -q autodev

# Lint and type-check the core package.
check:
	$(PYTHON) -m ruff check autodev
	$(PYTHON) -m mypy autodev

# Optional mypy strict lane for untyped definitions; non-blocking by default.
check-untyped-defs:
	$(PYTHON) -m mypy --check-untyped-defs autodev || true

# Run the repository test suite.
tests:
	$(PYTHON) -m pytest -q autodev/tests
	bash docs/ops/run_template_tests.sh

# Full local CI-equivalent pass.
ci: compile check tests check-template check-locks

# Validate template CI workflow and docs parity against shared contract.
check-template:
	bash docs/ops/check_template_parity_audit.sh

# Verify template requirement locks are present and in sync with direct requirements.
check-locks:
	bash docs/ops/check_template_dependency_locks.sh

# Release gates for release readiness.
check-release-gates:
	@test -f CHANGELOG.md || { echo "[FAIL] Missing CHANGELOG.md"; exit 1; }
	@test -z "$$(git status --porcelain)" || { echo "[FAIL] Working tree is dirty; commit or stash changes first."; exit 1; }

release-check: compile check ci check-untyped-defs check-release-gates
check-release: release-check
