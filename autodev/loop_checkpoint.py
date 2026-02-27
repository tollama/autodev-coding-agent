"""Checkpoint and generation cache persistence for run resume capability."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, List

from .json_utils import strict_json_loads, json_dumps
from .loop_utils import (
    CHECKPOINT_FILE,
    PLAN_CACHE_FILE,
    PLAN_CACHE_VERSION,
    _hash_payload,
    _write_json,
)


def _generation_cache_key(
    prd_markdown: str,
    template_candidates: List[str],
    validators_enabled: List[str],
    quality_profile: Dict[str, Any] | None,
) -> str:
    key_payload = {
        "version": PLAN_CACHE_VERSION,
        "prd_sha256": hashlib.sha256((prd_markdown or "").encode("utf-8")).hexdigest(),
        "template_candidates": template_candidates,
        "validators": validators_enabled,
        "quality_profile": quality_profile or {},
    }
    return _hash_payload(key_payload)


def _read_generation_cache(ws: Any) -> Dict[str, Any] | None:
    if not ws.exists(PLAN_CACHE_FILE):
        return None
    try:
        payload = strict_json_loads(ws.read_text(PLAN_CACHE_FILE))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != PLAN_CACHE_VERSION:
        return None
    return payload


def _write_generation_cache(
    ws: Any,
    cache_key: str,
    prd_struct: Dict[str, Any],
    plan: Dict[str, Any],
    architecture: Dict[str, Any] | None = None,
    prd_analysis: Dict[str, Any] | None = None,
) -> None:
    payload: Dict[str, Any] = {
        "version": PLAN_CACHE_VERSION,
        "cache_key": cache_key,
        "prd_struct": prd_struct,
        "plan": plan,
        "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    if architecture is not None:
        payload["architecture"] = architecture
    if prd_analysis is not None:
        payload["prd_analysis"] = prd_analysis
    ws.write_text(PLAN_CACHE_FILE, json_dumps(payload))


def _read_checkpoint(ws: Any) -> Dict[str, Any] | None:
    if not ws.exists(CHECKPOINT_FILE):
        return None
    try:
        payload = strict_json_loads(ws.read_text(CHECKPOINT_FILE))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _write_checkpoint(
    ws: Any,
    completed_task_ids: List[str],
    *,
    status: str,
    run_id: str,
    request_id: str,
    profile: str | None = None,
    failed_task_id: str | None = None,
    failed_task_ids: List[str] | None = None,
    skipped_task_ids: List[str] | None = None,
) -> None:
    payload: Dict[str, Any] = {
        "status": status,
        "completed_task_ids": sorted(set(completed_task_ids)),
        "failed_task_id": failed_task_id,
        "failed_task_ids": sorted(set(failed_task_ids or [])),
        "skipped_task_ids": sorted(set(skipped_task_ids or [])),
        "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "run_id": run_id,
        "request_id": request_id,
        "profile": profile,
    }
    _write_json(ws, CHECKPOINT_FILE, payload)
