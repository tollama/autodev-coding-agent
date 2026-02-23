from __future__ import annotations
import os
from datetime import datetime
from typing import Any, Dict
from .json_utils import json_dumps

def _write(repo_root: str, rel_path: str, content: str) -> None:
    p = os.path.join(repo_root, rel_path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)

def write_report(repo_root: str, prd_struct: Dict[str, Any], plan: Dict[str, Any], final_validation: Any, ok: bool) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md = []
    md.append("# AUTODEV REPORT")
    md.append(f"- timestamp: {ts}")
    md.append(f"- ok: {ok}")
    md.append("")
    md.append("## Project")
    md.append(f"- title: {prd_struct.get('title')}")
    md.append(f"- type: {plan.get('project',{}).get('type')}")
    md.append("")
    md.append("## Final Validation")
    md.append("```json")
    md.append(json_dumps(final_validation))
    md.append("```")
    _write(repo_root, ".autodev/REPORT.md", "\n".join(md))
