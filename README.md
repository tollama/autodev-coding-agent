# Enterprise AutoDev Agent

`autodev-agent` turns a single `PRD.md` into a generated repository using an LLM plus a local execution kernel.

## What It Automates

1. Parse PRD markdown into structured requirements.
2. Run role-based generation (`planner -> builder -> validator/fixer`).
3. Apply generated file writes into a workspace.
4. Execute enterprise validators locally:
   - `ruff`
   - `mypy`
   - `pytest`
   - `pip-audit`
   - `bandit`
   - `docker build`
5. Retry with a self-healing fixer loop based on validator logs.
6. Emit `AUTODEV_REPORT.json` in the generated repo.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python -m autodev.main --prd examples/PRD.md --out ./generated_repo --profile enterprise
```

## LLM Backends

The client is OpenAI-compatible, so both LM Studio and OpenAI API gateways are supported via `config.yaml`.

## Notes

- Validators run via command allowlist only (`autodev/exec_kernel.py`).
- Generated project template lives under `templates/python_fastapi`.
- The orchestrator writes full file contents (no patch/diff format expected from the model).

