"""Task graph operations, file pattern resolution, and context building."""

from __future__ import annotations

import fnmatch
import os
from pathlib import PurePosixPath
from typing import Any, Dict, List, Set

from .loop_utils import _write_json


# ---------------------------------------------------------------------------
# Topological sort
# ---------------------------------------------------------------------------


def _toposort(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_id = {t["id"]: t for t in tasks}
    indeg = {t["id"]: 0 for t in tasks}
    graph: Dict[str, List[str]] = {t["id"]: [] for t in tasks}

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

    if len(out) == len(tasks):
        return out

    state: Dict[str, int] = {}
    stack: List[str] = []
    cycle: List[str] = []

    def dfs(tid: str) -> bool:
        nonlocal cycle
        state[tid] = 1
        stack.append(tid)
        for nxt in graph[tid]:
            if state.get(nxt, 0) == 0:
                if dfs(nxt):
                    return True
            elif state.get(nxt) == 1:
                cycle_start = stack.index(nxt)
                cycle = stack[cycle_start:] + [nxt]
                return True
        stack.pop()
        state[tid] = 2
        return False

    for tid in out:
        state.setdefault(tid, 2)
    for tid in indeg:
        if state.get(tid, 0) == 0:
            if dfs(tid) and cycle:
                break

    if not cycle:
        unresolved = [t["id"] for t in tasks if indeg[t["id"]] > 0]
        cycle = unresolved

    raise ValueError(
        "Dependency cycle detected in task graph. Resolve dependency loop before execution. "
        f"Cycle path: {' -> '.join(cycle)}"
    )


def _toposort_levels(ordered_tasks: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    levels: Dict[int, List[Dict[str, Any]]] = {}
    level_by_id: Dict[str, int] = {}

    for task in ordered_tasks:
        dep_levels = [level_by_id[dep] for dep in task["depends_on"] if dep in level_by_id]
        level = (max(dep_levels) + 1) if dep_levels else 0
        level_by_id[task["id"]] = level
        levels.setdefault(level, []).append(task)

    return [levels[idx] for idx in sorted(levels)]


# ---------------------------------------------------------------------------
# Task file helpers
# ---------------------------------------------------------------------------


def _task_file_set(task: Dict[str, Any]) -> Set[str]:
    files = task.get("files", [])
    if not isinstance(files, list):
        return set()
    return {str(fp).replace("\\", "/") for fp in files if isinstance(fp, str)}


def _partition_level_for_parallel(level_tasks: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    batches: List[List[Dict[str, Any]]] = []
    batch_files: List[Set[str]] = []

    for task in level_tasks:
        files = _task_file_set(task)
        placed = False
        for idx, used_files in enumerate(batch_files):
            if files.isdisjoint(used_files):
                batches[idx].append(task)
                used_files.update(files)
                placed = True
                break
        if not placed:
            batches.append([task])
            batch_files.append(set(files))
    return batches


# ---------------------------------------------------------------------------
# Glob / file pattern resolution
# ---------------------------------------------------------------------------


def _is_glob_pattern(path: str) -> bool:
    return any(ch in path for ch in "*?[")


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
        t["files"] = list(dict.fromkeys(resolved))
    return plan


# ---------------------------------------------------------------------------
# Context building
# ---------------------------------------------------------------------------


def _build_files_context(
    ws: Any,
    files: List[str],
    max_files: int = 12,
    max_chars_per_file: int = 8_000,
) -> Dict[str, str]:
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


def _detect_incremental_mode(code_index: Any) -> bool:
    """Detect if workspace has an existing codebase worth preserving.

    Heuristic: >=3 source files with >=5 total symbols indicates a real project
    (not just a couple of config files or an empty scaffold).
    """
    if not code_index.files:
        return False
    total_symbols = sum(len(m.symbols) for m in code_index.files.values())
    return len(code_index.files) >= 3 and total_symbols >= 5


def _write_change_summary(
    ws: Any,
    pre_files: set[str],
    incremental_mode: bool,
) -> Dict[str, Any]:
    """Compare pre-existing files with current files to produce change summary."""
    current_files = set(ws.list_context_files(max_files=None))
    added = sorted(current_files - pre_files)
    possibly_modified = sorted(current_files & pre_files)
    deleted = sorted(pre_files - current_files)
    summary: Dict[str, Any] = {
        "incremental_mode": incremental_mode,
        "files_added": added,
        "files_added_count": len(added),
        "files_possibly_modified": possibly_modified,
        "files_possibly_modified_count": len(possibly_modified),
        "files_deleted": deleted,
        "files_deleted_count": len(deleted),
    }
    _write_json(ws, ".autodev/change_summary.json", summary)
    return summary
