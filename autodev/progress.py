"""Real-time progress callback system for ``run_autodev_enterprise``.

The :class:`ProgressEmitter` wraps an optional synchronous callback and
provides a high-level API for emitting progress events.  If no callback is
provided (null-object pattern), all methods become no-ops.

Each emitted event is a plain dict with at least::

    {"event": str, "progress_pct": float, "phase": str | None, "data": dict}

``progress_pct`` is a monotonically increasing value between 0.0 and 100.0
calculated from fixed phase weights and task completion count.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set

# Phase weights sum to 1.0 and determine how progress_pct grows.
PHASE_WEIGHTS: Dict[str, float] = {
    "prd_analysis": 0.10,
    "architecture": 0.10,
    "planning": 0.10,
    "implementation": 0.60,
    "final_validation": 0.10,
}

# Ordered list matching the typical execution order.
PHASE_ORDER: List[str] = [
    "prd_analysis",
    "architecture",
    "planning",
    "implementation",
    "final_validation",
]


class ProgressEmitter:
    """Tracks pipeline progress and emits events via an optional callback.

    Parameters
    ----------
    callback:
        A synchronous ``callback(event_dict)`` invoked on every event.
        If *None*, the emitter acts as a silent no-op.
    total_tasks:
        Initial task count (can be updated via :meth:`set_total_tasks`).
    """

    def __init__(
        self,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        total_tasks: int = 0,
    ) -> None:
        self._callback = callback
        self._total_tasks = total_tasks
        self._completed_tasks = 0
        self._current_phase: Optional[str] = None
        self._phases_complete: Set[str] = set()
        self._last_pct: float = 0.0

    # -- configuration --------------------------------------------------------

    def set_total_tasks(self, n: int) -> None:
        """Update the total task count (known after planning)."""
        self._total_tasks = max(0, n)

    # -- progress calculation -------------------------------------------------

    def _progress_pct(self) -> float:
        """Return a monotonically increasing progress percentage [0..100]."""
        pct = 0.0

        # Add completed phase weights
        for phase_name in PHASE_ORDER:
            weight = PHASE_WEIGHTS.get(phase_name, 0.0)
            if phase_name in self._phases_complete:
                pct += weight * 100.0
            elif phase_name == self._current_phase:
                # In-progress phase: estimate sub-progress
                if phase_name == "implementation" and self._total_tasks > 0:
                    # Implementation sub-progress based on task completion
                    task_fraction = self._completed_tasks / self._total_tasks
                    pct += weight * 100.0 * task_fraction
                else:
                    # Non-implementation phases: give 50% credit for being in-progress
                    pct += weight * 100.0 * 0.5

        # Ensure monotonic increase
        pct = max(pct, self._last_pct)
        self._last_pct = pct
        return round(pct, 1)

    # -- core emit ------------------------------------------------------------

    def emit(self, event_type: str, **data: Any) -> None:
        """Emit an event to the callback if registered.

        Parameters
        ----------
        event_type:
            A dotted event name, e.g. ``"phase.start"`` or ``"task.end"``.
        **data:
            Arbitrary payload forwarded inside ``event["data"]``.
        """
        if self._callback is None:
            return

        event: Dict[str, Any] = {
            "event": event_type,
            "progress_pct": self._progress_pct(),
            "phase": self._current_phase,
            "data": data,
        }
        try:
            self._callback(event)
        except Exception:
            # Never let a faulty callback crash the pipeline.
            pass

    # -- high-level helpers ---------------------------------------------------

    def run_start(self, run_id: str) -> None:
        """Emit at the very beginning of a run."""
        self._last_pct = 0.0
        self.emit("run.start", run_id=run_id)

    def run_end(self, run_id: str, ok: bool) -> None:
        """Emit at the very end of a run."""
        self._last_pct = 100.0
        self.emit("run.end", run_id=run_id, ok=ok)

    def phase_start(self, phase_name: str) -> None:
        """Emit when a pipeline phase begins."""
        self._current_phase = phase_name
        self.emit("phase.start", phase=phase_name)

    def phase_end(self, phase_name: str) -> None:
        """Emit when a pipeline phase completes."""
        self._phases_complete.add(phase_name)
        self.emit("phase.end", phase=phase_name)
        if self._current_phase == phase_name:
            self._current_phase = None

    def task_start(self, task_id: str, task_title: str) -> None:
        """Emit when an individual task begins execution."""
        self.emit("task.start", task_id=task_id, task_title=task_title)

    def task_end(self, task_id: str, task_title: str, ok: bool) -> None:
        """Emit when an individual task finishes."""
        if ok:
            self._completed_tasks += 1
        self.emit("task.end", task_id=task_id, task_title=task_title, ok=ok)

    def validation_start(self, task_id: str, validators: List[str]) -> None:
        """Emit when validation begins for a task or final phase."""
        self.emit("validation.start", task_id=task_id, validators=validators)

    def validation_end(self, task_id: str, ok: bool) -> None:
        """Emit when validation finishes for a task or final phase."""
        self.emit("validation.end", task_id=task_id, ok=ok)

    def repair_start(self, task_id: str, attempt: int) -> None:
        """Emit when a repair/fix loop begins for a task."""
        self.emit("repair.start", task_id=task_id, attempt=attempt)
