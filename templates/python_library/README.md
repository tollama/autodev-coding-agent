# Generated Python Library (AutoDev)

## Package

- Source: `src/library`
- Contract: `contracts/library_contract.json`

## Commands

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python -m ruff check src tests
python -m mypy src
semgrep --config .semgrep.yml --error
python scripts/generate_sbom.py
```
