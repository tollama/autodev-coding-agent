import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.cli import build_parser, main

def test_cli_runs(capsys):
    rc = main(["--hello", "agent"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out == "hello agent"

def test_cli_contract():
    contract = json.loads(Path("contracts/cli_contract.json").read_text(encoding="utf-8"))
    p = build_parser()
    flags = {a.option_strings[0] for a in p._actions if a.option_strings}
    for a in contract.get("args", []):
        assert a["flag"] in flags, f"Missing CLI flag in parser: {a['flag']}"
