from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for name in list(sys.modules):
    if name == "autodev" or name.startswith("autodev."):
        sys.modules.pop(name, None)

import autodev.browser_automation as browser_automation  # noqa: E402


def test_safari_automation_availability_handles_missing_osascript(monkeypatch) -> None:
    monkeypatch.setattr(browser_automation.shutil, "which", lambda name: None)
    payload = browser_automation.safari_automation_availability()
    assert payload["available"] is False
    assert payload["reason"] == "osascript_not_found"


def test_run_safari_gui_smoke_skips_when_unavailable(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        browser_automation,
        "safari_automation_availability",
        lambda: {"available": False, "reason": "safari_not_available"},
    )
    payload = browser_automation.run_safari_gui_smoke(base_url="http://127.0.0.1:8787", artifact_dir=tmp_path)
    assert payload["status"] == "skipped"
    assert payload["reason"] == "safari_not_available"


def test_run_safari_gui_smoke_returns_page_payload_on_success(monkeypatch, tmp_path: Path) -> None:
    class _Proc:
        def __init__(self, *, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    commands: list[list[str]] = []

    def _fake_run_command(args: list[str], *, timeout: float = 10.0):  # noqa: ARG001
        commands.append(args)
        if args and args[0] == "/usr/bin/screencapture":
            screenshot = tmp_path / "browser-safari.png"
            screenshot.write_bytes(b"fake")
            return _Proc(returncode=0, stdout="", stderr="")
        return _Proc(
            returncode=0,
            stdout='{"readyState":"complete","selectors":{"#trustCards":true},"activeTab":"compare","title":"AutoDev GUI MVP"}',
            stderr="",
        )

    monkeypatch.setattr(
        browser_automation,
        "safari_automation_availability",
        lambda: {"available": True, "osascript_path": "/usr/bin/osascript"},
    )
    monkeypatch.setattr(browser_automation, "_run_command", _fake_run_command)
    monkeypatch.setattr(browser_automation.shutil, "which", lambda name: "/usr/bin/screencapture" if name == "screencapture" else "/usr/bin/osascript")

    payload = browser_automation.run_safari_gui_smoke(
        base_url="http://127.0.0.1:8787",
        artifact_dir=tmp_path,
        selectors=["#trustCards"],
    )
    assert payload["status"] == "passed"
    assert payload["page"]["readyState"] == "complete"
    assert payload["page"]["selectors"]["#trustCards"] is True
    assert payload["screenshot_path"].endswith("browser-safari.png")
    assert any(cmd[0] == "/usr/bin/osascript" for cmd in commands)


def test_run_safari_gui_smoke_skips_when_safari_js_automation_is_disabled(monkeypatch, tmp_path: Path) -> None:
    class _Proc:
        def __init__(self, *, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    monkeypatch.setattr(
        browser_automation,
        "safari_automation_availability",
        lambda: {"available": True, "osascript_path": "/usr/bin/osascript"},
    )
    monkeypatch.setattr(
        browser_automation,
        "_run_command",
        lambda args, *, timeout=10.0: _Proc(  # noqa: ARG005
            returncode=1,
            stderr="You must enable 'Allow JavaScript from Apple Events' in the Developer section of Safari Settings to use 'do JavaScript'.",
        ),
    )

    payload = browser_automation.run_safari_gui_smoke(
        base_url="http://127.0.0.1:8787",
        artifact_dir=tmp_path,
    )
    assert payload["status"] == "skipped"
    assert payload["reason"] == "javascript_from_apple_events_disabled"
