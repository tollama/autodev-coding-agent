# Generated FastAPI App (AutoDev)

Template CI contract and pinned tool versions live in:
`docs/ops/template-validation-contract.json`.

Run locally:
```bash
pip install -r requirements.txt
PYTHONPATH=src uvicorn app.main:app --reload
```

Test:
```bash
python -m pytest -q
```

Semgrep:
```bash
semgrep --config .semgrep.yml --error
```

SBOM:
```bash
python scripts/generate_sbom.py
ls sbom/
```
