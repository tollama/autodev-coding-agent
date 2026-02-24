# docs/ops

This folder contains SDLC/운영 governance scripts and checks used by `coding-agent`:

- `check_template_parity_audit.py`
- `check_template_ci_drift.sh`
- `check_template_dependency_locks.sh`
- `run_template_tests.sh`
- `checklist.md`
- `benchmark_generate_cycle.py` (baseline vs optimized generate timing smoke)

Use `make` for standard lanes:

```bash
make fast        # fast local loop: compile + ruff + unit tests
make strict      # release-ready lane: mypy + tests + contract checks + release gates

# explicit targets
make ci-fast
make ci
make benchmark-generate
```
