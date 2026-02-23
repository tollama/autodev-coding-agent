from __future__ import annotations
import json
from typing import Any, Dict

def strict_json_loads(text: str) -> Dict[str, Any]:
    t = text.strip()
    try:
        return json.loads(t)
    except Exception:
        s = t.find("{")
        e = t.rfind("}")
        if s >= 0 and e > s:
            return json.loads(t[s:e+1])
        raise

def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
