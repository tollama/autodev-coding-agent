#!/usr/bin/env python3
"""Apply canonical autonomous-wave events to status docs.

AV4-001 scope:
- map canonical status events to docs status transitions
- keep updates idempotent and easy to run manually as fallback
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class CanonicalEventSpec:
    mode: str
    scope: str
    state: str
    av4_snapshot: str
    plan_title: str
    plan_av4_snapshot: str
    backlog_title: str
    backlog_av4_snapshot: str


CANONICAL_EVENT_MAP: dict[str, CanonicalEventSpec] = {
    "av4.kickoff.started": CanonicalEventSpec(
        mode="AV4 Kickoff",
        scope="AV4 wave planning + kickoff execution start",
        state="AV3 closed on `main`; AV4 kickoff package started",
        av4_snapshot="🚧 Kickoff started (plan + backlog published)",
        plan_title="# PLAN — Next Wave (AV4 Kickoff Active)",
        plan_av4_snapshot="- AV4 kickoff package is now active (`docs/AUTONOMOUS_V4_WAVE_PLAN.md`, `docs/AUTONOMOUS_V4_BACKLOG.md`).",
        backlog_title="# BACKLOG — Next Wave (AV4 Kickoff Queue)",
        backlog_av4_snapshot="- AV4 kickoff: 🚧 started",
    )
}


def _kst_timestamp() -> str:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    return now.strftime("%Y-%m-%d %H:%M KST (Asia/Seoul)")


def _replace_once(content: str, old: str, new: str, *, file_path: Path) -> str:
    if old not in content:
        raise ValueError(f"expected snippet not found in {file_path}: {old}")
    return content.replace(old, new, 1)


def _apply_status_board(path: Path, spec: CanonicalEventSpec, *, timestamp: str) -> bool:
    original = path.read_text(encoding="utf-8")
    updated = original
    updated = _replace_once(
        updated,
        "- **Mode:** AV4 Kickoff",
        f"- **Mode:** {spec.mode}",
        file_path=path,
    )
    updated = _replace_once(
        updated,
        "- **Scope:** AV4 wave planning + kickoff execution start",
        f"- **Scope:** {spec.scope}",
        file_path=path,
    )
    updated = _replace_once(
        updated,
        "- **State:** AV3 closed on `main`; AV4 kickoff package started",
        f"- **State:** {spec.state}",
        file_path=path,
    )
    updated = _replace_once(
        updated,
        "- **AV4:** 🚧 Kickoff started (plan + backlog published)",
        f"- **AV4:** {spec.av4_snapshot}",
        file_path=path,
    )

    prefix = "Status timestamp: "
    # Replace first status timestamp line if present.
    for line in updated.splitlines():
        if line.startswith(prefix):
            updated = _replace_once(updated, line, f"{prefix}{timestamp}", file_path=path)
            break

    if updated != original:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def _apply_plan(path: Path, spec: CanonicalEventSpec) -> bool:
    original = path.read_text(encoding="utf-8")
    updated = _replace_once(
        original,
        "# PLAN — Next Wave (AV4 Kickoff Active)",
        spec.plan_title,
        file_path=path,
    )
    updated = _replace_once(
        updated,
        "- AV4 kickoff package is now active (`docs/AUTONOMOUS_V4_WAVE_PLAN.md`, `docs/AUTONOMOUS_V4_BACKLOG.md`).",
        spec.plan_av4_snapshot,
        file_path=path,
    )
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def _apply_backlog(path: Path, spec: CanonicalEventSpec) -> bool:
    original = path.read_text(encoding="utf-8")
    updated = _replace_once(
        original,
        "# BACKLOG — Next Wave (AV4 Kickoff Queue)",
        spec.backlog_title,
        file_path=path,
    )
    updated = _replace_once(
        updated,
        "- AV4 kickoff: 🚧 started",
        spec.backlog_av4_snapshot,
        file_path=path,
    )
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def apply_event(event: str, *, docs_root: Path, timestamp: str | None = None) -> list[Path]:
    spec = CANONICAL_EVENT_MAP.get(event)
    if spec is None:
        known = ", ".join(sorted(CANONICAL_EVENT_MAP))
        raise ValueError(f"unknown event '{event}'. Known events: {known}")

    ts = timestamp or _kst_timestamp()
    changed: list[Path] = []

    status_path = docs_root / "STATUS_BOARD_CURRENT.md"
    plan_path = docs_root / "PLAN_NEXT_WEEK.md"
    backlog_path = docs_root / "BACKLOG_NEXT_WEEK.md"

    if _apply_status_board(status_path, spec, timestamp=ts):
        changed.append(status_path)
    if _apply_plan(plan_path, spec):
        changed.append(plan_path)
    if _apply_backlog(backlog_path, spec):
        changed.append(backlog_path)

    return changed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event", help="canonical event key (e.g. av4.kickoff.started)")
    parser.add_argument(
        "--docs-root",
        default=str(Path(__file__).resolve().parents[1] / "docs"),
        help="docs directory root (default: repo docs/)",
    )
    parser.add_argument(
        "--timestamp",
        default=None,
        help="status timestamp override; default is current KST",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate/apply in-memory and print target files without writing",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    docs_root = Path(args.docs_root).resolve()
    if not docs_root.exists():
        parser.error(f"docs root not found: {docs_root}")

    if args.dry_run:
        # Run against a temporary copy in-memory by restoring original content.
        originals = {}
        for rel in ("STATUS_BOARD_CURRENT.md", "PLAN_NEXT_WEEK.md", "BACKLOG_NEXT_WEEK.md"):
            path = docs_root / rel
            originals[path] = path.read_text(encoding="utf-8")
        try:
            changed = apply_event(args.event, docs_root=docs_root, timestamp=args.timestamp)
        finally:
            for path, content in originals.items():
                path.write_text(content, encoding="utf-8")
        if changed:
            print("[DRY-RUN] Would update:")
            for path in changed:
                print(f"  - {path}")
        else:
            print("[DRY-RUN] No file changes required (already up to date).")
        return 0

    changed = apply_event(args.event, docs_root=docs_root, timestamp=args.timestamp)
    if changed:
        print("[PASS] Updated status docs from canonical event:")
        for path in changed:
            print(f"  - {path}")
    else:
        print("[PASS] Status docs already matched canonical event (no changes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
