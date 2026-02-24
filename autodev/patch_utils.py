from __future__ import annotations
import re
from dataclasses import dataclass
from typing import List

@dataclass
class Hunk:
    orig_start: int
    orig_len: int
    new_start: int
    new_len: int
    lines: List[str]  # includes leading ' ', '+', '-'

_HUNK_RE = re.compile(r'^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?(?:\s+@@)?$')


def _strip_diff_fence(diff_text: str) -> str:
    cleaned = diff_text.strip()
    if not cleaned.startswith("```"):
        return diff_text

    lines = cleaned.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def parse_unified_diff(diff_text: str) -> List[Hunk]:
    text = _strip_diff_fence(diff_text)
    lines = text.splitlines(keepends=True)
    hunks: List[Hunk] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('@@'):
            m = _HUNK_RE.match(line)
            if not m:
                raise ValueError(f'Invalid hunk header: {line!r}')
            ostart = int(m.group(1))
            olen = int(m.group(2) or '1')
            nstart = int(m.group(3))
            nlen = int(m.group(4) or '1')
            i += 1
            hlines: List[str] = []
            while i < len(lines):
                l = lines[i]
                if l.startswith('@@'):
                    break
                if l.startswith('diff --git') or l.startswith('index ') or l.startswith('---') or l.startswith('+++'):
                    i += 1
                    continue
                if l.startswith('\\ No newline at end of file'):
                    i += 1
                    continue
                if l[:1] in (' ', '+', '-'):
                    hlines.append(l)
                else:
                    # allow empty? treat as context line with no prefix is invalid
                    raise ValueError(f'Invalid diff line (missing prefix): {l!r}')
                i += 1
            hunks.append(Hunk(ostart, olen, nstart, nlen, hlines))
            continue
        i += 1
    if not hunks:
        raise ValueError('No hunks found in diff')
    return hunks


def validate_unified_diff(diff_text: str) -> None:
    parse_unified_diff(diff_text)


def apply_unified_diff(original: str, diff_text: str) -> str:
    text = _strip_diff_fence(diff_text)

    try:
        hunks = parse_unified_diff(text)
    except ValueError as e:
        if str(e) == 'No hunks found in diff':
            # fallback: treat as full rewrite
            return text
        raise e

    orig_lines = original.splitlines(keepends=True)
    out: List[str] = []
    orig_idx = 0  # 0-based index into orig_lines

    for h in hunks:
        target_idx = max(h.orig_start - 1, 0)
        if target_idx < orig_idx:
            # overlapping hunks or wrong indices
            raise ValueError('Hunk target before current index (overlap?)')

        # copy unchanged part
        out.extend(orig_lines[orig_idx:target_idx])
        orig_idx = target_idx

        for dl in h.lines:
            prefix = dl[:1]
            text_line = dl[1:]
            if prefix == ' ':
                # context must match
                if orig_idx >= len(orig_lines):
                    raise ValueError('Context beyond EOF')
                if orig_lines[orig_idx] != text_line:
                    raise ValueError('Context mismatch')
                out.append(text_line)
                orig_idx += 1
            elif prefix == '-':
                if orig_idx >= len(orig_lines):
                    raise ValueError('Delete beyond EOF')
                if orig_lines[orig_idx] != text_line:
                    raise ValueError('Delete mismatch')
                orig_idx += 1
            elif prefix == '+':
                out.append(text_line)
            else:
                raise ValueError(f'Unknown prefix: {prefix!r}')

    out.extend(orig_lines[orig_idx:])
    return ''.join(out)
