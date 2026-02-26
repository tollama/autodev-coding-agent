#!/usr/bin/env python3
"""Lightweight markdown local link checker.

Checks only repository-local links to keep CI stable and fast.
External links (http/https/mailto), pure anchors (#section), and templated
placeholders are ignored.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_DIRS = [REPO_ROOT / "docs", REPO_ROOT / ".github"]
README_FILES = [REPO_ROOT / "README.md", REPO_ROOT / "CHANGELOG.md"]

LINK_PATTERN = re.compile(r"!?(?:\[[^\]]*\])\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def iter_markdown_files() -> list[Path]:
    files: list[Path] = []
    for doc_dir in DOC_DIRS:
        if doc_dir.exists():
            files.extend(doc_dir.rglob("*.md"))
    for readme in README_FILES:
        if readme.exists():
            files.append(readme)
    return sorted(set(files))


def is_ignored_target(target: str) -> bool:
    lowered = target.lower()
    return (
        lowered.startswith("http://")
        or lowered.startswith("https://")
        or lowered.startswith("mailto:")
        or lowered.startswith("#")
        or "{{" in target
        or target.startswith("<") and target.endswith(">")
    )


def resolve_target(src: Path, raw_target: str) -> Path:
    target = raw_target.split("#", 1)[0]
    if target.startswith("/"):
        # Repo-relative path (best effort)
        return (REPO_ROOT / target.lstrip("/")).resolve()
    return (src.parent / target).resolve()


def main() -> int:
    missing: list[str] = []
    files = iter_markdown_files()

    for md_file in files:
        content = md_file.read_text(encoding="utf-8")
        for raw in LINK_PATTERN.findall(content):
            target = raw.strip()
            if is_ignored_target(target):
                continue
            resolved = resolve_target(md_file, target)
            if not resolved.exists():
                missing.append(f"{md_file.relative_to(REPO_ROOT)} -> {target}")

    if missing:
        print("[FAIL] Broken local markdown links found:")
        for item in missing:
            print(f"  - {item}")
        return 1

    print(f"[PASS] Markdown local link check passed ({len(files)} files scanned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
