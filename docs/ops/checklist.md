# Template CI Drift Checklist

Machine-checkable drift check is defined in:
- `docs/ops/template-validation-contract.json`
- `docs/ops/check_template_ci_drift.sh`

Run from repository root:

```bash
bash docs/ops/check_template_ci_drift.sh
```

Optional: target specific workflows:

```bash
bash docs/ops/check_template_ci_drift.sh . "templates/python_fastapi/.github/workflows/ci.yml"
bash docs/ops/check_template_ci_drift.sh . "templates/python_cli/.github/workflows/ci.yml"
```
