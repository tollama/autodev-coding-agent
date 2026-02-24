# Monitoring & Operations Runbook

## 1) What to monitor during normal runs

### AutoDev run health
```bash
# during/after a run
cd "$RUN_DIR"
ls -la .autodev/
tail -n 200 .autodev/REPORT.md
cat .autodev/task_quality_index.json
cat .autodev/quality_run_summary.json 2>/dev/null || true
cat .autodev/quality_profile.json 2>/dev/null || true
```

Watch for:
- `final_status` in report
- hard vs soft failures
- unresolved blockers in quality summary
- repeated validation failures on same task

### Generated app/runtime signals
For FastAPI apps:
```bash
curl -sS http://127.0.0.1:8000/health | jq

docker compose ps

docker logs -f autodev-app
```

For containerized runs:
```bash
docker stats --no-stream autodev-app
```

## 2) SLA-style baseline checks
Run these every deployment/boot:

```bash
# process + reachability
ps -ef | grep -E "uvicorn|autodev" | grep -v grep
curl -sSf http://127.0.0.1:8000/health >/dev/null && echo "health-ok"
python -m pytest -q --maxfail=1
```

## 3) Artifact-level checks (daily/after-merge)

```bash
cd generated_runs/<run-folder>
python -m ruff check src tests
python -m mypy src
python -m pytest -q tests
python -m pip_audit -r requirements.txt || true
python -m bandit -q -r src
python -m semgrep --config .semgrep.yml --error || true
```

## 4) Common operational dashboards (manual)
Track these per run folder:
- Run duration (from timestamps in `REPORT.md`)
- Retry count (from `.autodev/task_quality_index.json`)
- Validator trend (`task_validation_trend`)
- Deployment freshness (`git log`, image `created` tag, container uptime)

## 5) Common failure triage checklist
- **Health endpoint fails**: check app bind address/port + container exposes 8000
- **Run folder missing artifacts**: confirm run command used `--out` and profile path is writable
- **Validation regressions**: run failing validator directly in failing run env
- **Intermittent container startup**: inspect latest logs and restart count, then rerun with `docker compose up` foreground
- **Post-deploy drift**: compare `requirements.txt` hash and lock artifacts (if any) to source
