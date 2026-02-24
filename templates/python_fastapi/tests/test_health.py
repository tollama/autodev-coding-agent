from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.main import app

def test_health():
    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_health_rejects_unsupported_method():
    c = TestClient(app)
    r = c.post("/health")
    assert r.status_code == 405
