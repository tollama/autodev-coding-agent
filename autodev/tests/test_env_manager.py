import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # noqa: E402

from autodev.env_manager import EnvManager  # noqa: E402
from autodev.exec_kernel import ExecKernel, CmdResult  # noqa: E402


class FakeKernel(ExecKernel):
    def __init__(self, results):
        super().__init__(cwd=os.getcwd())
        self.results = list(results)
        self.commands: list[object] = []

    def module_cmd(self, python_executable: str, module: str, *args: str) -> list[str]:
        return [python_executable, "-I", "-m", module, *args]

    def run(self, cmd: list[str]):
        self.commands.append(cmd)
        if not self.results:
            return CmdResult(cmd=cmd, returncode=0, stdout="", stderr="")
        return self.results.pop(0)


def test_ensure_venv_raises_on_bootstrap_failure():
    kernel = FakeKernel([CmdResult(cmd=["python", "-m", "venv", ".venv"], returncode=1, stdout="", stderr="venv failed")])
    em = EnvManager(kernel)
    em.venv_python = lambda: "/tmp/nonexistent-env/bin/python"  # type: ignore[method-assign, assignment]

    try:
        em.ensure_venv(system_python="python")
    except RuntimeError as e:
        msg = str(e)
        assert "venv bootstrap failed" in msg
        assert "venv failed" in msg
        assert "command:" in msg
    else:
        assert False, "Expected ensure_venv to fail"


def test_install_requirements_raises_on_bootstrap_failure():
    # pip bootstrap succeeds, requirements install fails
    kernel = FakeKernel([
        CmdResult(cmd=["/tmp/env/bin/python", "-m", "pip", "install", "-U", "pip"], returncode=0, stdout="", stderr=""),
        CmdResult(cmd=["/tmp/env/bin/python", "-m", "pip", "install", "-r", "requirements.txt"], returncode=2, stdout="", stderr="bad requirements"),
    ])
    em = EnvManager(kernel)
    em.venv_python = lambda: "/tmp/env/bin/python"  # type: ignore[method-assign, assignment]

    try:
        em.install_requirements()
    except RuntimeError as e:
        msg = str(e)
        assert "requirements bootstrap failed" in msg
        assert "bad requirements" in msg
        assert "exit=2" in msg
    else:
        assert False, "Expected install_requirements to fail"
