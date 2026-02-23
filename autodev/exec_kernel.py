from __future__ import annotations
import os
import subprocess
from dataclasses import dataclass
from typing import List

@dataclass
class CmdResult:
    cmd: List[str]
    returncode: int
    stdout: str
    stderr: str

class ExecKernel:
    """Safe command runner. No shell=True. Enforces allowlist."""

    ALLOWED_PY_MODULES = {"pytest", "ruff", "mypy", "pip_audit", "bandit", "pip", "venv"}
    ALLOWED_PY_SCRIPTS = {"scripts/generate_sbom.py"}  # relative paths

    def __init__(self, cwd: str, timeout_sec: int = 1200):
        self.cwd = cwd
        self.timeout = timeout_sec

    def _is_python(self, exe: str) -> bool:
        b = os.path.basename(exe).lower()
        return b.startswith("python")

    def module_cmd(self, python_executable: str, module: str, *args: str) -> List[str]:
        return [python_executable, "-I", "-m", module, *args]

    def script_cmd(self, python_executable: str, script_rel_path: str, *args: str) -> List[str]:
        return [python_executable, "-I", script_rel_path, *args]

    @staticmethod
    def _normalize_relpath(path: str) -> str:
        return path.replace("\\", "/").lstrip("./")

    def _allowed(self, cmd: List[str]) -> bool:
        if not cmd:
            return False

        if cmd[0] == "docker":
            return len(cmd) >= 2 and cmd[1] in {"version", "build"}

        if cmd[0] == "semgrep":
            # allow local semgrep with local config only
            return cmd == ["semgrep", "--config", ".semgrep.yml", "--error"]

        if not self._is_python(cmd[0]):
            return False
        if len(cmd) >= 4 and cmd[1] == "-I" and cmd[2] == "-m":
            mod = cmd[3]
            args = cmd[4:]
            if mod not in self.ALLOWED_PY_MODULES:
                return False
            if mod == "pip":
                return args in [
                    ["install", "-U", "pip"],
                    ["install", "-r", "requirements.txt"],
                    ["install", "--no-cache-dir", "-r", "requirements.txt"],
                ]
            if mod == "venv":
                return args == [".venv"]
            return True
        if len(cmd) >= 3 and cmd[1] == "-I":
            rel = self._normalize_relpath(cmd[2])
            return rel in self.ALLOWED_PY_SCRIPTS and len(cmd) == 3
        return False

    def run(self, cmd: List[str]) -> CmdResult:
        if not self._allowed(cmd):
            raise RuntimeError(f"Command not allowed: {cmd}")
        p = subprocess.run(
            cmd,
            cwd=self.cwd,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
        )
        return CmdResult(cmd=cmd, returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
