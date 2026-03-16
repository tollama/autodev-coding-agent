from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


SAFARI_APP_NAME = "Safari"
APPLE_EVENTS_JS_DISABLED = "allow javascript from apple events"
BROWSER_AUTOMATION_JSON = ".autodev/browser_automation.json"


def _run_command(args: list[str], *, timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def safari_automation_availability() -> dict[str, Any]:
    osascript_path = shutil.which("osascript")
    if not osascript_path:
        return {"available": False, "reason": "osascript_not_found"}

    probe = _run_command(
        [
            osascript_path,
            "-e",
            'try',
            "-e",
            f'id of application "{SAFARI_APP_NAME}"',
            "-e",
            'on error errMsg',
            "-e",
            'return "ERROR:" & errMsg',
            "-e",
            'end try',
        ],
        timeout=5.0,
    )
    output = (probe.stdout or probe.stderr or "").strip()
    if probe.returncode != 0 or output.startswith("ERROR:"):
        return {
            "available": False,
            "reason": "safari_not_available",
            "detail": output or f"returncode={probe.returncode}",
        }

    return {"available": True, "reason": "", "osascript_path": osascript_path}


def _applescript_lines(base_url: str, selectors: list[str]) -> list[str]:
    escaped_url = base_url.replace('"', '\\"')
    selector_checks = []
    for selector in selectors:
        escaped_selector = selector.replace("\\", "\\\\").replace('"', '\\"')
        selector_checks.append(
            f'"{escaped_selector}": !!document.querySelector("{escaped_selector}")'
        )
    checks_js = "{ " + ", ".join(selector_checks) + " }"
    result_js = (
        'JSON.stringify({'
        'readyState: document.readyState, '
        f'selectors: {checks_js}, '
        'activeTab: (document.querySelector(".tab.is-active") || {}).dataset ? (document.querySelector(".tab.is-active") || {}).dataset.tab : "", '
        'title: document.title || "", '
        'trustCardsVisible: !!document.getElementById("trustCards"), '
        'comparePanelVisible: !!document.getElementById("compareTrustPanel")'
        '})'
    )
    click_js = 'document.querySelector(".tab[data-tab=\\"compare\\"]") && document.querySelector(".tab[data-tab=\\"compare\\"]").click();'
    return [
        f'tell application "{SAFARI_APP_NAME}"',
        "activate",
        f'open location "{escaped_url}"',
        "delay 2",
        'tell front window',
        'set smokeTab to current tab',
        f"do JavaScript {json.dumps(click_js)} in smokeTab",
        "delay 1",
        f"set smokeResult to do JavaScript {json.dumps(result_js)} in smokeTab",
        "end tell",
        "return smokeResult",
        "end tell",
    ]


def run_safari_gui_smoke(
    *,
    base_url: str,
    artifact_dir: str | Path,
    selectors: list[str] | None = None,
    require_available: bool = False,
) -> dict[str, Any]:
    selectors = selectors or [
        "#trustCards",
        "#trustTrendCards",
        "#compareTrustPanel",
        "#compareSavedPanel",
        "#apiNoticeSummary",
    ]
    artifact_root = Path(artifact_dir).expanduser().resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)

    availability = safari_automation_availability()
    if not availability.get("available"):
        result = {
            "status": "skipped",
            "reason": availability.get("reason") or "browser_automation_unavailable",
            "detail": availability.get("detail") or "",
        }
        if require_available:
            result["status"] = "failed"
        return result

    script_lines = _applescript_lines(base_url, selectors)
    command = [str(availability["osascript_path"])]
    for line in script_lines:
        command.extend(["-e", line])

    started_at = time.time()
    proc = _run_command(command, timeout=20.0)
    elapsed_ms = int((time.time() - started_at) * 1000)
    raw_output = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    result: dict[str, Any] = {
        "status": "failed" if proc.returncode != 0 else "passed",
        "elapsed_ms": elapsed_ms,
        "returncode": proc.returncode,
        "stderr": stderr,
        "script_lines": script_lines,
    }
    if proc.returncode != 0 and APPLE_EVENTS_JS_DISABLED in stderr.lower():
        result["status"] = "failed" if require_available else "skipped"
        result["reason"] = "javascript_from_apple_events_disabled"
    if raw_output:
        try:
            result["page"] = json.loads(raw_output)
        except json.JSONDecodeError:
            result["raw_output"] = raw_output

    screenshot_path = artifact_root / "browser-safari.png"
    screencapture = shutil.which("screencapture")
    if proc.returncode == 0 and screencapture:
        shot = _run_command([screencapture, "-x", str(screenshot_path)], timeout=5.0)
        if shot.returncode == 0 and screenshot_path.exists():
            result["screenshot_path"] = str(screenshot_path)

    if require_available and result["status"] != "passed":
        result["required"] = True
    return result


def persist_browser_automation_result(run_dir: str | Path, payload: dict[str, Any]) -> str:
    target = Path(run_dir).expanduser().resolve() / BROWSER_AUTOMATION_JSON
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(target)


def load_browser_automation_result(run_dir: str | Path) -> dict[str, Any]:
    target = Path(run_dir).expanduser().resolve() / BROWSER_AUTOMATION_JSON
    if not target.exists() or not target.is_file():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
