from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class CmdResult:
    cmd: list[str]
    returncode: int
    stdout: str
    stderr: str


class ExecKernel:
    """
    Security: allowlist only. No shell=True. No arbitrary commands.
    """

    ALLOWED_PY_MODULES = {"pytest", "ruff", "mypy", "pip_audit", "bandit"}
    ALLOWLIST_PREFIXES = [
        ["docker", "build"],
        ["docker", "version"],
    ]

    def __init__(self, cwd: str, timeout_sec: int = 600):
        self.cwd = cwd
        self.timeout = timeout_sec
        self.python_executable = shutil.which("python") or shutil.which("python3") or sys.executable

    def _allowed(self, cmd: list[str]) -> bool:
        if len(cmd) >= 3 and cmd[1] == "-m":
            exe = os.path.basename(cmd[0])
            if exe.startswith("python") and cmd[2] in self.ALLOWED_PY_MODULES:
                return True
        for prefix in self.ALLOWLIST_PREFIXES:
            if cmd[: len(prefix)] == prefix:
                return True
        return False

    def module_cmd(self, module: str, *args: str) -> list[str]:
        if module not in self.ALLOWED_PY_MODULES:
            raise ValueError(f"Module not allowlisted: {module}")
        return [self.python_executable, "-m", module, *args]

    def run(self, cmd: list[str]) -> CmdResult:
        if not self._allowed(cmd):
            raise RuntimeError(f"Command not allowed: {cmd}")
        proc = subprocess.run(
            cmd,
            cwd=self.cwd,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
        )
        return CmdResult(
            cmd=cmd,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
