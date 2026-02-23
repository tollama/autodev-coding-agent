import json
from pathlib import Path
import sys
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.main import app

def test_api_contract_matches_openapi():
    contract_path = Path("contracts/api_contract.json")
    assert contract_path.exists(), "Missing contracts/api_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))

    c = TestClient(app)
    spec = c.get("/openapi.json").json()

    paths = spec.get("paths", {})
    for ep in contract.get("endpoints", []):
        method = ep["method"].lower()
        path = ep["path"]
        assert path in paths, f"Contract path missing in OpenAPI: {path}"
        assert method in paths[path], f"Contract method missing in OpenAPI: {method} {path}"
        # basic response code check
        expected_responses = set(ep.get("responses", []))
        actual_responses = set((paths[path][method].get("responses") or {}).keys())
        missing = expected_responses - actual_responses
        assert not missing, f"Missing responses for {method} {path}: {sorted(missing)}"
