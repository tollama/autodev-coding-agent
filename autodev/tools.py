"""Tool-Use Agent Layer: ToolRegistry + ToolExecutor for pre-implementation context gathering."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from .exec_kernel import CmdResult, ExecKernel
from .env_manager import EnvManager
from .workspace import Workspace


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ToolResult:
    """Result from a single tool execution."""

    tool_name: str
    ok: bool
    output: str
    error: str = ""
    duration_ms: int = 0
    truncated: bool = False


@dataclass(frozen=True)
class ToolSpec:
    """Specification for a registered tool.

    *kind* determines the execution path:
    - ``"workspace"`` — runs *workspace_fn(ws, args)* purely in-process.
    - ``"command"``   — builds a CLI command via *command_builder(python, args)*
      and delegates to :class:`ExecKernel`.

    *relevance_check* (optional) receives the current task dict and returns
    ``True`` when the tool should be included in :meth:`ToolExecutor.gather_context`.
    """

    name: str
    description: str
    kind: str  # "workspace" | "command"
    workspace_fn: Callable[[Workspace, Dict[str, Any]], str] | None = None
    command_builder: Callable[[str, Dict[str, Any]], List[str]] | None = None
    relevance_check: Callable[[Dict[str, Any]], bool] | None = None


# ---------------------------------------------------------------------------
# Global registry (mirrors _VALIDATOR_REGISTRY pattern)
# ---------------------------------------------------------------------------

_TOOL_REGISTRY: Dict[str, ToolSpec] = {}


def register_tool(
    name: str,
    description: str,
    kind: str,
    *,
    workspace_fn: Callable[[Workspace, Dict[str, Any]], str] | None = None,
    command_builder: Callable[[str, Dict[str, Any]], List[str]] | None = None,
    relevance_check: Callable[[Dict[str, Any]], bool] | None = None,
) -> ToolSpec:
    """Register a tool in the global registry and return its spec."""
    spec = ToolSpec(
        name=name,
        description=description,
        kind=kind,
        workspace_fn=workspace_fn,
        command_builder=command_builder,
        relevance_check=relevance_check,
    )
    _TOOL_REGISTRY[name] = spec
    return spec


def get_tool_definition(name: str) -> ToolSpec | None:
    """Look up a registered tool by name."""
    return _TOOL_REGISTRY.get(name)


def registered_tool_names() -> List[str]:
    """Return a sorted list of all registered tool names."""
    return sorted(_TOOL_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Built-in workspace tools
# ---------------------------------------------------------------------------


def _file_search_fn(ws: Workspace, args: Dict[str, Any]) -> str:
    """Search workspace files for a pattern. Returns file:line matches."""
    pattern = args.get("pattern", "")
    if not pattern:
        return "No search pattern provided."

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return f"Invalid regex pattern: {pattern}"

    matches: List[str] = []
    max_matches = int(args.get("max_matches", 50))

    for rel_path in ws.list_files(max_files=500):
        if not Workspace._context_file_allowed(rel_path):
            continue
        ext = os.path.splitext(rel_path)[1].lower()
        if ext not in {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".yaml", ".yml", ".toml", ".cfg", ".txt", ".md", ".json"}:
            continue
        try:
            content = ws.read_text(rel_path)
        except Exception:
            continue
        for line_no, line in enumerate(content.splitlines(), 1):
            if regex.search(line):
                matches.append(f"{rel_path}:{line_no}: {line.rstrip()[:120]}")
                if len(matches) >= max_matches:
                    return "\n".join(matches) + f"\n... truncated at {max_matches} matches"

    if not matches:
        return f"No matches for pattern: {pattern}"
    return "\n".join(matches)


def _file_search_relevance(task: Dict[str, Any]) -> bool:
    """Run file_search when goal contains search-related keywords or many seed files."""
    goal = task.get("goal", "").lower()
    keywords = {"search", "find", "existing", "locate", "grep", "where", "usage", "reference"}
    if any(kw in goal for kw in keywords):
        return True
    files = task.get("files", [])
    return len(files) >= 3


def _dependency_check_fn(ws: Workspace, args: Dict[str, Any]) -> str:
    """Read requirements.txt and list declared dependencies."""
    lines: List[str] = []
    for req_file in ["requirements.txt", "requirements-dev.txt", "pyproject.toml"]:
        if ws.exists(req_file):
            try:
                content = ws.read_text(req_file)
                lines.append(f"=== {req_file} ===")
                # For requirements files, show all non-comment lines
                for ln in content.splitlines():
                    stripped = ln.strip()
                    if stripped and not stripped.startswith("#"):
                        lines.append(stripped)
            except Exception:
                lines.append(f"=== {req_file} === (read error)")
    if not lines:
        return "No dependency files found (requirements.txt, requirements-dev.txt, pyproject.toml)."
    return "\n".join(lines)


def _dependency_check_relevance(task: Dict[str, Any]) -> bool:
    """Run dependency_check when workspace likely has requirements."""
    # Relevance is checked later against actual workspace existence
    return True


# ---------------------------------------------------------------------------
# Built-in command tools
# ---------------------------------------------------------------------------


def _lint_check_command(python: str, args: Dict[str, Any]) -> List[str]:
    """Build ruff check command for specific paths."""
    paths = args.get("paths", [])
    if not paths:
        paths = ["src"]
    return [python, "-I", "-m", "ruff", "check", *paths, "--select", "E,F,I", "--no-fix"]


def _lint_check_relevance(task: Dict[str, Any]) -> bool:
    """Always relevant when task files exist."""
    return bool(task.get("files"))


def _test_discovery_command(python: str, args: Dict[str, Any]) -> List[str]:
    """Build pytest --collect-only command to discover test names."""
    paths = args.get("paths", ["tests"])
    return [python, "-I", "-m", "pytest", "--collect-only", "-q", *paths]


def _test_discovery_relevance(task: Dict[str, Any]) -> bool:
    """Relevant when task involves test-related files or tests/ directory."""
    files = task.get("files", [])
    goal = task.get("goal", "").lower()
    if any("test" in f for f in files):
        return True
    if "test" in goal:
        return True
    return False


# ---------------------------------------------------------------------------
# Register built-in tools
# ---------------------------------------------------------------------------

register_tool(
    "file_search",
    "Search workspace files for a regex pattern. Returns file:line matches.",
    "workspace",
    workspace_fn=_file_search_fn,
    relevance_check=_file_search_relevance,
)

register_tool(
    "dependency_check",
    "Read and list declared dependencies from requirements files.",
    "workspace",
    workspace_fn=_dependency_check_fn,
    relevance_check=_dependency_check_relevance,
)

register_tool(
    "lint_check",
    "Run ruff linter on task files to detect existing lint issues.",
    "command",
    command_builder=_lint_check_command,
    relevance_check=_lint_check_relevance,
)

register_tool(
    "test_discovery",
    "Discover existing test names via pytest --collect-only.",
    "command",
    command_builder=_test_discovery_command,
    relevance_check=_test_discovery_relevance,
)


# ---------------------------------------------------------------------------
# ToolExecutor
# ---------------------------------------------------------------------------


class ToolExecutor:
    """Execute registered tools safely and gather context for LLM payloads.

    Follows the same pattern as :class:`Validators` — wraps an
    :class:`ExecKernel` for command tools and uses the :class:`Workspace`
    directly for workspace tools.
    """

    def __init__(self, kernel: ExecKernel, env: EnvManager, ws: Workspace) -> None:
        self.kernel = kernel
        self.env = env
        self.ws = ws

    # -- single tool execution ------------------------------------------------

    def execute_one(
        self,
        name: str,
        args: Dict[str, Any] | None = None,
        output_limit: int = 4000,
    ) -> ToolResult:
        """Execute a single tool by name and return a :class:`ToolResult`."""
        args = args or {}
        spec = get_tool_definition(name)
        if spec is None:
            return ToolResult(tool_name=name, ok=False, output="", error=f"Unknown tool: {name}")

        t0 = time.monotonic()
        try:
            if spec.kind == "workspace":
                return self._run_workspace_tool(spec, args, output_limit, t0)
            elif spec.kind == "command":
                return self._run_command_tool(spec, args, output_limit, t0)
            else:
                return ToolResult(
                    tool_name=name, ok=False, output="", error=f"Unknown tool kind: {spec.kind}",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
        except Exception as exc:
            return ToolResult(
                tool_name=name, ok=False, output="", error=str(exc),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

    def _run_workspace_tool(
        self, spec: ToolSpec, args: Dict[str, Any], output_limit: int, t0: float,
    ) -> ToolResult:
        assert spec.workspace_fn is not None
        raw = spec.workspace_fn(self.ws, args)
        truncated = False
        if len(raw) > output_limit:
            raw = raw[:output_limit] + "\n... (truncated)"
            truncated = True
        return ToolResult(
            tool_name=spec.name, ok=True, output=raw, truncated=truncated,
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    def _run_command_tool(
        self, spec: ToolSpec, args: Dict[str, Any], output_limit: int, t0: float,
    ) -> ToolResult:
        assert spec.command_builder is not None
        python = self.env.venv_python()
        cmd = spec.command_builder(python, args)

        if not self.kernel.is_command_available(cmd):
            return ToolResult(
                tool_name=spec.name, ok=False, output="",
                error=f"Command not available: {' '.join(cmd[:3])}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        result: CmdResult = self.kernel.run(cmd)
        raw = (result.stdout + "\n" + result.stderr).strip()
        truncated = False
        if len(raw) > output_limit:
            raw = raw[:output_limit] + "\n... (truncated)"
            truncated = True
        return ToolResult(
            tool_name=spec.name,
            ok=result.returncode == 0,
            output=raw,
            error="" if result.returncode == 0 else f"exit code {result.returncode}",
            truncated=truncated,
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    # -- context gathering -----------------------------------------------------

    def gather_context(
        self,
        task: Dict[str, Any],
        *,
        tools: List[str] | None = None,
        output_limit: int = 4000,
    ) -> List[ToolResult]:
        """Run relevant tools for a task and return their results.

        If *tools* is given, only those tools are considered; otherwise all
        registered tools whose ``relevance_check`` returns ``True`` are run.
        """
        results: List[ToolResult] = []

        if tools is not None:
            names_to_run = tools
        else:
            names_to_run = []
            for name, spec in _TOOL_REGISTRY.items():
                if spec.relevance_check is None or spec.relevance_check(task):
                    names_to_run.append(name)

        for name in names_to_run:
            spec = get_tool_definition(name)
            if spec is None:
                continue

            # Build tool-specific args from task
            args = self._build_tool_args(name, task)
            result = self.execute_one(name, args, output_limit=output_limit)
            results.append(result)

        return results

    def _build_tool_args(self, tool_name: str, task: Dict[str, Any]) -> Dict[str, Any]:
        """Build tool-specific arguments from the task payload."""
        files = task.get("files", [])
        goal = task.get("goal", "")

        if tool_name == "file_search":
            # Extract key terms from goal for searching
            words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", goal)
            # Use the most specific-looking words (skip common ones)
            common = {"implement", "create", "update", "modify", "write", "code", "function",
                      "class", "method", "file", "test", "should", "must", "will", "that",
                      "this", "with", "from", "have", "make", "task", "goal", "need"}
            specific = [w for w in words if w.lower() not in common]
            pattern = "|".join(specific[:5]) if specific else ""
            return {"pattern": pattern, "max_matches": 30}

        elif tool_name == "lint_check":
            # Lint only task-specific files
            py_files = [f for f in files if f.endswith(".py")]
            return {"paths": py_files or ["src"]}

        elif tool_name == "test_discovery":
            test_paths = [f for f in files if "test" in f]
            return {"paths": test_paths or ["tests"]}

        elif tool_name == "dependency_check":
            return {}

        return {}

    # -- serialization ---------------------------------------------------------

    @staticmethod
    def serialize(results: List[ToolResult]) -> Dict[str, Any]:
        """Convert tool results into a dict suitable for LLM payload injection."""
        tools_data: List[Dict[str, Any]] = []
        for r in results:
            entry: Dict[str, Any] = {
                "tool_name": r.tool_name,
                "ok": r.ok,
                "output": r.output,
            }
            if r.error:
                entry["error"] = r.error
            if r.truncated:
                entry["truncated"] = True
            tools_data.append(entry)
        return {
            "tools": tools_data,
            "total_tools": len(tools_data),
            "hint": "Pre-gathered tool results. Use these to understand existing codebase state. Results are informational only.",
        }
