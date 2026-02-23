from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any
from .exec_kernel import ExecKernel, CmdResult
from .env_manager import EnvManager

@dataclass
class Validation:
    name: str
    ok: bool
    result: CmdResult
    note: str = ""

class Validators:
    def __init__(self, kernel: ExecKernel, env: EnvManager):
        self.k = kernel
        self.env = env

    def run_all(self, enabled: List[str], audit_required: bool = False) -> List[Validation]:
        return [self.run_one(v, audit_required=audit_required) for v in enabled]

    def run_one(self, name: str, audit_required: bool = False) -> Validation:
        py = self.env.venv_python()
        note = ""
        if name == "ruff":
            r = self.k.run(self.k.module_cmd(py, "ruff", "check", "."))
        elif name == "mypy":
            r = self.k.run(self.k.module_cmd(py, "mypy", "src"))
        elif name == "pytest":
            r = self.k.run(self.k.module_cmd(py, "pytest", "-q"))
        elif name == "pip_audit":
            r = self.k.run(self.k.module_cmd(py, "pip_audit", "-r", "requirements.txt"))
            if r.returncode != 0 and not audit_required:
                note = "pip-audit failed (possibly offline). WARN because audit_required=false."
        elif name == "bandit":
            r = self.k.run(self.k.module_cmd(py, "bandit", "-q", "-r", "src"))
        elif name == "semgrep":
            # local rules only; fail if findings
            import os
            semgrep_bin = os.path.join(os.path.dirname(py), "semgrep")
            if os.name == "nt":
                semgrep_bin += ".exe"
            r = self.k.run([semgrep_bin, "--config", ".semgrep.yml", "--error"])
        elif name == "sbom":
            r = self.k.run(self.k.script_cmd(py, "scripts/generate_sbom.py"))
        elif name == "docker_build":
            r = self.k.run(["docker", "build", "-t", "autodev-app:test", "."])
        else:
            raise ValueError(f"Unknown validator: {name}")

        ok = (r.returncode == 0)
        if name == "pip_audit" and (r.returncode != 0) and (not audit_required):
            ok = True
        return Validation(name=name, ok=ok, result=r, note=note)

    @staticmethod
    def serialize(results: List[Validation]) -> List[Dict[str, Any]]:
        return [
            {
                "name": v.name,
                "ok": v.ok,
                "cmd": v.result.cmd,
                "returncode": v.result.returncode,
                "stdout": v.result.stdout[-6000:],
                "stderr": v.result.stderr[-6000:],
                "note": v.note,
            }
            for v in results
        ]
