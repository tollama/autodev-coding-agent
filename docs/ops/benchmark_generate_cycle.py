#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict

import yaml


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUT_ROOT = ROOT_DIR / "generated_runs" / "benchmark-cycles"
DEFAULT_PRD = ROOT_DIR / "docs" / "ops" / "benchmark_smoke_prd.md"


def resolve_env_vars(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        return os.environ.get(name, match.group(0))

    return pattern.sub(repl, value)


def has_unresolved_tokens(value: str) -> bool:
    return "${" in value and "}" in value


def run_mode(
    mode: str,
    cfg: Dict[str, Any],
    prd: Path,
    profile: str,
    out_root: Path,
    timeout_sec: int,
    optimized_validators: list[str],
    optimized_run: Dict[str, int],
) -> Dict[str, Any]:
    mode_cfg = copy.deepcopy(cfg)
    if mode == "optimized":
        mode_cfg.setdefault("profiles", {})
        profile_cfg = mode_cfg["profiles"].get(profile, {}).copy()
        validators = profile_cfg.get("validators", [])
        if optimized_validators:
            profile_cfg["validators"] = [v for v in optimized_validators if v in validators] or validators
        mode_cfg["profiles"][profile] = profile_cfg

        run_cfg = mode_cfg.get("run", {}).copy()
        run_cfg.update(optimized_run)
        mode_cfg["run"] = run_cfg

    cfg_path = out_root / f"config.{mode}.yaml"
    with cfg_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(mode_cfg, f, sort_keys=False)

    run_root = out_root / mode
    run_root.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "autodev.main",
        "--prd",
        str(prd),
        "--out",
        str(run_root),
        "--config",
        str(cfg_path),
        "--profile",
        profile,
    ]

    env = os.environ.copy()
    t0 = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    output = f"{proc.stdout}\n{proc.stderr}"
    out_match = re.search(r"'out':\s*'([^']+)'", output)
    if not out_match:
        out_match = re.search(r'\"out\"\s*:\s*\"([^\"]+)\"', output)
    out_dir = out_match.group(1) if out_match else ""

    return {
        "mode": mode,
        "elapsed_ms": elapsed_ms,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "out_dir": out_dir,
        "log": output[:4000],
    }


def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if not isinstance(cfg, dict):
        raise ValueError(f"Invalid config file: expected dict at {path}")

    return cfg


def validate_provider_ready(cfg: Dict[str, Any]) -> None:
    llm = cfg.get("llm", {})
    if not isinstance(llm, dict):
        raise ValueError("config.llm must be an object")

    api_key = resolve_env_vars(llm.get("api_key", ""))
    base_url = resolve_env_vars(str(llm.get("base_url", "")))
    model = resolve_env_vars(str(llm.get("model", "")))

    if not base_url or not model:
        raise ValueError("Missing llm.base_url or llm.model in config")

    if has_unresolved_tokens(api_key):
        raise RuntimeError(
            "LLM API key appears unresolved (e.g., ${AUTODEV_LLM_API_KEY} not set).\n"
            "Set AUTODEV_LLM_API_KEY and retry; benchmark script is intentionally default-safe."
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="Benchmark baseline vs optimized generate cycles.")
    ap.add_argument("--config", default=str(ROOT_DIR / "config.yaml"))
    ap.add_argument("--prd", default=str(DEFAULT_PRD))
    ap.add_argument("--profile", default="enterprise")
    ap.add_argument("--out", default=str(DEFAULT_OUT_ROOT))
    ap.add_argument("--timeout", type=int, default=420)
    ap.add_argument("--optimized-max-fix-loops", type=int, default=2)
    ap.add_argument("--optimized-max-fix-loops-per-task", type=int, default=1)
    ap.add_argument("--optimized-max-json-repair", type=int, default=0)
    ap.add_argument(
        "--optimized-validators",
        default="ruff,pytest",
        help="Comma-separated validator subset for optimized lane (defaults to ruff,pytest).",
    )
    args = ap.parse_args()

    cfg_path = Path(args.config)
    prd_path = Path(args.prd)
    out_root = Path(args.out)

    if not cfg_path.exists():
        raise SystemExit(f"Config not found: {cfg_path}")
    if not prd_path.exists():
        raise SystemExit(f"PRD not found: {prd_path}")

    cfg = load_config(cfg_path)
    validate_provider_ready(cfg)

    if args.profile not in cfg.get("profiles", {}):
        raise SystemExit(f"Profile '{args.profile}' not found in {cfg_path}")

    out_root.mkdir(parents=True, exist_ok=True)

    optimized_validators = [v.strip() for v in args.optimized_validators.split(",") if v.strip()]
    optimized_run = {
        "max_fix_loops_total": args.optimized_max_fix_loops,
        "max_fix_loops_per_task": args.optimized_max_fix_loops_per_task,
        "max_json_repair": args.optimized_max_json_repair,
    }

    # Resolve env vars in-place (mirrors config loading behavior).
    cfg = copy.deepcopy(cfg)
    cfg["llm"] = {k: resolve_env_vars(v) for k, v in cfg.get("llm", {}).items()}
    for section in ("run", "profiles", "security"):
        if isinstance(cfg.get(section), dict):
            for key, value in cfg[section].items():
                if isinstance(value, str):
                    cfg[section][key] = resolve_env_vars(value)

    results = []
    for mode in ("baseline", "optimized"):
        result = run_mode(
            mode=mode,
            cfg=cfg,
            prd=prd_path,
            profile=args.profile,
            out_root=out_root,
            timeout_sec=args.timeout,
            optimized_validators=optimized_validators,
            optimized_run=optimized_run,
        )
        results.append(result)

    width = max(len(r["mode"]) for r in results) + 2
    print("Benchmark summary:")
    for r in results:
        status = "PASS" if r["ok"] else "FAIL"
        print(f"- {r['mode'].ljust(width)} {status} | {r['elapsed_ms']} ms | out: {r['out_dir']}")

    if all(r["ok"] for r in results):
        diff = results[1]["elapsed_ms"] - results[0]["elapsed_ms"]
        print(f"\nRelative delta: optimized - baseline = {diff:+} ms")
        if diff < 0:
            print("Optimization lane improved baseline timing in this run.")
        elif diff == 0:
            print("No timing delta observed.")
        else:
            print("Optimization lane was slower; tune validators/loop caps accordingly.")
        return 0

    print("\nOne or more runs failed. See log excerpts:")
    for r in results:
        if not r["ok"]:
            print(f"[{r['mode']}] exit={r['returncode']}\n{r['log'][:2000]}")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as e:
        print(f"SKIP: {e}")
        raise SystemExit(0)
