from __future__ import annotations
import fnmatch
import os
from pathlib import PurePosixPath
from typing import Any, Dict, List, Tuple
from jsonschema import validate

from .llm_client import LLMClient
from .json_utils import strict_json_loads, json_dumps
from .roles import prompts
from .schemas import PRD_SCHEMA, PLAN_SCHEMA, CHANGESET_SCHEMA
from .workspace import Workspace, Change
from .exec_kernel import ExecKernel
from .env_manager import EnvManager
from .validators import Validators

DEFAULT_TASK_SOFT_VALIDATORS = {"docker_build", "pip_audit", "sbom"}

def _msg(system: str, user: str):
    return [{"role":"system","content":system},{"role":"user","content":user}]

async def _llm_json(client: LLMClient, system: str, user: str, schema: Dict[str, Any], max_repair: int = 2) -> Dict[str, Any]:
    raw = await client.chat(_msg(system, user), temperature=0.2)
    for _ in range(max_repair + 1):
        try:
            data = strict_json_loads(raw)
            validate(instance=data, schema=schema)
            return data
        except Exception as e:
            repair_user = f"""Your previous output did not match the required JSON schema.
Error: {e}

Return ONLY a corrected JSON object that matches the schema.
Do not include markdown fences or additional text.
"""
            raw = await client.chat(_msg(system, repair_user), temperature=0.2)
    data = strict_json_loads(raw)
    validate(instance=data, schema=schema)
    return data

def _toposort(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_id = {t["id"]: t for t in tasks}
    indeg = {t["id"]: 0 for t in tasks}
    graph = {t["id"]: [] for t in tasks}
    for t in tasks:
        for dep in t["depends_on"]:
            if dep in graph:
                graph[dep].append(t["id"])
                indeg[t["id"]] += 1
    q = [tid for tid, d in indeg.items() if d == 0]
    out = []
    while q:
        tid = q.pop(0)
        out.append(by_id[tid])
        for nxt in graph[tid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                q.append(nxt)
    return out if len(out) == len(tasks) else tasks

def _is_glob_pattern(path: str) -> bool:
    return any(ch in path for ch in "*?[]")

def _match_task_file_pattern(pattern: str, repo_files: List[str]) -> List[str]:
    pat = pattern.replace("\\", "/")
    variants = [pat]
    if pat.startswith("**/"):
        variants.append(pat[3:])
    if "/**/" in pat:
        variants.append(pat.replace("/**/", "/"))

    out: List[str] = []
    for rel in repo_files:
        rel_norm = rel.replace("\\", "/")
        rel_path = PurePosixPath(rel_norm)
        for cand in variants:
            if fnmatch.fnmatch(rel_norm, cand) or rel_path.match(cand):
                out.append(rel_norm)
                break
            if "/" not in cand and fnmatch.fnmatch(os.path.basename(rel_norm), cand):
                out.append(rel_norm)
                break
    return sorted(set(out))

def _canonicalize_task_files(plan: Dict[str, Any], repo_files: List[str]) -> Dict[str, Any]:
    for t in plan["tasks"]:
        resolved: List[str] = []
        for fp in t["files"]:
            rel = fp.replace("\\", "/")
            if _is_glob_pattern(rel):
                matches = _match_task_file_pattern(rel, repo_files)
                if not matches:
                    raise ValueError(f"Task '{t['id']}' has unmatched file glob: {fp}")
                resolved.extend(matches)
            else:
                resolved.append(rel)
        deduped = list(dict.fromkeys(resolved))
        t["files"] = deduped
    return plan

def _build_files_context(ws: Workspace, files: List[str], max_files: int = 30, max_chars_per_file: int = 20_000) -> Dict[str, str]:
    files_ctx: Dict[str, str] = {}
    for fp in files[:max_files]:
        if ws.exists(fp):
            try:
                files_ctx[fp] = ws.read_text(fp)[:max_chars_per_file]
            except Exception:
                files_ctx[fp] = "<unreadable>"
        else:
            files_ctx[fp] = "<missing>"
    return files_ctx

def _validations_ok(validation_rows: List[Dict[str, Any]], soft_validators: set[str]) -> bool:
    blocking = [row for row in validation_rows if row["name"] not in soft_validators]
    return all(row["ok"] for row in blocking)

async def run_autodev_enterprise(
    client: LLMClient,
    ws: Workspace,
    prd_markdown: str,
    template_root: str,
    template_candidates: List[str],
    validators_enabled: List[str],
    audit_required: bool,
    max_fix_loops_total: int,
    max_fix_loops_per_task: int,
    max_json_repair: int,
    task_soft_validators: List[str] | None = None,
    final_soft_validators: List[str] | None = None,
    verbose: bool = True,
) -> Tuple[bool, Dict[str, Any], Dict[str, Any], Any]:
    p = prompts()

    # 1) Normalize PRD with LLM (strict schema)
    prd_struct = await _llm_json(
        client,
        p["prd_normalizer"]["system"],
        f"PRD_MARKDOWN:\n{prd_markdown}\n\nTASK:\n{p['prd_normalizer']['task']}",
        PRD_SCHEMA,
        max_repair=max_json_repair,
    )

    # 2) Plan
    plan = await _llm_json(
        client,
        p["planner"]["system"],
        json_dumps({
            "template_candidates": template_candidates,
            "prd_struct": prd_struct,
            "task": p["planner"]["task"],
        }),
        PLAN_SCHEMA,
        max_repair=max_json_repair,
    )

    # 3) Scaffold
    project_type = plan["project"]["type"]
    template_dir = os.path.join(template_root, project_type)
    ws.apply_template(template_dir)

    # Expand task file globs to concrete files once after scaffold.
    # If planner produces non-matching glob patterns, request one repair pass.
    repo_files_for_plan = ws.list_context_files(max_files=None)
    try:
        plan = _canonicalize_task_files(plan, repo_files_for_plan)
    except ValueError as e:
        repair_payload = {
            "task": "Repair ONLY tasks[].files in the PLAN so each glob matches existing repo files.",
            "constraints": [
                f"Keep project.type unchanged: {project_type}",
                "Keep task intent and ordering unless required to fix file targeting.",
                "Use concrete file paths where possible.",
                "If glob patterns are used, each must match at least one file in repo_files.",
            ],
            "error": str(e),
            "repo_files": repo_files_for_plan[:1500],
            "current_plan": plan,
        }
        repaired_plan = await _llm_json(
            client,
            p["planner"]["system"],
            json_dumps(repair_payload),
            PLAN_SCHEMA,
            max_repair=max_json_repair,
        )
        if repaired_plan["project"]["type"] != project_type:
            raise ValueError("Planner repair changed project.type; refusing to continue.")
        plan = _canonicalize_task_files(repaired_plan, repo_files_for_plan)

    # Persist autodev artifacts
    ws.write_text(".autodev/prd_struct.json", json_dumps(prd_struct))
    ws.write_text(".autodev/plan.json", json_dumps(plan))

    # 4) Prepare env
    kernel = ExecKernel(cwd=ws.root, timeout_sec=1800)
    env = EnvManager(kernel)
    env.ensure_venv(system_python="python")
    env.install_requirements()
    validators = Validators(kernel, env)
    task_soft = set(task_soft_validators or DEFAULT_TASK_SOFT_VALIDATORS)
    final_soft = set(final_soft_validators or [])

    tasks = _toposort(plan["tasks"])
    total_fix_loops = 0
    last_validation = None

    for t in tasks:
        if verbose:
            print(f"\n== TASK {t['id']} == {t['title']}")
        # Provide rich file context for patching.
        files_ctx = _build_files_context(ws, t["files"])
        repo_files = ws.list_context_files(max_files=500)
        impl_payload = {
            "plan": plan,
            "task": t,
            "repo_files": repo_files,
            "files_context": files_ctx,
            "guidance": p["implementer"]["task"],
        }
        changeset = await _llm_json(
            client,
            p["implementer"]["system"],
            json_dumps(impl_payload),
            CHANGESET_SCHEMA,
            max_repair=max_json_repair,
        )

        changes: List[Change] = []
        for c in changeset["changes"]:
            changes.append(Change(op=c["op"], path=c["path"], content=c.get("content")))
        ws.apply_changes(changes)

        # Validate: focus set or default fast checks
        focus = t.get("validator_focus") or ["ruff", "mypy", "pytest"]
        run_set = [v for v in focus if v in validators_enabled]
        if not run_set:
            run_set = [v for v in ["ruff", "mypy", "pytest"] if v in validators_enabled] or list(
                validators_enabled
            )
        res = validators.run_all(run_set, audit_required=audit_required)
        last_validation = Validators.serialize(res)
        all_ok = _validations_ok(last_validation, task_soft)

        loops = 0
        while not all_ok:
            loops += 1
            total_fix_loops += 1
            if loops > max_fix_loops_per_task or total_fix_loops > max_fix_loops_total:
                return (False, prd_struct, plan, last_validation)

            files_ctx = _build_files_context(ws, t["files"])
            fixer_payload = {
                "plan": plan,
                "task": t,
                "validation": last_validation,
                "repo_files": ws.list_context_files(max_files=500),
                "files_context": files_ctx,
                "guidance": p["fixer"]["task"],
            }
            fix = await _llm_json(
                client,
                p["fixer"]["system"],
                json_dumps(fixer_payload),
                CHANGESET_SCHEMA,
                max_repair=max_json_repair,
            )
            fix_changes: List[Change] = []
            for c in fix["changes"]:
                fix_changes.append(Change(op=c["op"], path=c["path"], content=c.get("content")))
            ws.apply_changes(fix_changes)

            res = validators.run_all(run_set, audit_required=audit_required)
            last_validation = Validators.serialize(res)
            all_ok = _validations_ok(last_validation, task_soft)

        ws.write_text(f".autodev/task_{t['id']}_last_validation.json", json_dumps(last_validation))

    # Final enterprise validation (all enabled)
    res = validators.run_all(validators_enabled, audit_required=audit_required)
    last_validation = Validators.serialize(res)
    ok = _validations_ok(last_validation, final_soft)
    return (ok, prd_struct, plan, last_validation)
