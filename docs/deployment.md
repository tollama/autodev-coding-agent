# Deployment Runbook (P1)

## 0) Scope
This runbook covers deploying two layers:
1. **AutoDev control plane** (this repo)
2. **Generated project artifact** (FastAPI/CLI/library outputs in `--out` directory)

## 1) Produce a fresh artifact

```bash
autodev --prd examples/PRD.md --out ./generated_runs --profile enterprise
```

Example output dir:

```bash
RUN_DIR=$(find generated_runs -maxdepth 1 -type d -name 'PRD-*' -print | tail -n 1)
```

## 2) Validate before deploy (same commands as CI parity)

```bash
cd "$RUN_DIR"
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -q
python -m ruff check src tests
python -m mypy src
python -m pip_audit -r requirements.txt || true
python -m bandit -q -r src
python -m semgrep --config .semgrep.yml --error
python scripts/generate_sbom.py
```

> `pip_audit`/`sbom` failures may be advisory depending on policy; verify run metadata for `soft_fail` rules.

## 3) FastAPI deployment (container)

```bash
cd "$RUN_DIR"
# local image build
python -m pip install -r requirements.txt
# or containerized path
docker compose up --build -d
# or explicit image

docker build -t autodev-app:test .
docker run --rm -p 8000:8000 --name autodev-app autodev-app:test
```

Smoke test:

```bash
curl -sS http://127.0.0.1:8000/health
```

## 4) Generated CLI/library deployment

For CLI artifacts (templates/python_cli), run with project entry point from generated package:

```bash
# after install
python -m pip install -r requirements.txt
python -m <your_package> --help
```

For library artifacts, publish/build flows are project-dependent:

```bash
python -m pip install build
python -m build
python -m pip install dist/*.whl
```

## 5) Stop/cleanup

```bash
# fastapi container
cd "$RUN_DIR" && docker compose down --remove-orphans

docker images | grep autodev-app
# optional cleanup
# docker rmi autodev-app:test
```

## 6) Minimal deploy checklist
- [ ] Correct PRD and profile selected (`--profile`)
- [ ] `.autodev/REPORT.md` status is `ok: True`
- [ ] Run directory includes `requirements.txt`, `requirements-dev.txt` (if expected)
- [ ] Validation checks pass locally
- [ ] Image/container starts and `GET /health` returns `{"ok": true}` (or expected app start signal)
- [ ] Runtime config/secrets are set for target environment
