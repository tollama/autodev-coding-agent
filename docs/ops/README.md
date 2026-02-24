# docs/ops

This folder contains SDLC/운영 governance scripts and checks used by `coding-agent`:

- `check_template_parity_audit.py`
- `check_template_ci_drift.sh`
- `check_template_dependency_locks.sh`
- `run_template_tests.sh`
- `checklist.md`

Run `make ci` for the standard quality gate and `make release-check` for release readiness checks.
