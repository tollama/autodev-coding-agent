from __future__ import annotations

import json
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import Any, Dict, List


def _norm_name(name: str) -> str:
    return name.lower().replace("_", "-")


def collect_packages() -> List[Dict[str, Any]]:
    pkgs = []
    for d in metadata.distributions():
        name = d.metadata.get("Name") or d.name
        version = d.version
        license_ = d.metadata.get("License") or ""
        pkgs.append({
            "name": _norm_name(name),
            "version": version,
            "license": license_.strip(),
        })

    uniq = {}
    for p in pkgs:
        uniq.setdefault(p["name"], p)
    return sorted(uniq.values(), key=lambda x: x["name"])


def cyclonedx_json(packages: List[Dict[str, Any]]) -> Dict[str, Any]:
    ts = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    components = []
    for p in packages:
        comp = {
            "type": "library",
            "name": p["name"],
            "version": p["version"],
        }
        if p.get("license"):
            comp["licenses"] = [{"license": {"name": p["license"]}}]
        components.append(comp)

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": ts,
            "tools": [{"vendor": "autodev", "name": "generate_sbom.py", "version": "0.1"}],
        },
        "components": components,
    }


def main() -> int:
    out_dir = Path("sbom")
    out_dir.mkdir(parents=True, exist_ok=True)

    pkgs = collect_packages()
    (out_dir / "cyclonedx.json").write_text(json.dumps(cyclonedx_json(pkgs), indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
