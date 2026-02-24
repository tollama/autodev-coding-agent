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

    ALLOWED_PY_MODULES = {
        "ruff",
        "mypy",
        "pip_audit",
        "bandit",
        "pytest",
        "pip",
        "venv",
        "semgrep",
    }
    ALLOWED_PY_SCRIPTS = {"scripts/generate_sbom.py"}
    ALLOWED_DOCKER_CMDS = {"version", "build"}

    def __init__(self, cwd: str, timeout_sec: int = 1200):
        self.cwd = cwd
        self.timeout = timeout_sec
        self._reject_reason: str | None = None

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

    def _normalize_cmd(self, cmd: List[str]) -> List[str]:
        return [str(c) for c in cmd]

    @staticmethod
    def _looks_like_semgrep(cmd: List[str]) -> bool:
        base = os.path.basename(cmd[0]).lower()
        if base in {"semgrep", "semgrep.exe"}:
            return True
        if base in {"python", "python.exe", "python3", "python3.exe"} and len(cmd) >= 4:
            return cmd[1:4] == ["-I", "-m", "semgrep"]
        return False

    def _allowed(self, cmd: List[str]) -> bool:
        self._reject_reason = None
        if not cmd:
            self._reject_reason = "empty command"
            return False

        normalized = self._normalize_cmd(cmd)

        if normalized[0] == "docker":
            if len(normalized) >= 2 and normalized[1] in self.ALLOWED_DOCKER_CMDS:
                return True
            self._reject_reason = f"docker command not permitted: {normalized}"
            return False

        if self._looks_like_semgrep(normalized):
            # Support direct binary call or `python -I -m semgrep`.
            if normalized[0] in {"semgrep", "semgrep.exe"}:
                semgrep_args = normalized[1:]
            else:
                if len(normalized) < 4 or normalized[1:4] != ["-I", "-m", "semgrep"]:
                    self._reject_reason = f"unsupported semgrep invocation: {normalized}"
                    return False
                semgrep_args = normalized[4:]

            if semgrep_args == ["--version"]:
                return True

            if "--config" not in semgrep_args or "--error" not in semgrep_args:
                self._reject_reason = f"semgrep command missing required flags: {normalized}"
                return False

            cfg_candidates = [idx for idx, v in enumerate(semgrep_args) if v == "--config"]
            if not cfg_candidates:
                self._reject_reason = f"semgrep command missing --config: {normalized}"
                return False

            cfg_index = cfg_candidates[0]
            cfg_path = semgrep_args[cfg_index + 1] if cfg_index + 1 < len(semgrep_args) else ""
            if cfg_path != ".semgrep.yml":
                self._reject_reason = f"semgrep command must use .semgrep.yml config: {normalized}"
                return False

            for i, arg in enumerate(semgrep_args):
                if arg.startswith("-"):
                    continue
                if i == cfg_index + 1:
                    continue
                self._reject_reason = f"semgrep invocation has unsupported positional argument: {arg}"
                return False

            if not semgrep_args:
                self._reject_reason = f"semgrep command malformed: {normalized}"
                return False

            return True

        if not self._is_python(normalized[0]):
            self._reject_reason = f"non-python command blocked: {normalized[0]}"
            return False
        if len(normalized) < 4 or normalized[1] != "-I":
            self._reject_reason = f"python command must include -I isolation flag: {normalized}"
            return False

        if normalized[2] == "-m":
            if len(normalized) < 4:
                self._reject_reason = f"python module invocation missing module name: {normalized}"
                return False
            mod = normalized[3]
            args = normalized[4:]
            if mod not in self.ALLOWED_PY_MODULES:
                self._reject_reason = f"python module blocked: {mod}"
                return False
            if mod == "pip":
                allowed = {
                    ("install", "-U", "pip"),
                    ("install", "-r", "requirements.txt"),
                    ("install", "--no-cache-dir", "-r", "requirements.txt"),
                    ("install", "-r", "requirements-dev.txt"),
                    ("install", "--no-cache-dir", "-r", "requirements-dev.txt"),
                }
                if tuple(args) not in allowed:
                    self._reject_reason = f"unsupported pip arguments: {args}"
                    return False
                return True
            if mod == "venv":
                return args == [".venv"]
            if mod == "semgrep":
                if "--version" in args and len(args) == 1:
                    return True
                self._reject_reason = f"unsupported python -m semgrep invocation: {normalized}"
                return False
            return True

        if len(normalized) >= 3 and normalized[2] not in {".", "./"}:
            rel = self._normalize_relpath(normalized[2])
            if rel not in self.ALLOWED_PY_SCRIPTS:
                self._reject_reason = f"script path blocked: {normalized[2]}"
                return False
            if len(normalized) != 3:
                self._reject_reason = f"script invocation must include only script path: {normalized}"
                return False
            return True

        self._reject_reason = f"unsupported command shape: {' '.join(normalized)}"
        return False

    def run(self, cmd: List[str]) -> CmdResult:
        if not self._allowed(cmd):
            reason = self._reject_reason or "unknown"
            raise RuntimeError(f"Command not allowed: {cmd}. reason={reason}")
        try:
            p = subprocess.run(
                cmd,
                cwd=self.cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
            return CmdResult(cmd=cmd, returncode=p.returncode, stdout=p.stdout, stderr=p.stderr)
        except Exception as e:
            return CmdResult(cmd=cmd, returncode=127, stdout="", stderr=str(e))
