"""Low-level utilities and shared constants used across the loop sub-modules."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, List, Set

from .json_utils import json_dumps

logger = logging.getLogger("autodev")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TASK_SOFT_VALIDATORS = {"docker_build", "pip_audit", "sbom", "semgrep"}
DEFAULT_VALIDATOR_FALLBACK = [
    "ruff",
    "mypy",
    "pytest",
    "pip_audit",
    "bandit",
    "semgrep",
    "sbom",
    "docker_build",
]
QUALITY_SUMMARY_FILE = ".autodev/task_quality_index.json"
QUALITY_TASK_FILE_TMPL = ".autodev/task_{task_id}_quality.json"
QUALITY_TASK_LAST_FILE_TMPL = ".autodev/task_{task_id}_last_validation.json"
QUALITY_PROFILE_FILE = ".autodev/quality_profile.json"
QUALITY_SUMMARY_METADATA_FILE = ".autodev/quality_run_summary.json"
QUALITY_RESOLUTION_FILE = ".autodev/quality_resolution.json"
REPAIR_HISTORY_FILE = ".autodev/repair_history.json"
PLAN_CACHE_FILE = ".autodev/generate_cache.json"
CHECKPOINT_FILE = ".autodev/checkpoint.json"
PLAN_CACHE_VERSION = 1
FULL_REPO_VALIDATORS = {
    "mypy",
    "pytest",
    "pip_audit",
    "bandit",
    "semgrep",
    "sbom",
    "docker_build",
    "dependency_lock",
}

HANDOFF_REQUIRED_FIELDS = [
    "Summary",
    "Changed Files",
    "Commands",
    "Evidence",
    "Risks",
    "Next Input",
]
DEFAULT_MAX_PARALLEL_TASKS = 2
RECOMMENDED_MAX_PARALLEL_TASKS = 3
CONSECUTIVE_FAILURE_FAIL_FAST_THRESHOLD = 3
RUN_TRACE_FILE = ".autodev/run_trace.json"
PERF_BASELINE_FILE = ".autodev/perf_baseline.json"

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def _log_event(event: str, run_id: str, request_id: str, profile: str | None = None, **fields: object) -> None:
    payload = {
        "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "event": event,
        "run_id": run_id,
        "request_id": request_id,
        "run_profile": profile,
        **fields,
    }

    if logger.handlers:
        logger.info(json_dumps(payload))
    else:
        print(json_dumps(payload))


def _safe_short_text(value: str, limit: int = 200) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _shorten_text(value: str, limit: int = 1400) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 5] + " ..."


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(json_dumps(payload).encode("utf-8")).hexdigest()


def _write_json(ws: Any, rel_path: str, payload: Dict[str, Any]) -> None:
    ws.write_text(rel_path, json_dumps(payload))


def _msg(system: str, user: str) -> list:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _ordered_unique(items: List[str]) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
