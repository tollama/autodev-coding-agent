# Generated FastAPI App (AutoDev)

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
