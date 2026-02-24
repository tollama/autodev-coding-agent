from __future__ import annotations
import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from .config import load_config
from .llm_client import LLMClient
from .workspace import Workspace
from .loop import run_autodev_enterprise
from .report import write_report
from .json_utils import json_dumps

def _ensure_str_list(value, default):
    if value is None:
        return list(default)
    if isinstance(value, list):
        return [str(x) for x in value]
    if isinstance(value, tuple):
        return [str(x) for x in value]
    return [str(value)]

def _slugify_prd_stem(prd_path: str) -> str:
    stem = Path(prd_path).stem.strip()
    if not stem:
        return "prd"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")
    return slug or "prd"

def _resolve_output_dir(prd_path: str, out_root: str) -> str:
    prd_slug = _slugify_prd_stem(prd_path)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = Path(out_root).expanduser()
    candidate = root / f"{prd_slug}_{ts}"
    suffix = 1
    while candidate.exists():
        candidate = root / f"{prd_slug}_{ts}_{suffix:02d}"
        suffix += 1
    return str(candidate)

def cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prd", required=True)
    ap.add_argument(
        "--out",
        required=True,
        help="Output root directory. A run folder named '<prd-file-stem>_<timestamp>' is created inside it.",
    )
    ap.add_argument("--profile", default="enterprise")
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()

    try:
        cfg = load_config(args.config)
    except ValueError as e:
        raise SystemExit(str(e)) from e
    prof = cfg["profiles"][args.profile]
    validator_policy = prof.get("validator_policy", {})
    quality_profile = prof.get("quality_profile", {})
    if quality_profile.get("per_task_soft") is not None:
        per_task_soft = _ensure_str_list(
            quality_profile.get("per_task_soft"),
            default=[],
        )
    elif validator_policy.get("per_task", {}).get("soft_fail") is not None:
        per_task_soft = _ensure_str_list(
            validator_policy.get("per_task", {}).get("soft_fail"),
            default=[],
        )
    else:
        per_task_soft = None

    if quality_profile.get("final_soft") is not None:
        final_soft = _ensure_str_list(
            quality_profile.get("final_soft"),
            default=[],
        )
    elif validator_policy.get("final", {}).get("soft_fail") is not None:
        final_soft = _ensure_str_list(
            validator_policy.get("final", {}).get("soft_fail"),
            default=[],
        )
    else:
        final_soft = None

    with open(args.prd, "r", encoding="utf-8") as f:
        prd_md = f.read()

    llm_cfg = cfg["llm"]
    llm_api_key = (llm_cfg.get("api_key") or "").strip()
    if not llm_api_key:
        raise SystemExit(
            "Missing LLM API key. Set llm.api_key in config.yaml (or as ${AUTODEV_LLM_API_KEY}) "
            "or define AUTODEV_LLM_API_KEY in the environment."
        )
    client = LLMClient(
        base_url=llm_cfg["base_url"],
        api_key=llm_api_key,
        model=llm_cfg["model"],
        timeout_sec=int(llm_cfg.get("timeout_sec", 240)),
    )

    run_out = _resolve_output_dir(args.prd, args.out)
    ws = Workspace(run_out)
    template_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "templates"))
    quality_profile = dict(quality_profile)
    if "validator_policy" not in quality_profile:
        quality_profile["validator_policy"] = validator_policy
    run_metadata = {
        "requested_profile": args.profile,
        "quality_profile": quality_profile,
        "template_candidates": prof.get("template_candidates", []),
        "per_task_soft_validators": per_task_soft,
        "final_soft_validators": final_soft,
        "validators_enabled": prof.get("validators", []),
        "resolved_from": quality_profile.get("name", prof.get("quality_gate_profile", "balanced")),
        "quality_payload_files": {
            "task_quality_index": ".autodev/task_quality_index.json",
            "quality_profile": ".autodev/quality_profile.json",
            "quality_summary": ".autodev/quality_run_summary.json",
            "quality_resolution": ".autodev/quality_resolution.json",
            "final_last_validation": ".autodev/task_final_last_validation.json",
        },
    }
    ws.write_text(".autodev/run_metadata.json", json_dumps(run_metadata))

    import asyncio
    ok, prd_struct, plan, last_validation = asyncio.run(
        run_autodev_enterprise(
            client=client,
            ws=ws,
            prd_markdown=prd_md,
            template_root=template_root,
            template_candidates=prof["template_candidates"],
            validators_enabled=prof["validators"],
            audit_required=bool(prof.get("security", {}).get("audit_required", False)),
            max_fix_loops_total=int(cfg["run"].get("max_fix_loops_total", 10)),
            max_fix_loops_per_task=int(cfg["run"].get("max_fix_loops_per_task", 4)),
            max_json_repair=int(cfg["run"].get("max_json_repair", 2)),
            task_soft_validators=per_task_soft,
            final_soft_validators=final_soft,
            quality_profile=quality_profile,
            verbose=bool(cfg["run"].get("verbose", True)),
        )
    )

    quality_profile_path = os.path.join(run_out, ".autodev", "quality_profile.json")
    if os.path.exists(quality_profile_path):
        try:
            with open(quality_profile_path, "r", encoding="utf-8") as fp:
                resolved_quality_profile: dict[str, Any] = json.loads(fp.read())
            run_metadata["quality_profile"] = resolved_quality_profile
        except Exception:
            run_metadata["quality_profile"] = quality_profile
    else:
        run_metadata["quality_profile"] = quality_profile

    ws.write_text(".autodev/run_metadata.json", json_dumps(run_metadata))

    write_report(ws.root, prd_struct, plan, last_validation, ok)
    print({"ok": ok, "out": os.path.abspath(run_out)})
    if not ok:
        raise SystemExit(1)

if __name__ == "__main__":
    cli()
