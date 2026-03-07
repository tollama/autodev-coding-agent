from __future__ import annotations

import json
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_module(script_name: str):
    script_path = Path(__file__).resolve().parents[2] / "scripts" / script_name
    spec = spec_from_file_location(script_name.replace(".py", ""), script_path)
    assert spec and spec.loader
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_scorecard_includes_latest_compare_and_trends(tmp_path: Path) -> None:
    fixtures_mod = _load_module("showoff_seed_fixtures.py")
    scorecard_mod = _load_module("demo_scorecard.py")

    runs_root = fixtures_mod.generate(tmp_path / "generated_runs", clean=True)
    scorecard = scorecard_mod.build_scorecard(runs_root, latest=3)

    assert scorecard["latest"] is not None
    latest = scorecard["latest"]
    assert latest["run_id"] == "showoff_running_001"
    assert latest["status"] == "running"

    compare = scorecard["compare_delta"]
    assert compare is not None
    assert compare["from_run_id"] == "showoff_failed_001"
    assert compare["to_run_id"] == "showoff_running_001"
    assert compare["totals"]["hard_failures"] == 0

    trends = scorecard["trends"]
    assert trends["run_count"] == 3
    assert trends["status_counts"]["ok"] == 1
    assert trends["status_counts"]["failed"] == 1
    assert trends["status_counts"]["running"] == 1


def test_main_writes_markdown_and_json_artifacts(tmp_path: Path, monkeypatch) -> None:
    fixtures_mod = _load_module("showoff_seed_fixtures.py")
    scorecard_mod = _load_module("demo_scorecard.py")

    runs_root = fixtures_mod.generate(tmp_path / "generated_runs", clean=True)
    out_dir = tmp_path / "artifacts" / "demo-day"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "demo_scorecard.py",
            "--runs-root",
            str(runs_root),
            "--output-dir",
            str(out_dir),
            "--latest",
            "2",
        ],
    )
    scorecard_mod.main()

    json_path = out_dir / "demo_scorecard_latest.json"
    md_path = out_dir / "demo_scorecard_latest.md"

    assert json_path.is_file()
    assert md_path.is_file()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["latest"]["run_id"] == "showoff_running_001"
    assert "Demo Day Scorecard" in md_path.read_text(encoding="utf-8")
