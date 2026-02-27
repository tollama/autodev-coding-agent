"""Tests for the context engine: CodeIndex and ContextSelector."""

from __future__ import annotations

import pytest

from autodev.context_engine import (
    CodeIndex,
    ContextSelector,
    _detect_language,
    _parse_go,
    _parse_python,
    _parse_typescript,
)
from autodev.loop import _detect_incremental_mode, _write_change_summary
from autodev.workspace import Workspace


@pytest.fixture()
def tmp_ws(tmp_path):  # type: ignore[no-untyped-def]
    """Create a temporary workspace with sample files."""
    ws = Workspace(str(tmp_path))
    return ws


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------


def test_detect_language_python():
    assert _detect_language("src/main.py") == "python"


def test_detect_language_typescript():
    assert _detect_language("src/app.ts") == "typescript"
    assert _detect_language("src/component.tsx") == "typescript"


def test_detect_language_go():
    assert _detect_language("cmd/main.go") == "go"


def test_detect_language_unknown():
    assert _detect_language("README.md") == "unknown"
    assert _detect_language("data.json") == "unknown"


# ---------------------------------------------------------------------------
# Python parsing (ast-based)
# ---------------------------------------------------------------------------


def test_parse_python_extracts_classes_and_functions():
    source = '''
import os
from pathlib import Path

class MyService:
    """A service class."""

    def process(self, data):
        pass

async def fetch_data(url: str):
    """Fetch data from URL."""
    pass

def helper():
    pass

CONSTANT = 42
'''
    meta = _parse_python("src/service.py", source)
    assert meta.language == "python"
    assert meta.path == "src/service.py"

    names = [s.name for s in meta.symbols]
    assert "MyService" in names
    assert "process" in names
    assert "fetch_data" in names
    assert "helper" in names

    kinds = {s.name: s.kind for s in meta.symbols}
    assert kinds["MyService"] == "class"
    assert kinds["process"] == "function"
    assert kinds["fetch_data"] == "function"

    # Imports
    assert "os" in meta.imports
    assert "pathlib" in meta.imports


def test_parse_python_handles_syntax_error():
    meta = _parse_python("bad.py", "def foo(:\n  pass")
    assert meta.language == "python"
    assert meta.symbols == []
    assert meta.imports == []


def test_parse_python_docstrings():
    source = '''
class Foo:
    """This is a docstring for Foo."""
    pass

def bar():
    """Bar does something."""
    pass
'''
    meta = _parse_python("doc.py", source)
    foo = [s for s in meta.symbols if s.name == "Foo"][0]
    bar = [s for s in meta.symbols if s.name == "bar"][0]
    assert foo.docstring == "This is a docstring for Foo."
    assert bar.docstring == "Bar does something."


def test_parse_python_deduplicates_imports():
    source = '''
import os
import os
from os.path import join
from os import getcwd
'''
    meta = _parse_python("dup.py", source)
    # os should appear only once, os.path once
    assert meta.imports.count("os") == 1


# ---------------------------------------------------------------------------
# TypeScript parsing (regex-based)
# ---------------------------------------------------------------------------


def test_parse_typescript_extracts_exports_and_imports():
    source = '''
import { Router } from 'express';
import axios from 'axios';

export class UserService {
  async getUser(id: string) {}
}

export function createRouter(): Router {
  return Router();
}

export const API_URL = "https://example.com";

export interface UserDTO {
  id: string;
  name: string;
}
'''
    meta = _parse_typescript("src/service.ts", source)
    assert meta.language == "typescript"

    names = [s.name for s in meta.symbols]
    assert "UserService" in names
    assert "createRouter" in names
    assert "API_URL" in names
    assert "UserDTO" in names

    assert "express" in meta.imports
    assert "axios" in meta.imports


# ---------------------------------------------------------------------------
# Go parsing (regex-based)
# ---------------------------------------------------------------------------


def test_parse_go_extracts_funcs_and_types():
    source = '''
package main

import (
    "fmt"
    "net/http"
)

type Server struct {
    port int
}

type Handler interface {
    Handle()
}

func NewServer(port int) *Server {
    return &Server{port: port}
}

func (s *Server) Start() {
    fmt.Println("starting")
}
'''
    meta = _parse_go("cmd/main.go", source)
    assert meta.language == "go"

    names = [s.name for s in meta.symbols]
    assert "Server" in names
    assert "Handler" in names
    assert "NewServer" in names
    assert "Start" in names

    assert "fmt" in meta.imports
    assert "net/http" in meta.imports


# ---------------------------------------------------------------------------
# CodeIndex
# ---------------------------------------------------------------------------


def test_code_index_scans_python_files(tmp_ws):
    tmp_ws.write_text("src/models.py", '''
class User:
    """User model."""
    pass

class Order:
    pass

def get_user(user_id: int):
    pass
''')
    tmp_ws.write_text("src/api.py", '''
from src.models import User

def create_user(name: str):
    pass
''')
    tmp_ws.write_text("README.md", "# Project\nHello.")

    idx = CodeIndex(tmp_ws)
    idx.scan()

    assert "src/models.py" in idx.files
    assert "src/api.py" in idx.files
    # README.md should not be indexed (unknown language)
    assert "README.md" not in idx.files

    models_meta = idx.files["src/models.py"]
    assert len(models_meta.symbols) == 3  # User, Order, get_user
    assert models_meta.language == "python"


def test_code_index_find_symbol(tmp_ws):
    tmp_ws.write_text("a.py", "class Foo:\n    pass\n")
    tmp_ws.write_text("b.py", "class Foo:\n    pass\ndef bar():\n    pass\n")

    idx = CodeIndex(tmp_ws)
    idx.scan()

    foos = idx.find_symbol("Foo")
    assert len(foos) == 2
    assert {s.file for s in foos} == {"a.py", "b.py"}

    bars = idx.find_symbol("bar")
    assert len(bars) == 1
    assert bars[0].file == "b.py"

    assert idx.find_symbol("nonexistent") == []


def test_code_index_find_importers(tmp_ws):
    tmp_ws.write_text("models.py", "class User:\n    pass\n")
    tmp_ws.write_text("api.py", "from models import User\n")
    tmp_ws.write_text("cli.py", "import models\n")

    idx = CodeIndex(tmp_ws)
    idx.scan()

    importers = idx.find_importers("models")
    assert "api.py" in importers
    assert "cli.py" in importers


def test_code_index_structure_summary(tmp_ws):
    tmp_ws.write_text("src/main.py", "def main():\n    pass\n")
    tmp_ws.write_text("src/utils.py", "def helper():\n    pass\n")
    tmp_ws.write_text("tests/test_main.py", "def test_main():\n    pass\n")

    idx = CodeIndex(tmp_ws)
    idx.scan()

    summary = idx.structure_summary()
    assert "3 files" in summary
    assert "src" in summary
    assert "tests" in summary


def test_code_index_empty_workspace(tmp_ws):
    """CodeIndex.scan() should work on empty workspace without error."""
    idx = CodeIndex(tmp_ws)
    idx.scan()
    assert len(idx.files) == 0
    assert idx.structure_summary() == "Empty index (no source files found)."
    assert idx.find_symbol("anything") == []
    assert idx.find_importers("anything") == []


def test_code_index_file_summary(tmp_ws):
    tmp_ws.write_text("app.py", "import os\nclass App:\n    pass\ndef run():\n    pass\n")

    idx = CodeIndex(tmp_ws)
    idx.scan()

    summary = idx.file_summary("app.py")
    assert "app.py" in summary
    assert "python" in summary
    assert "App" in summary
    assert "run" in summary

    # Non-indexed file
    assert "<not indexed>" in idx.file_summary("nonexistent.py")


# ---------------------------------------------------------------------------
# ContextSelector
# ---------------------------------------------------------------------------


def test_context_selector_follows_imports(tmp_ws):
    tmp_ws.write_text("src/models.py", '''
class User:
    pass
class Order:
    pass
''')
    tmp_ws.write_text("src/api.py", '''
from src.models import User

def create_user():
    pass
''')
    tmp_ws.write_text("src/unrelated.py", '''
def unrelated_func():
    pass
''')

    idx = CodeIndex(tmp_ws)
    idx.scan()
    selector = ContextSelector(idx, tmp_ws)

    # When asking for api.py context, models.py should be included (import 1-hop)
    ctx = selector.select_for_task(
        goal="Implement user creation endpoint",
        seed_files=["src/api.py"],
    )
    assert "src/api.py" in ctx
    assert "src/models.py" in ctx


def test_context_selector_respects_budget(tmp_ws):
    # Create many files
    for i in range(20):
        tmp_ws.write_text(f"mod_{i}.py", f"def func_{i}():\n    pass\n")

    idx = CodeIndex(tmp_ws)
    idx.scan()
    selector = ContextSelector(idx, tmp_ws)

    ctx = selector.select_for_task(
        goal="test",
        seed_files=[f"mod_{i}.py" for i in range(20)],
        max_files=5,
    )
    assert len(ctx) <= 5


def test_context_selector_returns_seed_files_even_if_unindexed(tmp_ws):
    tmp_ws.write_text("config.yaml", "key: value")  # Not a code file

    idx = CodeIndex(tmp_ws)
    idx.scan()
    selector = ContextSelector(idx, tmp_ws)

    ctx = selector.select_for_task(
        goal="Update config",
        seed_files=["config.yaml"],
    )
    # config.yaml is not in the index but exists on disk
    assert "config.yaml" in ctx


def test_context_selector_planner_summary(tmp_ws):
    tmp_ws.write_text("src/main.py", '''
import fastapi
from src.models import User

class App:
    pass

def create_app():
    pass
''')
    tmp_ws.write_text("src/models.py", '''
from pydantic import BaseModel

class User(BaseModel):
    name: str
''')
    tmp_ws.write_text("tests/test_main.py", '''
import pytest

def test_app():
    pass
''')

    idx = CodeIndex(tmp_ws)
    idx.scan()
    selector = ContextSelector(idx, tmp_ws)

    planner_ctx = selector.select_for_planner(
        prd_keywords=["API", "User management"],
    )

    assert "structure" in planner_ctx
    assert "key_files" in planner_ctx
    assert "test_files" in planner_ctx
    assert "detected_patterns" in planner_ctx
    assert "total_indexed_files" in planner_ctx

    # Should detect fastapi and pydantic patterns
    assert "fastapi" in planner_ctx["detected_patterns"]
    assert "pydantic" in planner_ctx["detected_patterns"]

    # Test files should include tests/test_main.py
    assert "tests/test_main.py" in planner_ctx["test_files"]


def test_context_selector_keyword_matching(tmp_ws):
    tmp_ws.write_text("auth.py", '''
class AuthService:
    def authenticate(self, token):
        pass
    def authorize(self, user, resource):
        pass
''')
    tmp_ws.write_text("payment.py", '''
class PaymentProcessor:
    def process_payment(self, amount):
        pass
''')

    idx = CodeIndex(tmp_ws)
    idx.scan()
    selector = ContextSelector(idx, tmp_ws)

    # Goal mentions "authentication" — should find auth.py via keyword overlap
    ctx = selector.select_for_task(
        goal="Fix authentication token validation",
        seed_files=[],
    )
    assert "auth.py" in ctx


def test_context_selector_missing_seed_files(tmp_ws):
    """Missing seed files should be marked as <missing>."""
    idx = CodeIndex(tmp_ws)
    idx.scan()
    selector = ContextSelector(idx, tmp_ws)

    ctx = selector.select_for_task(
        goal="Create new feature",
        seed_files=["nonexistent.py"],
    )
    assert ctx.get("nonexistent.py") == "<missing>"


# ---------------------------------------------------------------------------
# Incremental Mode Detection
# ---------------------------------------------------------------------------


def test_detect_incremental_mode_real_project(tmp_ws):
    """3+ source files with 5+ symbols → incremental mode detected."""
    tmp_ws.write_text("src/models.py", "class User:\n    pass\nclass Order:\n    pass\n")
    tmp_ws.write_text("src/api.py", "def create_user():\n    pass\ndef delete_user():\n    pass\n")
    tmp_ws.write_text("src/utils.py", "def helper():\n    pass\n")

    idx = CodeIndex(tmp_ws)
    idx.scan()
    assert _detect_incremental_mode(idx) is True


def test_detect_incremental_mode_empty(tmp_ws):
    """Empty workspace → not incremental."""
    idx = CodeIndex(tmp_ws)
    idx.scan()
    assert _detect_incremental_mode(idx) is False


def test_detect_incremental_mode_minimal(tmp_ws):
    """Only 1 file with 1 symbol → not incremental (too small)."""
    tmp_ws.write_text("main.py", "def main():\n    pass\n")

    idx = CodeIndex(tmp_ws)
    idx.scan()
    assert _detect_incremental_mode(idx) is False


def test_detect_incremental_mode_two_files_few_symbols(tmp_ws):
    """2 files with 3 symbols → not incremental (below threshold)."""
    tmp_ws.write_text("a.py", "def foo():\n    pass\n")
    tmp_ws.write_text("b.py", "def bar():\n    pass\ndef baz():\n    pass\n")

    idx = CodeIndex(tmp_ws)
    idx.scan()
    # 2 files < 3 threshold
    assert _detect_incremental_mode(idx) is False


# ---------------------------------------------------------------------------
# Change Summary Tracking
# ---------------------------------------------------------------------------


def test_write_change_summary_incremental(tmp_ws):
    """Change summary correctly tracks added, modified, and deleted files."""
    # Pre-existing files
    tmp_ws.write_text("existing.py", "x = 1\n")
    tmp_ws.write_text("to_delete.py", "y = 2\n")
    pre_files = {"existing.py", "to_delete.py"}

    # Simulate changes: add new file, delete one
    tmp_ws.write_text("new_file.py", "z = 3\n")
    tmp_ws.delete("to_delete.py")

    summary = _write_change_summary(tmp_ws, pre_files, incremental_mode=True)

    assert summary["incremental_mode"] is True
    assert "new_file.py" in summary["files_added"]
    assert "existing.py" in summary["files_possibly_modified"]
    assert "to_delete.py" in summary["files_deleted"]
    assert summary["files_added_count"] >= 1
    assert summary["files_deleted_count"] >= 1

    # Verify it was written to disk
    assert tmp_ws.exists(".autodev/change_summary.json")


def test_write_change_summary_greenfield(tmp_ws):
    """Greenfield mode: all files are 'added', none modified or deleted."""
    tmp_ws.write_text("app.py", "def main():\n    pass\n")
    pre_files: set[str] = set()

    summary = _write_change_summary(tmp_ws, pre_files, incremental_mode=False)

    assert summary["incremental_mode"] is False
    assert "app.py" in summary["files_added"]
    assert summary["files_possibly_modified_count"] == 0
    assert summary["files_deleted_count"] == 0
