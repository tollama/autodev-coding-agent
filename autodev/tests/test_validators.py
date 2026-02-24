import pytest

from autodev.validators import Validators
from autodev.exec_kernel import ExecKernel, CmdResult


class _FakeKernel:
    def __init__(self, command_results=None):
        self.command_results = dict(command_results or {})

    def run(self, cmd):
        cmd_key = tuple(cmd)
        if cmd_key in self.command_results:
            code = self.command_results[cmd_key]
        elif "pip_audit" in cmd:
            code = self.command_results.get("pip_audit", 0)
        elif "ruff" in cmd:
            code = self.command_results.get("ruff", 0)
        elif "semgrep" in cmd:
            code = self.command_results.get("semgrep", 0)
        else:
            code = 0
        return CmdResult(cmd=cmd, returncode=code, stdout="", stderr="")

    def module_cmd(self, python_executable, module, *args):
        return [python_executable, "-I", "-m", module, *args]

    def script_cmd(self, python_executable, script_rel_path, *args):
        return [python_executable, "-I", script_rel_path, *args]


class _FakeEnvManager:
    def __init__(self, kernel: _FakeKernel):
        self._kernel = kernel

    def venv_python(self) -> str:
        return "/fake/python"


def test_validator_soft_and_hard_classification_and_serialize_fields():
    kernel = _FakeKernel({"pip_audit": 1, "semgrep": 1})
    validators = Validators(kernel=kernel, env=_FakeEnvManager(kernel))
    results = validators.run_all(["pip_audit", "ruff"], audit_required=False, soft_validators={"pip_audit"}, phase="per_task")

    payload = Validators.serialize(results)
    assert payload[0]["name"] == "ruff"
    assert payload[1]["name"] == "pip_audit"
    assert payload[1]["status"] == "soft_fail"
    assert "status" in payload[1]
    assert "tool_version" in payload[0]
    assert "duration_ms" in payload[0]

    hard = validators.run_all(["semgrep"], audit_required=True, soft_validators=set(), phase="final")
    hard_payload = Validators.serialize(hard)
    assert hard_payload[0]["status"] in {"passed", "failed", "soft_fail"}
    assert hard_payload[0]["phase"] == "final"


def test_exec_kernel_rejects_unsupported_command_shapes():
    kernel = ExecKernel(cwd=".", timeout_sec=10)

    with pytest.raises(RuntimeError):
        kernel.run(["python", "-c", "print('x')"])

    with pytest.raises(RuntimeError):
        kernel.run(["semgrep", "--config", "other.yml"])

    with pytest.raises(RuntimeError):
        kernel.run(["python", "-I", "-m", "semgrep", "scan", "--config", ".semgrep.yml", "--error"])


def test_semgrep_variants_allowed_with_strict_shape():
    kernel = ExecKernel(cwd=".", timeout_sec=10)

    assert kernel._allowed(["semgrep", "--config", ".semgrep.yml", "--error"]) is True
    assert kernel._allowed(["python", "-I", "-m", "semgrep", "--config", ".semgrep.yml", "--error"]) is True


def test_run_all_preserves_phase_and_soft_split():
    fake_kernel = _FakeKernel()
    validators = Validators(kernel=fake_kernel, env=_FakeEnvManager(fake_kernel))
    results = validators.run_all(["ruff", "pip_audit", "semgrep"], soft_validators={"pip_audit"}, phase="per_task")
    payload = Validators.serialize(results)

    assert payload[0]["phase"] == "per_task"
    assert payload[1]["name"] == "pip_audit"
    assert payload[1]["phase"] == "per_task"
