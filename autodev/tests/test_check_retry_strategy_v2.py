from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent.parent.parent


def _run_checker(*, schema: Path | None = None, example: Path | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "scripts/check_retry_strategy_v2.py"]
    if schema is not None:
        cmd.extend(["--schema", str(schema)])
    if example is not None:
        cmd.extend(["--example", str(example)])
    return subprocess.run(  # noqa: S603
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_retry_strategy_v2_passes_for_repo_contract() -> None:
    proc = _run_checker()

    assert proc.returncode == 0, proc.stdout + "\n" + proc.stderr
    assert "[PASS] retry strategy v2 schema/example validation passed" in proc.stdout


def test_check_retry_strategy_v2_fails_on_mismatched_expected_decision(tmp_path: Path) -> None:
    bad = tmp_path / "bad_retry_example.json"
    bad.write_text(
        """
{
  "policy_id": "autonomous.retry-strategy.v2",
  "version": "v1",
  "retry_classes": [
    {"name": "retryable", "retry_budget": 3, "stop_after_failures": 3, "escalate_after_no_progress": 4, "hard_stop_on_non_retryable_failure": true},
    {"name": "conditional", "retry_budget": 2, "stop_after_failures": 2, "escalate_after_no_progress": 2, "hard_stop_on_non_retryable_failure": true},
    {"name": "non_retryable", "retry_budget": 0, "stop_after_failures": 1, "escalate_after_no_progress": 1, "hard_stop_on_non_retryable_failure": true}
  ],
  "deterministic_examples": [
    {
      "id": "BAD-1",
      "stage": "ingest",
      "retry_class": "retryable",
      "replay_attempt": 1,
      "consecutive_failures": 0,
      "no_progress_streak": 0,
      "non_retryable_failure": false,
      "expected_decision": "stop",
      "expected_reason_code": "retry_policy.retryable_within_budget"
    }
  ]
}
        """.strip(),
        encoding="utf-8",
    )

    proc = _run_checker(example=bad)

    assert proc.returncode == 1
    assert "deterministic mismatch" in proc.stdout
