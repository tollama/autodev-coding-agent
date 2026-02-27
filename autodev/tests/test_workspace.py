"""Tests for autodev.workspace module."""

from __future__ import annotations

import hashlib
import os

import pytest

from autodev.workspace import Change, Workspace


@pytest.fixture()
def ws(tmp_path):
    return Workspace(str(tmp_path))


# ---------------------------------------------------------------------------
# Basic file operations
# ---------------------------------------------------------------------------


def test_init_creates_root_directory(tmp_path):
    """Workspace should create root dir if it doesn't exist."""
    new_root = os.path.join(str(tmp_path), "new_project")
    ws = Workspace(new_root)
    assert os.path.isdir(ws.root)


def test_write_text_creates_file(ws):
    """write_text should create file and parent directories."""
    ws.write_text("src/main.py", "print('hello')")
    assert ws.exists("src/main.py")
    assert ws.read_text("src/main.py") == "print('hello')"


def test_read_text_returns_content(ws):
    """read_text should return exact file content."""
    ws.write_text("data.txt", "line1\nline2\n")
    assert ws.read_text("data.txt") == "line1\nline2\n"


def test_delete_removes_file(ws):
    """delete should remove an existing file."""
    ws.write_text("temp.py", "x = 1")
    assert ws.exists("temp.py")
    ws.delete("temp.py")
    assert not ws.exists("temp.py")


def test_delete_noop_for_nonexistent(ws):
    """delete should not raise for nonexistent file."""
    ws.delete("nonexistent.py")  # should not raise


def test_exists_true_for_existing(ws):
    """exists should return True for existing file."""
    ws.write_text("a.py", "")
    assert ws.exists("a.py") is True


def test_exists_false_for_missing(ws):
    """exists should return False for missing file."""
    assert ws.exists("missing.py") is False


# ---------------------------------------------------------------------------
# Path security
# ---------------------------------------------------------------------------


def test_abs_rejects_path_escape(ws):
    """Paths traversing outside root should be rejected."""
    with pytest.raises(ValueError, match="escapes workspace root"):
        ws.write_text("../../etc/passwd", "bad")


def test_abs_strips_leading_slash(ws):
    """Leading slash should be stripped (treated as relative)."""
    ws.write_text("/src/main.py", "ok")
    assert ws.exists("src/main.py")


# ---------------------------------------------------------------------------
# list_files / list_context_files
# ---------------------------------------------------------------------------


def test_list_files_sorted(ws):
    """list_files should return sorted relative paths."""
    ws.write_text("b.py", "")
    ws.write_text("a.py", "")
    ws.write_text("src/c.py", "")
    files = ws.list_files()
    assert files == sorted(files)
    assert "a.py" in files
    assert "b.py" in files


def test_list_files_max_limit(ws):
    """list_files should respect max_files limit."""
    for i in range(10):
        ws.write_text(f"file_{i}.py", "")
    files = ws.list_files(max_files=3)
    assert len(files) == 3


def test_list_context_files_excludes_pycache(ws):
    """list_context_files should exclude __pycache__ dirs."""
    ws.write_text("src/main.py", "")
    ws.write_text("__pycache__/main.cpython-311.pyc", "")
    files = ws.list_context_files()
    assert "src/main.py" in files
    assert not any("__pycache__" in f for f in files)


def test_context_file_allowed_blocks_pyc():
    """.pyc files should be excluded."""
    assert Workspace._context_file_allowed("src/main.py") is True
    assert Workspace._context_file_allowed("src/main.pyc") is False


# ---------------------------------------------------------------------------
# apply_changes
# ---------------------------------------------------------------------------


def test_apply_changes_write_creates_file(ws):
    """Write op should create file with given content."""
    ws.apply_changes([Change(op="write", path="new.py", content="x = 1")])
    assert ws.read_text("new.py") == "x = 1"


def test_apply_changes_delete_removes_file(ws):
    """Delete op should remove file."""
    ws.write_text("old.py", "delete me")
    ws.apply_changes([Change(op="delete", path="old.py")])
    assert not ws.exists("old.py")


def test_apply_changes_write_requires_content(ws):
    """Write op without content should raise ValueError."""
    with pytest.raises(ValueError, match="write op requires content"):
        ws.apply_changes([Change(op="write", path="x.py", content=None)])


def test_apply_changes_unknown_op_raises(ws):
    """Unknown op should raise ValueError."""
    with pytest.raises(ValueError, match="Unknown op"):
        ws.apply_changes([Change(op="rename", path="x.py")])


def test_apply_changes_dry_run_no_mutation(ws):
    """dry_run=True should not create/modify files."""
    ws.apply_changes([Change(op="write", path="test.py", content="x = 1")], dry_run=True)
    assert not ws.exists("test.py")


def test_apply_changes_rollback_on_failure(ws):
    """If one change fails, previous changes should be rolled back."""
    ws.write_text("safe.py", "original")

    changes = [
        Change(op="write", path="safe.py", content="modified"),
        Change(op="write", path="../../escape.py", content="bad"),
    ]
    with pytest.raises(ValueError):
        ws.apply_changes(changes)

    # safe.py should be rolled back to original
    assert ws.read_text("safe.py") == "original"


def test_apply_changes_noop_skip(ws):
    """Writing same content should be treated as noop."""
    ws.write_text("same.py", "unchanged")
    ws.apply_changes([Change(op="write", path="same.py", content="unchanged")])
    assert ws.read_text("same.py") == "unchanged"


# ---------------------------------------------------------------------------
# Snapshot / Rollback
# ---------------------------------------------------------------------------


def test_snapshot_creates_manifest(ws):
    """snapshot should create manifest.json with correct structure."""
    ws.write_text("main.py", "print('hello')")
    manifest = ws.snapshot("v1")

    assert manifest["name"] == "v1"
    assert manifest["file_count"] == 1
    assert "main.py" in manifest["files"]
    assert "created_at" in manifest

    # Verify manifest file was persisted
    manifest_path = os.path.join(ws.root, ".autodev", "snapshots", "v1", "manifest.json")
    assert os.path.isfile(manifest_path)


def test_snapshot_captures_files(ws):
    """snapshot should back up all source files with correct content."""
    ws.write_text("src/app/models.py", "class User: pass")
    ws.write_text("src/app/api.py", "def get(): return {}")
    ws.write_text("README.md", "# Project")

    manifest = ws.snapshot("baseline")
    assert manifest["file_count"] == 3

    # Verify backup files exist with correct content
    for rel_path, info in manifest["files"].items():
        backup_rel = os.path.join(".autodev", "snapshots", "baseline", info["backup_path"])
        assert ws.exists(backup_rel)
        assert ws.read_text(backup_rel) == ws.read_text(rel_path)


def test_rollback_restores_files(ws):
    """rollback should restore modified files to snapshot state."""
    ws.write_text("config.py", "DEBUG = False")
    ws.write_text("src/main.py", "v1")
    ws.snapshot("before_change")

    # Modify files
    ws.write_text("config.py", "DEBUG = True")
    ws.write_text("src/main.py", "v2 — completely different")

    ws.rollback("before_change")
    assert ws.read_text("config.py") == "DEBUG = False"
    assert ws.read_text("src/main.py") == "v1"


def test_rollback_deletes_added_files(ws):
    """rollback should delete files added after the snapshot."""
    ws.write_text("original.py", "keep me")
    ws.snapshot("clean_state")

    # Add new files
    ws.write_text("generated.py", "new code")
    ws.write_text("src/extra.py", "more new code")

    ws.rollback("clean_state")
    assert ws.exists("original.py")
    assert not ws.exists("generated.py")
    assert not ws.exists("src/extra.py")


def test_rollback_nonexistent_raises(ws):
    """rollback should raise FileNotFoundError for missing snapshot."""
    with pytest.raises(FileNotFoundError, match="Snapshot not found"):
        ws.rollback("nonexistent")


def test_list_snapshots_empty(ws):
    """list_snapshots should return empty list on fresh workspace."""
    assert ws.list_snapshots() == []


def test_list_snapshots_returns_names(ws):
    """list_snapshots should return sorted snapshot names."""
    ws.write_text("a.py", "")
    ws.snapshot("beta")
    ws.snapshot("alpha")

    names = ws.list_snapshots()
    assert names == ["alpha", "beta"]


def test_snapshot_excludes_autodev(ws):
    """snapshot should not include .autodev/ files."""
    ws.write_text("src/main.py", "code")
    ws.write_text(".autodev/metadata.json", '{"key": "value"}')

    manifest = ws.snapshot("check")
    assert "src/main.py" in manifest["files"]
    assert ".autodev/metadata.json" not in manifest["files"]


def test_snapshot_overwrite(ws):
    """Re-creating a snapshot with the same name should reflect latest state."""
    ws.write_text("data.py", "version_1")
    ws.snapshot("snap")

    ws.write_text("data.py", "version_2")
    ws.snapshot("snap")

    # Rollback should restore version_2 (the second snapshot), not version_1
    ws.write_text("data.py", "version_3")
    ws.rollback("snap")
    assert ws.read_text("data.py") == "version_2"


def test_rollback_to_empty(ws):
    """Rollback to empty snapshot should delete all source files."""
    ws.snapshot("empty")

    ws.write_text("added1.py", "x")
    ws.write_text("added2.py", "y")

    ws.rollback("empty")
    context_files = ws.list_context_files(max_files=None)
    assert context_files == []


def test_snapshot_rollback_roundtrip(ws):
    """Full roundtrip: create → snapshot → modify/add/delete → rollback."""
    ws.write_text("keep.py", "original")
    ws.write_text("modify.py", "before")
    ws.write_text("to_delete_later.py", "temp")
    ws.snapshot("checkpoint")

    # Modify one file
    ws.write_text("modify.py", "after")
    # Add a new file
    ws.write_text("brand_new.py", "fresh")
    # Delete an existing file (via direct os.remove since ws.delete doesn't affect
    # the snapshot — the file is still in the backup)
    ws.delete("to_delete_later.py")

    ws.rollback("checkpoint")
    assert ws.read_text("keep.py") == "original"
    assert ws.read_text("modify.py") == "before"
    assert ws.read_text("to_delete_later.py") == "temp"
    assert not ws.exists("brand_new.py")


def test_snapshot_sha256_manifest(ws):
    """Manifest should contain correct SHA-256 hashes."""
    content = "print('hello world')"
    ws.write_text("hello.py", content)

    manifest = ws.snapshot("hash_check")
    expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert manifest["files"]["hello.py"]["sha256"] == expected_hash
