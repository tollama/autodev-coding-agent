from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from .exec_kernel import ExecKernel, CmdResult
from .env_manager import EnvManager


@dataclass
class Validation:
    name: str
    ok: bool
    result: CmdResult
    note: str = ""
    status: str = "done"
    duration_ms: int = 0
    tool_version: str = "unknown"
    error_classification: Optional[str] = None
    phase: str = "task"


class Validators:
    def __init__(self, kernel: ExecKernel, env: EnvManager):
        self.k = kernel
        self.env = env
        self._version_cache: Dict[str, str] = {}

    @staticmethod
    def _parse_error_class(name: str, returncode: int, audit_required: bool, r: CmdResult) -> tuple[str, Optional[str]]:
        if returncode == 0:
            return "passed", None

        if name == "pip_audit" and not audit_required:
            return "soft_fail", "warning_offline_or_vulnerable"

        if name == "semgrep":
            return "failed", "policy_violation"

        return "failed", "tool_error"

    def _run(self, name: str, command: List[str], audit_required: bool = False, phase: str = "task") -> Validation:
        start = time.perf_counter()
        result = self.k.run(command)
        duration_ms = int((time.perf_counter() - start) * 1000)

        status, error_class = self._parse_error_class(name, result.returncode, audit_required, result)
        ok = status == "passed"
        note = ""
        if name == "pip_audit" and (result.returncode != 0) and (not audit_required):
            note = "pip-audit failed (possibly offline). WARN because audit_required=false."

        return Validation(
            name=name,
            ok=ok,
            result=result,
            note=note,
            status=status,
            duration_ms=duration_ms,
            tool_version=self._version(name),
            error_classification=error_class,
            phase=phase,
        )

    @staticmethod
    def _extract_version(output: str) -> str:
        if not output:
            return "unknown"
        m = re.search(r"\d+\.\d+(?:\.\d+)?", output)
        return m.group(0) if m else "unknown"

    def _version(self, validator: str) -> str:
        if validator in self._version_cache:
            return self._version_cache[validator]

        probe = {
            "ruff": ["ruff", "--version"],
            "mypy": ["mypy", "--version"],
            "pytest": ["pytest", "--version"],
            "pip_audit": ["pip_audit", "--version"],
            "bandit": ["bandit", "--version"],
            "semgrep": ["semgrep", "--version"],
            "sbom": ["python", "--version"],
            "docker_build": ["docker", "version"],
        }.get(validator)
        if not probe:
            self._version_cache[validator] = "unknown"
            return "unknown"

        try:
            r = self.k.run(probe)
            text = f"{r.stdout}\n{r.stderr}".strip()
            self._version_cache[validator] = self._extract_version(text)
        except Exception:
            self._version_cache[validator] = "unknown"
        return self._version_cache[validator]

    def _split_soft(self, validators_enabled: List[str], soft_validators: Set[str] | None = None) -> tuple[List[str], List[str]]:
        soft_set = set(soft_validators or [])
        hard: List[str] = []
        soft: List[str] = []
        for v in validators_enabled:
            if v in soft_set:
                soft.append(v)
            else:
                hard.append(v)

        return hard, soft

    def run_all(
        self,
        enabled: List[str],
        audit_required: bool = False,
        soft_validators: Set[str] | None = None,
        phase: str = "task",
    ) -> List[Validation]:
        out: List[Validation] = []

        hard, soft = self._split_soft(enabled, soft_validators=soft_validators)
        for name in hard + soft:
            out.append(self.run_one(name, audit_required=audit_required, phase=phase))

        return out

    def run_one(
        self,
        name: str,
        audit_required: bool = False,
        phase: str = "task",
    ) -> Validation:
        py = self.env.venv_python()

        if name == "ruff":
            return self._run(
                name,
                self.k.module_cmd(py, "ruff", "check", "src", "tests", "--select", "E,F,I,B,UP,SIM,S,ASYNC,PERF", "--line-length", "100"),
                audit_required=audit_required,
                phase=phase,
            )
        if name == "mypy":
            return self._run(
                name,
                self.k.module_cmd(py, "mypy", "--hide-error-context", "--show-error-codes", "--pretty", "--install-types", "--non-interactive", "src"),
                audit_required=audit_required,
                phase=phase,
            )
        if name == "pytest":
            return self._run(name, self.k.module_cmd(py, "pytest", "-q", "--maxfail", "1", "tests"), audit_required=audit_required, phase=phase)
        if name == "pip_audit":
            return self._run(name, self.k.module_cmd(py, "pip_audit", "-r", "requirements.txt", "--format", "json"), audit_required=audit_required, phase=phase)
        if name == "bandit":
            return self._run(name, self.k.module_cmd(py, "bandit", "-q", "-r", "src"), audit_required=audit_required, phase=phase)
        if name == "semgrep":
            return self._run(name, ["semgrep", "--config", ".semgrep.yml", "--error"], audit_required=audit_required, phase=phase)
        if name == "sbom":
            return self._run(name, self.k.script_cmd(py, "scripts/generate_sbom.py"), audit_required=audit_required, phase=phase)
        if name == "docker_build":
            return self._run(name, ["docker", "build", "--pull", "-t", "autodev-app:test", "."], audit_required=audit_required, phase=phase)

        raise ValueError(f"Unknown validator: {name}")

    @staticmethod
    def serialize(results: List[Validation]) -> List[Dict[str, object]]:
        return [
            {
                "name": result.name,
                "ok": result.ok,
                "status": result.status,
                "phase": result.phase,
                "cmd": result.result.cmd,
                "returncode": result.result.returncode,
                "duration_ms": result.duration_ms,
                "tool_version": result.tool_version,
                "error_classification": result.error_classification,
                "stdout": result.result.stdout[-6000:],
                "stderr": result.result.stderr[-6000:],
                "note": result.note,
            }
            for result in results
        ]
