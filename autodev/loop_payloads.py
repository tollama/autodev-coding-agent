"""LLM payload building, schema coercion, and performance validation helpers."""

from __future__ import annotations

from typing import Any, Dict, List

from .loop_utils import HANDOFF_REQUIRED_FIELDS


# ---------------------------------------------------------------------------
# Task payload building
# ---------------------------------------------------------------------------


def _build_task_payload(
    plan: Dict[str, Any],
    task: Dict[str, Any],
    performance_context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    constraints: List[str] = []
    acceptance = task.get("acceptance", [])
    if isinstance(acceptance, list) and acceptance:
        constraints.extend([f"acceptance: {item}" for item in acceptance if isinstance(item, str) and item.strip()])

    quality_expectations = task.get("quality_expectations", {})
    if isinstance(quality_expectations, dict) and quality_expectations:
        constraints.append("quality_expectations를 만족해야 함")

    output_format = {
        "type": "CHANGESET_SCHEMA",
        "required_root_fields": ["role", "summary", "changes", "notes", "handoff"],
        "handoff_required_fields": HANDOFF_REQUIRED_FIELDS,
    }

    return {
        "core": {
            "goal": task.get("goal", ""),
            "paths": task.get("files", []),
            "constraints": constraints,
            "output_format": output_format,
        },
        "optional_context": {
            "task": {
                "id": task["id"],
                "title": task["title"],
                "acceptance": acceptance,
                "depends_on": task.get("depends_on", []),
                "quality_expectations": quality_expectations,
                "validator_focus": task.get("validator_focus", []),
            },
            "plan": {
                "project": {
                    "type": plan["project"].get("type"),
                    "name": plan["project"].get("name"),
                    "quality_gate_profile": plan["project"].get("quality_gate_profile"),
                    "default_artifacts": plan["project"].get("default_artifacts", []),
                },
                "performance_hints": performance_context or {},
            },
        },
    }


# ---------------------------------------------------------------------------
# Performance hints and validation
# ---------------------------------------------------------------------------


def _extract_performance_hints(prd_struct: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    hints: Dict[str, Any] = {}

    for key in ("performance_targets", "expected_load", "latency_sensitive_paths", "cost_priority"):
        if key in plan and isinstance(plan[key], (dict, list, str)):
            hints[key] = plan[key]

    fallback = {
        "performance_targets": prd_struct.get("performance_targets"),
        "expected_load": prd_struct.get("expected_load"),
        "latency_sensitive_paths": prd_struct.get("latency_sensitive_paths"),
        "cost_priority": prd_struct.get("cost_priority"),
    }
    for key, value in fallback.items():
        if key not in hints and value not in (None, {}, [], ""):
            hints[key] = value

    return hints


def _is_perf_gate_failure(row: Dict[str, Any]) -> bool:
    if row.get("ok"):
        return False
    name = str(row.get("name", "")).lower()
    error_class = str(row.get("error_classification") or "").lower()
    tokens = ("perf", "performance", "latency", "throughput")
    return any(token in name for token in tokens) or any(token in error_class for token in tokens)


def _perf_failure_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if _is_perf_gate_failure(row)]


def _perf_repair_task_files(plan: Dict[str, Any], hotspots: List[str]) -> List[str]:
    if not hotspots:
        return []

    candidate_files = []
    for t in plan.get("tasks", []):
        for fp in t.get("files", []):
            if any(path in fp for path in hotspots):
                candidate_files.append(fp)

    if candidate_files:
        return list(dict.fromkeys(candidate_files))

    return [fp for task in plan.get("tasks", []) for fp in task.get("files", [])][:12]


def _targeted_perf_validator_set(
    failed_perf_rows: List[Dict[str, Any]],
    available: List[str],
) -> List[str]:
    perf_names = [row["name"] for row in failed_perf_rows if isinstance(row.get("name"), str)]
    if not perf_names:
        return available

    available_set = {name for name in available}
    targeted = [name for name in perf_names if name in available_set]
    if targeted:
        return targeted
    return available


# ---------------------------------------------------------------------------
# Handoff / changeset validation
# ---------------------------------------------------------------------------


def _validate_handoff_fields(changeset: Dict[str, Any]) -> str | None:
    handoff = changeset.get("handoff")
    if not isinstance(handoff, dict):
        return "MISSING_HANDOFF_FIELDS:" + ",".join(HANDOFF_REQUIRED_FIELDS)

    missing = [field for field in HANDOFF_REQUIRED_FIELDS if not str(handoff.get(field, "")).strip()]
    if missing:
        return "MISSING_HANDOFF_FIELDS:" + ",".join(missing)
    return None


# ---------------------------------------------------------------------------
# Schema coercion
# ---------------------------------------------------------------------------


def _coerce_prd_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """Lightly fill missing optional-but-required-in-schema PRD fields.

    This keeps the schema happy for benchmark-style PRDs while preserving
    all model-provided details.
    """
    out = dict(data)
    out.setdefault("non_goals", [])
    out.setdefault("constraints", [])
    out.setdefault("nfr", {})
    out.setdefault("features", [])
    out.setdefault("acceptance_criteria", [])
    out.setdefault("goals", [])
    out.setdefault("title", "AutoDev PRD")

    if not isinstance(out.get("features"), list):
        out["features"] = []
    else:
        normalized_features = []
        for feature in out.get("features", []):
            if not isinstance(feature, dict):
                continue
            name = feature.get("name")
            if not isinstance(name, str) or not name.strip():
                fallback_name = feature.get("title")
                feature["name"] = fallback_name.strip() if isinstance(fallback_name, str) else "Feature"
            description = feature.get("description")
            if not isinstance(description, str) or not description.strip():
                if isinstance(feature.get("goal"), str) and feature["goal"].strip():
                    description = feature["goal"]
                elif isinstance(feature.get("summary"), str) and feature["summary"].strip():
                    description = feature["summary"]
                feature["description"] = description or "No description provided."
            requirements = feature.get("requirements")
            if not isinstance(requirements, list):
                requirements = []
            normalized_requirements: list[str] = []
            for req in requirements:
                if isinstance(req, str) and req.strip():
                    normalized_requirements.append(req)
                elif isinstance(req, dict) and isinstance(req.get("description"), str) and req["description"].strip():
                    normalized_requirements.append(req["description"])
            if not normalized_requirements:
                if isinstance(feature.get("description"), str) and feature["description"].strip():
                    normalized_requirements = [f"{feature['description']}"]
                else:
                    normalized_requirements = ["Implement feature."]
            feature["requirements"] = normalized_requirements
            normalized_features.append(feature)
        out["features"] = normalized_features

    return out


def _coerce_plan_payload(data: Dict[str, Any], template_candidates: List[str] | None = None) -> Dict[str, Any]:
    """Fill/normalize PLAN_SCHEMA required keys when model output is incomplete.

    This is intentionally conservative and keeps execution going for short
    benchmarking runs by inferring stable defaults.
    """
    allowed_top = {
        "project",
        "runtime_dependencies",
        "dev_dependencies",
        "tasks",
        "ci",
        "docker",
        "security",
        "observability",
        "performance_targets",
        "expected_load",
        "latency_sensitive_paths",
        "cost_priority",
    }
    out: Dict[str, Any] = {k: v for k, v in data.items() if k in allowed_top}

    out.setdefault("project", {})
    out.setdefault("tasks", [])
    out.setdefault("ci", {"enabled": True, "provider": "github_actions"})
    out.setdefault("docker", {"enabled": False})
    out.setdefault("security", {"enabled": False, "tools": []})
    out.setdefault("observability", {"enabled": False})

    project = dict(out.get("project", {}))
    template_root_default = (template_candidates or ["python_cli"])[0]
    valid_types = set(template_candidates or []) | {"python_fastapi", "python_cli", "python_library"}
    if project.get("type") not in valid_types:
        project["type"] = template_root_default
    if not isinstance(project.get("name"), str) or not project.get("name"):
        project["name"] = "autodev-bench"
    # python_version is optional for non-Python templates; provide default for Python.
    proj_type = project.get("type", "")
    if proj_type.startswith("python"):
        if not isinstance(project.get("python_version"), str) or not project.get("python_version"):
            project["python_version"] = "3.11"
    out["project"] = project

    ci = dict(out.get("ci", {}))
    ci.setdefault("enabled", True)
    ci.setdefault("provider", "github_actions")
    out["ci"] = ci

    docker = dict(out.get("docker", {}))
    docker.setdefault("enabled", False)
    out["docker"] = docker

    security = dict(out.get("security", {}))
    security.setdefault("enabled", False)
    security.setdefault("tools", [])
    if not isinstance(security.get("tools"), list):
        security["tools"] = []
    out["security"] = security

    observability = dict(out.get("observability", {}))
    observability.setdefault("enabled", False)
    out["observability"] = observability

    if "runtime_dependencies" not in out or not isinstance(out.get("runtime_dependencies"), list):
        out["runtime_dependencies"] = []
    if "dev_dependencies" not in out or not isinstance(out.get("dev_dependencies"), list):
        out["dev_dependencies"] = []

    normalized_tasks: List[Dict[str, Any]] = []
    raw_tasks = out.get("tasks", [])
    if isinstance(raw_tasks, list):
        for idx, raw_task in enumerate(raw_tasks, start=1):
            if not isinstance(raw_task, dict):
                continue

            title = str(raw_task.get("title") or raw_task.get("name") or f"Task {idx}").strip()
            goal = str(raw_task.get("goal") or raw_task.get("description") or "Implement requested behavior.").strip()
            if len(title) < 5:
                title = f"{title} work"

            raw_files = raw_task.get("files", [])
            files: List[str] = []
            if isinstance(raw_files, list):
                for item in raw_files:
                    if isinstance(item, str):
                        files.append(item)
                    elif isinstance(item, dict) and isinstance(item.get("path"), str):
                        files.append(item.get("path"))
            if not files:
                files = ["README.md"]

            raw_acceptance = raw_task.get("acceptance", [])
            acceptance: List[str] = []
            if isinstance(raw_acceptance, list):
                acceptance = [str(x) for x in raw_acceptance if isinstance(x, str) and len(x.strip()) >= 5]
            if not acceptance:
                acceptance = ["Task implemented with automated checks and validation."]

            raw_depends_on = raw_task.get("depends_on", [])
            depends_on: List[str] = []
            if isinstance(raw_depends_on, list):
                depends_on = [str(x) for x in raw_depends_on if isinstance(x, str) and x.strip()]

            quality_expectations = raw_task.get("quality_expectations")
            if not isinstance(quality_expectations, dict):
                quality_expectations = {"requires_tests": False, "requires_error_contract": False}
            quality_expectations.setdefault("requires_tests", True)
            quality_expectations.setdefault("requires_error_contract", False)

            normalized_tasks.append(
                {
                    "id": str(raw_task.get("id") or f"task{len(normalized_tasks)+1}"),
                    "title": title,
                    "goal": goal,
                    "acceptance": acceptance,
                    "files": files,
                    "depends_on": depends_on,
                    "quality_expectations": {
                        "requires_tests": bool(quality_expectations.get("requires_tests")),
                        "requires_error_contract": bool(quality_expectations.get("requires_error_contract")),
                    },
                }
            )
    out["tasks"] = normalized_tasks
    return out
