from __future__ import annotations

import json
import os
from datetime import datetime

from .prd_parser import PRDStruct


def write_report(repo_root: str, prd: PRDStruct, result: dict) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report = {
        "timestamp": timestamp,
        "prd_title": prd.title,
        "goals": prd.goals,
        "non_goals": prd.non_goals,
        "features": prd.features,
        "nfr": prd.nfr,
        "acceptance_criteria": prd.acceptance_criteria,
        "result": result,
    }

    path = os.path.join(repo_root, "AUTODEV_REPORT.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

