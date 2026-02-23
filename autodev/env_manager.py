from __future__ import annotations
import os
from .exec_kernel import ExecKernel

class EnvManager:
    def __init__(self, kernel: ExecKernel):
        self.k = kernel

    def venv_python(self) -> str:
        win = os.name == "nt"
        return os.path.join(self.k.cwd, ".venv", "Scripts" if win else "bin", "python.exe" if win else "python")

    def ensure_venv(self, system_python: str = "python") -> None:
        py = self.venv_python()
        if os.path.exists(py):
            return
        self.k.run(self.k.module_cmd(system_python, "venv", ".venv"))

    def install_requirements(self) -> None:
        py = self.venv_python()
        self.k.run(self.k.module_cmd(py, "pip", "install", "-U", "pip"))
        self.k.run(self.k.module_cmd(py, "pip", "install", "-r", "requirements.txt"))
