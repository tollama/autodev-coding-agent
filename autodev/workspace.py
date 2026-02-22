from __future__ import annotations

import os
import shutil
from dataclasses import dataclass


@dataclass
class FileWrite:
    path: str
    content: str


class Workspace:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def _resolve_under_root(self, relative_path: str) -> str:
        abs_path = os.path.abspath(os.path.join(self.root, relative_path))
        if os.path.commonpath([self.root, abs_path]) != self.root:
            raise ValueError(f"Path escapes workspace root: {relative_path}")
        return abs_path

    def apply_template(self, template_dir: str) -> None:
        if not os.path.exists(template_dir):
            raise FileNotFoundError(f"Template not found: {template_dir}")
        for base, _, files in os.walk(template_dir):
            rel = os.path.relpath(base, template_dir)
            dest_base = os.path.join(self.root, rel) if rel != "." else self.root
            os.makedirs(dest_base, exist_ok=True)
            for fn in files:
                src = os.path.join(base, fn)
                dst = os.path.join(dest_base, fn)
                if os.path.exists(dst):
                    continue
                shutil.copy2(src, dst)

    def write_files(self, writes: list[FileWrite]) -> None:
        for write in writes:
            abs_path = self._resolve_under_root(write.path)
            os.makedirs(os.path.dirname(abs_path), exist_ok=True)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(write.content)

    def read_file(self, path: str) -> str:
        abs_path = self._resolve_under_root(path)
        with open(abs_path, "r", encoding="utf-8") as f:
            return f.read()

    def list_files(self, max_files: int = 400) -> list[str]:
        out: list[str] = []
        for base, _, files in os.walk(self.root):
            for fn in files:
                rel = os.path.relpath(os.path.join(base, fn), self.root)
                out.append(rel)
                if len(out) >= max_files:
                    return sorted(out)
        return sorted(out)

