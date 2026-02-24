from pathlib import Path

from autodev.workspace import Change, Workspace


def test_workspace_patch_change_requires_valid_unified_diff_for_existing_file(tmp_path: Path):
    ws = Workspace(tmp_path)
    ws.write_text("app.py", "a = 1\n")

    valid_patch = """@@ -1,1 +1,1\n-a = 1\n+a = 2\n"""
    ws.apply_changes([Change(op="patch", path="app.py", content=valid_patch)])

    assert ws.read_text("app.py") == "a = 2\n"


def test_workspace_patch_rejects_invalid_patch_for_existing_file(tmp_path: Path):
    ws = Workspace(tmp_path)
    ws.write_text("app.py", "a = 1\n")

    invalid_patch = "just plain text replacement"
    try:
        ws.apply_changes([Change(op="patch", path="app.py", content=invalid_patch)])
    except ValueError as exc:
        assert "No hunk" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid patch text")


def test_workspace_patch_allows_full_replace_for_missing_file(tmp_path: Path):
    ws = Workspace(tmp_path)
    full_text = "hello\nworld\n"

    ws.apply_changes([Change(op="patch", path="new.txt", content=full_text)])
    assert ws.read_text("new.txt") == full_text
