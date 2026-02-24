# Onboarding Runbook

## 1) Who this is for
- New contributors to the AutoDev repo
- New project owners using generated run artifacts

## 2) One-time local setup

```bash
# from repo root
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Verify CLI:

```bash
autodev --help
```

## 3) Configure credentials
AutoDev requires an LLM key for run execution:

```bash
export AUTODEV_LLM_API_KEY="<your-key>"
# optional
# export AUTODEV_LLM_BASE_URL="http://127.0.0.1:1234/v1"
```

Profile behavior notes:
- Profile fields must include `template_candidates` and `validators`.
- `--profile` may be omitted only when exactly one profile is defined.
- Keep execution policy under `quality_profile` (`quality_profile.validator_policy`, `per_task_soft`, `final_soft`);
  top-level `validator_policy` is still accepted only as fallback.

Then confirm config:

```bash
python - <<'PY'
import yaml
print(yaml.safe_load(open('config.yaml').read())['llm'].keys())
PY
```

## 4) Minimal “hello” run

```bash
# run in repo root
autodev --prd examples/PRD.md --out ./generated_runs --profile enterprise
```

- Output is created at `<out>/<prd-stem>_<YYYYMMDD_HHMMSS>/`
- On success you'll get a JSON-like message like `{ok: true, out: ...}`
- On failure, command exits non-zero and writes failure artifacts under the run directory.

## 5) First actions for a generated run

```bash
cd ./generated_runs/<run-folder>
ls -la
cat .autodev/REPORT.md
cat .autodev/run_metadata.json
```

Common follow-up checks:

```bash
# basic repo hygiene
python -m ruff check src tests
python -m mypy src
python -m pytest -q
```

## 6) Runbook cheat sheet for generated FastAPI projects

```bash
cd ./generated_runs/<run-folder>
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl -sS http://127.0.0.1:8000/health
```

## 7) Template CI contract
- Source root: `autodev/`
- Run outputs: `generated_runs/*/.autodev/`
- Template validation contract: `docs/ops/template-validation-contract.json`
- CI validators (required): `ruff`, `mypy`, `pytest`, `pip_audit`, `bandit`, `semgrep`, `python scripts/generate_sbom.py` @ versions in contract
- Drift check command:
  ```bash
  bash docs/ops/check_template_ci_drift.sh
  ```
