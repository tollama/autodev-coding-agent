# Failure Handling Runbook

## 1) Fast triage checklist (first 5 mins)

1. Capture run context
```bash
pwd
ls -la .autodev
cat .autodev/run_metadata.json
cat .autodev/REPORT.md
```

2. Re-run only the smallest failing surface
```bash
python -m ruff check src tests
python -m pytest -q --maxfail=1
```

3. Verify environment
```bash
python --version
python -m pip --version
python -m venv --help >/dev/null 2>&1 && echo ok
```

4. Check resource/timeouts (common in heavy LLM or validator runs)
```bash
ulimit -n
free -h
```

5. Confirm command output paths
```bash
find .autodev -maxdepth 2 -type f | sort
```

## 2) Failure patterns and actions

### A) Run starts but exits with non-zero immediately
- Symptoms: `Missing LLM API key`, `Could not resolve ...`, parser/schema errors
- Actions:
  - `export AUTODEV_LLM_API_KEY=...`
  - Validate PRD exists and is readable
  - Re-run with same command and inspect top lines from `.autodev/REPORT.md`

### B) `pip_audit` or `semgrep` failures
- Often non-blocking in default enterprise profile (soft-fail depending on profile)
- Actions:
  - Check `.autodev/task_<id>_last_validation.json`
  - Run failing tool directly to confirm root error
  - If policy-compliant, mark and continue with documented risk note

### C) `ruff/mypy/pytest` hard failures
- Actions:
  - Open failing task report
  - Fix code/test drift
  - Re-run same failed validator(s) then full `pytest -q`

```bash
python -m pytest -q tests -k failing_name
python -m mypy src
python -m ruff check src tests
```

### D) `docker_build` failure
- Common: missing Dockerfile in template output, bad base image network, disk pressure
- Actions:
  - `docker build --pull -t autodev-app:test .`
  - Check `docker system df` and prune old caches if needed
  - Ensure generated project has required files (`Dockerfile`, `requirements.txt`)

### E) `Dependency cycle detected in task graph`
- Source: bad plan/dependencies generated from PRD ambiguity
- Actions:
  - Inspect `.autodev/plan.json`
  - Fix cyclic `depends_on` or duplicate/contradictory task IDs
  - Re-run with same profile/PRD

### F) `Command not allowed` / allowlist errors
- Happens when agent asks for non-allowlisted command (expected by design)
- Actions:
  - Keep all maintenance commands within allowed binaries: python modules, `docker version/build`, generated scripts
  - Do not bypass allowlist; adjust tooling in code if truly needed and re-run

## 3) Recovery decision matrix

| Failure type | Impact | Immediate step | Re-run scope |
| --- | --- | --- | --- |
| Soft fail (`pip_audit`, `sbom`, `semgrep` advisory) | Low | Capture output + note | Narrow (same task or final validation) |
| Hard lint/test fail | High | Fix and re-run validator + task loop | Isolated task first |
| Plan/schema/config fail | High | Fix source file/schema/config | Full rerun from PRD |
| Runtime deploy fail | Medium | Validate runtime dependencies + health checks | Service-level only |

> In production-like runs, require two independent checks passing (validator + runtime health) before handoff.

## 4) Escalation protocol
1. Escalate to maintainer with: run command, profile, `.autodev/REPORT.md`, last failing validation JSON, and exact stderr.
2. Attach one minimal reproducer command and environment (`python --version`, `pip --version`, Docker version).
3. If repeated after 2 reruns, run in a clean workspace (fresh clone or empty `generated_runs` target) to rule out local state corruption.
