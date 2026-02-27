"""CLI progress consumer for :class:`~autodev.progress.ProgressEmitter`.

Usage::

    from autodev.cli_progress import make_cli_progress_callback
    callback = make_cli_progress_callback()
    result = await run_autodev_enterprise(..., progress_callback=callback)

The callback prints an ANSI progress bar and phase/task status to *stderr*.
"""

from __future__ import annotations

import sys
from typing import Any, Callable, Dict, TextIO

# Bar characters
_BAR_FILL = "\u2593"  # ▓
_BAR_EMPTY = "\u2591"  # ░


def _format_bar(pct: float, width: int = 30) -> str:
    """Return a ``[▓▓▓░░░] 35.0%`` style progress bar string."""
    filled = int(pct / 100.0 * width)
    empty = width - filled
    return f"[{_BAR_FILL * filled}{_BAR_EMPTY * empty}] {pct:5.1f}%"


def _phase_label(phase: str | None) -> str:
    """Return a human-friendly phase label."""
    if not phase:
        return ""
    labels = {
        "prd_analysis": "Analyzing PRD",
        "architecture": "Architecture Design",
        "planning": "Planning",
        "implementation": "Implementing",
        "final_validation": "Final Validation",
    }
    return labels.get(phase, phase)


def make_cli_progress_callback(
    stream: TextIO = sys.stderr,
    color: bool = True,
) -> Callable[[Dict[str, Any]], None]:
    """Create a CLI callback that prints progress events.

    Parameters
    ----------
    stream:
        Output stream (default: *stderr*).
    color:
        Whether to use ANSI colour codes.

    Returns
    -------
    A callback suitable for :class:`~autodev.progress.ProgressEmitter`.
    """
    # ANSI codes
    _BOLD = "\033[1m" if color else ""
    _GREEN = "\033[32m" if color else ""
    _YELLOW = "\033[33m" if color else ""
    _RED = "\033[31m" if color else ""
    _CYAN = "\033[36m" if color else ""
    _RESET = "\033[0m" if color else ""
    _CR = "\r"

    def _callback(event: Dict[str, Any]) -> None:
        event_type = event.get("event", "")
        pct = event.get("progress_pct", 0.0)
        data = event.get("data", {})

        bar = _format_bar(pct)

        if event_type == "run.start":
            stream.write(f"\n{_BOLD}{_CYAN}AutoDev Pipeline Started{_RESET}\n")
            stream.flush()

        elif event_type == "run.end":
            ok = data.get("ok", False)
            status = f"{_GREEN}PASSED{_RESET}" if ok else f"{_RED}FAILED{_RESET}"
            stream.write(f"\n{bar} {_BOLD}{status}{_RESET}\n")
            stream.flush()

        elif event_type == "phase.start":
            label = _phase_label(data.get("phase"))
            stream.write(f"{_CR}{bar} {_YELLOW}{label}...{_RESET}  ")
            stream.flush()

        elif event_type == "phase.end":
            label = _phase_label(data.get("phase"))
            stream.write(f"{_CR}{bar} {_GREEN}{label} \u2713{_RESET}\n")
            stream.flush()

        elif event_type == "task.start":
            task_id = data.get("task_id", "")
            title = data.get("task_title", "")
            stream.write(
                f"{_CR}{bar} {_CYAN}Task {task_id}{_RESET}: {title}  "
            )
            stream.flush()

        elif event_type == "task.end":
            task_id = data.get("task_id", "")
            ok = data.get("ok", False)
            mark = f"{_GREEN}\u2713{_RESET}" if ok else f"{_RED}\u2717{_RESET}"
            stream.write(f"{_CR}{bar} Task {task_id} {mark}\n")
            stream.flush()

        elif event_type == "repair.start":
            task_id = data.get("task_id", "")
            attempt = data.get("attempt", 0)
            stream.write(
                f"{_CR}{bar} {_YELLOW}Repair {task_id} (attempt {attempt}){_RESET}  "
            )
            stream.flush()

        elif event_type == "validation.start":
            task_id = data.get("task_id", "")
            stream.write(
                f"{_CR}{bar} Validating {task_id}...  "
            )
            stream.flush()

        elif event_type == "validation.end":
            task_id = data.get("task_id", "")
            ok = data.get("ok", False)
            mark = f"{_GREEN}\u2713{_RESET}" if ok else f"{_RED}\u2717{_RESET}"
            stream.write(f"{_CR}{bar} Validation {task_id} {mark}\n")
            stream.flush()

    return _callback
