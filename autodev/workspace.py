from __future__ import annotations
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List
from os import PathLike
from .patch_utils import apply_unified_diff, validate_unified_diff


@dataclass
class Change:
    op: str   # write|delete|patch
    path: str
    content: str | None = None


class Workspace:
    CONTEXT_EXCLUDED_DIRS = {
        ".git",
        ".venv",
        ".autodev",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "sbom",
        "dist",
        "build",
    }
    CONTEXT_EXCLUDED_SUFFIXES = {".pyc"}
    SNAPSHOT_DIR = ".autodev/snapshots"

    def __init__(self, root: str | PathLike[str]):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def apply_template(self, template_dir: str) -> None:
        if not os.path.isdir(template_dir):
            raise FileNotFoundError(f"Template not found: {template_dir}")
        for base, _, files in os.walk(template_dir):
            rel = os.path.relpath(base, template_dir)
            dest_base = self.root if rel == "." else os.path.join(self.root, rel)
            os.makedirs(dest_base, exist_ok=True)
            for fn in files:
                src = os.path.join(base, fn)
                dst = os.path.join(dest_base, fn)
                if os.path.exists(dst):
                    continue
                shutil.copy2(src, dst)

    def _abs(self, rel_path: str | PathLike[str]) -> str:
        # strip leading slash so os.path.join treats it strictly as relative
        rel_path = os.fspath(rel_path).lstrip("/\\")
        abs_path = os.path.abspath(os.path.join(self.root, rel_path))
        try:
            common = os.path.commonpath([self.root, abs_path])
        except ValueError as exc:
            raise ValueError(f"Invalid path: {rel_path}") from exc
        if common != self.root:
            raise ValueError(f"Path escapes workspace root: {rel_path}")
        return abs_path

    def write_text(self, rel_path: str | PathLike[str], content: str) -> None:
        abs_path = self._abs(rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)

    def delete(self, rel_path: str | PathLike[str]) -> None:
        abs_path = self._abs(rel_path)
        if os.path.exists(abs_path):
            os.remove(abs_path)

    def read_text(self, rel_path: str | PathLike[str]) -> str:
        abs_path = self._abs(rel_path)
        with open(abs_path, "r", encoding="utf-8") as f:
            return f.read()

    def exists(self, rel_path: str | PathLike[str]) -> bool:
        return os.path.exists(self._abs(rel_path))

    @staticmethod
    def _materialize_patch_for_new_file(diff: str) -> str | None:
        """Best-effort fallback for malformed creation patches."""
        added: list[str] = []
        for line in diff.splitlines():
            if line.startswith(("+++", "@@")):
                continue
            if line.startswith("+"):
                added.append(line[1:])
        if not added:
            return None
        return "\n".join(added) + "\n"

    def list_files(self, max_files: int = 1200) -> List[str]:
        out: List[str] = []
        for base, _, files in os.walk(self.root):
            for fn in files:
                rel = os.path.relpath(os.path.join(base, fn), self.root)
                out.append(rel)
                if len(out) >= max_files:
                    return sorted(out)
        return sorted(out)

    @classmethod
    def _context_file_allowed(cls, rel_path: str) -> bool:
        rel_norm = rel_path.replace("\\", "/")
        parts = rel_norm.split("/")
        for part in parts[:-1]:
            if part in cls.CONTEXT_EXCLUDED_DIRS:
                return False
        for suffix in cls.CONTEXT_EXCLUDED_SUFFIXES:
            if rel_norm.endswith(suffix):
                return False
        return True

    def list_context_files(self, max_files: int | None = 1200) -> List[str]:
        out: List[str] = []
        for base, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in self.CONTEXT_EXCLUDED_DIRS]
            for fn in files:
                rel = os.path.relpath(os.path.join(base, fn), self.root)
                if not self._context_file_allowed(rel):
                    continue
                out.append(rel)
                if max_files is not None and len(out) >= max_files:
                    return sorted(out)
        return sorted(out)

    def apply_changes(self, changes: List[Change], dry_run: bool = False) -> None:
        # Validate and compute every change before mutating anything, so we can
        # fail early and keep behavior atomic.
        pending: List[dict[str, Any]] = []

        for c in changes:
            if c.op == "write":
                if c.content is None:
                    raise ValueError("write op requires content")
                existed = self.exists(c.path)
                backup = self.read_text(c.path) if existed else None
                pending.append({
                    "op": "write",
                    "path": c.path,
                    "backup": backup,
                    "backup_exists": existed,
                    "next_content": c.content,
                    "noop": existed and backup == c.content,
                })
            elif c.op == "delete":
                existed = self.exists(c.path)
                backup = self.read_text(c.path) if existed else None
                pending.append({
                    "op": "delete",
                    "path": c.path,
                    "backup": backup,
                    "backup_exists": existed,
                })
            elif c.op == "patch":
                if c.content is None:
                    raise ValueError("patch op requires content")
                if c.content == "":
                    raise ValueError("patch content must not be empty")

                if self.exists(c.path):
                    validate_unified_diff(c.content)
                    original = self.read_text(c.path)
                    try:
                        updated = apply_unified_diff(original, c.content)
                    except Exception:
                        materialized = self._materialize_patch_for_new_file(c.content)
                        if materialized is None:
                            raise
                        updated = materialized
                    backup = original
                    backup_exists = True
                else:
                    try:
                        updated = apply_unified_diff("", c.content)
                    except Exception:
                        materialized = self._materialize_patch_for_new_file(c.content)
                        if materialized is None:
                            raise
                        updated = materialized
                    backup = None
                    backup_exists = False

                pending.append({
                    "op": "patch",
                    "path": c.path,
                    "backup": backup,
                    "backup_exists": backup_exists,
                    "next_content": updated,
                    "noop": backup_exists and updated == backup,
                })
            else:
                raise ValueError(f"Unknown op: {c.op}")

        if dry_run:
            return

        applied = []
        try:
            for p in pending:
                if p["op"] == "write":
                    if p.get("noop"):
                        continue
                    self.write_text(p["path"], p["next_content"])
                    applied.append(p)
                elif p["op"] == "delete":
                    self.delete(p["path"])
                    applied.append(p)
                elif p["op"] == "patch":
                    if p.get("noop"):
                        continue
                    self.write_text(p["path"], p["next_content"])
                    applied.append(p)
        except Exception:
            for p in reversed(applied):
                if p["op"] in ("write", "patch"):
                    if p["backup_exists"]:
                        self.write_text(p["path"], p["backup"])
                    else:
                        if self.exists(p["path"]):
                            self.delete(p["path"])
                elif p["op"] == "delete":
                    if p["backup_exists"]:
                        self.write_text(p["path"], p["backup"])
            raise

    # ------------------------------------------------------------------
    # Snapshot / Rollback
    # ------------------------------------------------------------------

    @staticmethod
    def _backup_filename(rel_path: str) -> str:
        """Encode a relative path as a flat filename for snapshot storage."""
        return rel_path.replace("/", "__").replace("\\", "__")

    def snapshot(self, name: str) -> Dict[str, Any]:
        """Capture workspace source files to ``.autodev/snapshots/{name}/``.

        Uses :meth:`list_context_files` so ``.autodev/``, ``.git/``,
        ``.venv/`` and other metadata directories are excluded automatically.
        Overwrites any existing snapshot with the same *name* (idempotent).

        Returns the manifest dict.
        """
        snapshot_base = os.path.join(self.SNAPSHOT_DIR, name)
        abs_snapshot = os.path.join(self.root, snapshot_base)
        if os.path.isdir(abs_snapshot):
            shutil.rmtree(abs_snapshot)

        context_files = self.list_context_files(max_files=None)
        manifest_files: Dict[str, Dict[str, str]] = {}

        for rel_path in context_files:
            content = self.read_text(rel_path)
            sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
            backup_name = self._backup_filename(rel_path)
            backup_rel = os.path.join(snapshot_base, "files", backup_name)
            self.write_text(backup_rel, content)
            manifest_files[rel_path] = {
                "sha256": sha256,
                "backup_path": f"files/{backup_name}",
            }

        manifest: Dict[str, Any] = {
            "name": name,
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "file_count": len(manifest_files),
            "files": manifest_files,
        }
        self.write_text(
            os.path.join(snapshot_base, "manifest.json"),
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
        return manifest

    def rollback(self, name: str) -> Dict[str, Any]:
        """Restore workspace to a previously captured snapshot.

        * Files added after the snapshot are deleted.
        * Files modified after the snapshot are restored.
        * ``.autodev/`` metadata is never touched (excluded by
          :meth:`list_context_files`).

        Raises :class:`FileNotFoundError` if the snapshot does not exist.
        Returns the manifest dict.
        """
        snapshot_base = os.path.join(self.SNAPSHOT_DIR, name)
        manifest_path = os.path.join(snapshot_base, "manifest.json")
        abs_manifest = os.path.join(self.root, manifest_path)
        if not os.path.isfile(abs_manifest):
            raise FileNotFoundError(f"Snapshot not found: {name}")

        manifest: Dict[str, Any] = json.loads(self.read_text(manifest_path))
        snapshot_files = set(manifest.get("files", {}).keys())

        # Delete files added after the snapshot
        current_files = self.list_context_files(max_files=None)
        for rel_path in current_files:
            if rel_path not in snapshot_files:
                self.delete(rel_path)

        # Restore files to snapshot state
        for rel_path, info in manifest.get("files", {}).items():
            backup_rel = os.path.join(snapshot_base, info["backup_path"])
            content = self.read_text(backup_rel)
            self.write_text(rel_path, content)

        return manifest

    def compute_loc_delta(self, snapshot_name: str) -> int:
        """Compute net LOC change between a snapshot and the current workspace.

        Returns ``current_total_loc - snapshot_total_loc``.  Positive means
        lines were added; negative means lines were removed.  Returns ``0``
        if the snapshot does not exist or on any I/O error.
        """
        snapshot_base = os.path.join(self.SNAPSHOT_DIR, snapshot_name)
        manifest_path = os.path.join(snapshot_base, "manifest.json")
        abs_manifest = os.path.join(self.root, manifest_path)
        if not os.path.isfile(abs_manifest):
            return 0

        try:
            manifest: Dict[str, Any] = json.loads(self.read_text(manifest_path))
        except Exception:
            return 0

        # Count LOC in snapshot (from backed-up files)
        snapshot_loc = 0
        for _rel, info in manifest.get("files", {}).items():
            backup_rel = os.path.join(snapshot_base, info["backup_path"])
            try:
                content = self.read_text(backup_rel)
                snapshot_loc += content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            except Exception:
                pass

        # Count LOC in current workspace
        current_loc = 0
        for rel_path in self.list_context_files(max_files=None):
            try:
                content = self.read_text(rel_path)
                current_loc += content.count("\n") + (1 if content and not content.endswith("\n") else 0)
            except Exception:
                pass

        return current_loc - snapshot_loc

    def list_snapshots(self) -> List[str]:
        """Return sorted list of available snapshot names."""
        snapshots_dir = os.path.join(self.root, self.SNAPSHOT_DIR)
        if not os.path.isdir(snapshots_dir):
            return []
        names: List[str] = []
        for entry in os.listdir(snapshots_dir):
            entry_path = os.path.join(snapshots_dir, entry)
            if os.path.isdir(entry_path):
                manifest = os.path.join(entry_path, "manifest.json")
                if os.path.isfile(manifest):
                    names.append(entry)
        return sorted(names)
