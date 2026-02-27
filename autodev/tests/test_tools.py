"""Tests for the Tool-Use Agent Layer: ToolRegistry + ToolExecutor."""

from __future__ import annotations

import pytest

from autodev.exec_kernel import CmdResult, ExecKernel
from autodev.env_manager import EnvManager
from autodev.tools import (
    ToolExecutor,
    ToolResult,
    _TOOL_REGISTRY,
    get_tool_definition,
    register_tool,
    registered_tool_names,
)
from autodev.workspace import Workspace


# ---------------------------------------------------------------------------
# Fakes (same pattern as test_validators.py)
# ---------------------------------------------------------------------------


class _FakeKernel(ExecKernel):
    def __init__(self, command_results=None, available=True):
        super().__init__(cwd=".")
        self.command_results = dict(command_results or {})
        self._available = available

    def run(self, cmd):
        cmd_key = tuple(cmd)
        if cmd_key in self.command_results:
            r = self.command_results[cmd_key]
            if isinstance(r, CmdResult):
                return r
            return CmdResult(cmd=cmd, returncode=r, stdout="", stderr="")
        # Default: return success with "ok"
        return CmdResult(cmd=cmd, returncode=0, stdout="ok", stderr="")

    def is_command_available(self, cmd):
        return bool(self._available)


class _FakeEnvManager(EnvManager):
    def __init__(self, kernel: _FakeKernel):
        self.k = kernel

    def venv_python(self) -> str:
        return "/fake/python"


@pytest.fixture()
def tmp_ws(tmp_path):
    return Workspace(str(tmp_path))


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


def test_register_and_lookup_tool():
    """Register a custom tool, look it up, then clean up."""
    name = "_test_custom_tool"
    spec = register_tool(
        name,
        "A test-only tool",
        "workspace",
        workspace_fn=lambda ws, args: "hello",
    )
    try:
        assert get_tool_definition(name) is spec
        assert spec.name == name
        assert spec.kind == "workspace"
    finally:
        _TOOL_REGISTRY.pop(name, None)


def test_registered_tool_names():
    """Built-in tools should be present in the names list."""
    names = registered_tool_names()
    assert "file_search" in names
    assert "dependency_check" in names
    assert "lint_check" in names
    assert "test_discovery" in names


# ---------------------------------------------------------------------------
# Workspace tool tests
# ---------------------------------------------------------------------------


def test_file_search_finds_pattern(tmp_ws):
    """file_search should find matching lines in workspace files."""
    tmp_ws.write_text("src/main.py", "class UserService:\n    pass\n")
    tmp_ws.write_text("src/utils.py", "def helper():\n    pass\n")

    kernel = _FakeKernel()
    env = _FakeEnvManager(kernel)
    executor = ToolExecutor(kernel, env, tmp_ws)

    result = executor.execute_one("file_search", {"pattern": "UserService"})
    assert result.ok is True
    assert "UserService" in result.output
    assert "src/main.py" in result.output


def test_dependency_check_reads_requirements(tmp_ws):
    """dependency_check should read requirements.txt contents."""
    tmp_ws.write_text("requirements.txt", "fastapi==0.111.0\nuvicorn>=0.29\n# comment\n")

    kernel = _FakeKernel()
    env = _FakeEnvManager(kernel)
    executor = ToolExecutor(kernel, env, tmp_ws)

    result = executor.execute_one("dependency_check", {})
    assert result.ok is True
    assert "fastapi==0.111.0" in result.output
    assert "uvicorn>=0.29" in result.output
    # Comments should be filtered out
    assert "# comment" not in result.output


# ---------------------------------------------------------------------------
# Command tool tests
# ---------------------------------------------------------------------------


def test_lint_check_command_tool(tmp_ws):
    """lint_check should run ruff and return output."""
    kernel = _FakeKernel()
    env = _FakeEnvManager(kernel)
    executor = ToolExecutor(kernel, env, tmp_ws)

    result = executor.execute_one("lint_check", {"paths": ["src/main.py"]})
    assert result.ok is True
    assert result.tool_name == "lint_check"


def test_command_tool_unavailable(tmp_ws):
    """Command tool should return error when kernel says unavailable."""
    kernel = _FakeKernel(available=False)
    env = _FakeEnvManager(kernel)
    executor = ToolExecutor(kernel, env, tmp_ws)

    result = executor.execute_one("lint_check", {"paths": ["src"]})
    assert result.ok is False
    assert "not available" in result.error.lower() or "unavailable" in result.error.lower()


# ---------------------------------------------------------------------------
# Gather context tests
# ---------------------------------------------------------------------------


def test_gather_context_respects_relevance(tmp_ws):
    """Only tools whose relevance_check returns True should be gathered."""
    # Register two test tools: one always relevant, one never relevant
    always_name = "_test_always_relevant"
    never_name = "_test_never_relevant"
    register_tool(
        always_name, "Always run", "workspace",
        workspace_fn=lambda ws, args: "always_output",
        relevance_check=lambda task: True,
    )
    register_tool(
        never_name, "Never run", "workspace",
        workspace_fn=lambda ws, args: "never_output",
        relevance_check=lambda task: False,
    )

    try:
        kernel = _FakeKernel()
        env = _FakeEnvManager(kernel)
        executor = ToolExecutor(kernel, env, tmp_ws)

        results = executor.gather_context({"goal": "test", "files": []})
        result_names = [r.tool_name for r in results]
        assert always_name in result_names
        assert never_name not in result_names
    finally:
        _TOOL_REGISTRY.pop(always_name, None)
        _TOOL_REGISTRY.pop(never_name, None)


def test_gather_context_with_explicit_tool_list(tmp_ws):
    """When explicit tools list is given, only those tools run."""
    tmp_ws.write_text("requirements.txt", "requests==2.31.0\n")

    kernel = _FakeKernel()
    env = _FakeEnvManager(kernel)
    executor = ToolExecutor(kernel, env, tmp_ws)

    results = executor.gather_context(
        {"goal": "test", "files": []},
        tools=["dependency_check"],
    )
    assert len(results) == 1
    assert results[0].tool_name == "dependency_check"
    assert results[0].ok is True


# ---------------------------------------------------------------------------
# Output handling tests
# ---------------------------------------------------------------------------


def test_output_truncation(tmp_ws):
    """Long tool output should be truncated."""
    long_name = "_test_long_output"
    register_tool(
        long_name, "Long output", "workspace",
        workspace_fn=lambda ws, args: "x" * 10000,
    )

    try:
        kernel = _FakeKernel()
        env = _FakeEnvManager(kernel)
        executor = ToolExecutor(kernel, env, tmp_ws)

        result = executor.execute_one(long_name, {}, output_limit=500)
        assert result.truncated is True
        assert len(result.output) <= 520  # 500 + "... (truncated)" suffix
    finally:
        _TOOL_REGISTRY.pop(long_name, None)


def test_serialize_format(tmp_ws):
    """ToolExecutor.serialize should produce expected dict structure."""
    results = [
        ToolResult(tool_name="file_search", ok=True, output="found something"),
        ToolResult(tool_name="lint_check", ok=False, output="", error="exit code 1"),
    ]

    serialized = ToolExecutor.serialize(results)
    assert serialized["total_tools"] == 2
    assert len(serialized["tools"]) == 2
    assert serialized["tools"][0]["tool_name"] == "file_search"
    assert serialized["tools"][0]["ok"] is True
    assert serialized["tools"][1]["error"] == "exit code 1"
    assert "hint" in serialized


def test_tool_exception_returns_error(tmp_ws):
    """Tool that raises an exception should return ok=False result."""
    err_name = "_test_error_tool"

    def _raise_fn(ws, args):
        raise ValueError("Something broke")

    register_tool(
        err_name, "Raises error", "workspace",
        workspace_fn=_raise_fn,
    )

    try:
        kernel = _FakeKernel()
        env = _FakeEnvManager(kernel)
        executor = ToolExecutor(kernel, env, tmp_ws)

        result = executor.execute_one(err_name, {})
        assert result.ok is False
        assert "Something broke" in result.error
    finally:
        _TOOL_REGISTRY.pop(err_name, None)
