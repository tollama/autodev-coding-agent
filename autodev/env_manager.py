from __future__ import annotations
import os
from .exec_kernel import ExecKernel

class EnvManager:
    def __init__(self, kernel: ExecKernel):
        self.k = kernel

    def venv_python(self) -> str:
        win = os.name == "nt"
        return os.path.join(self.k.cwd, ".venv", "Scripts" if win else "bin", "python.exe" if win else "python")

    def _require_success(self, result, action: str) -> None:
        if result.returncode != 0:
            cmd = " ".join(result.cmd)
            raise RuntimeError(
                f"{action} failed (exit={result.returncode}).\n"
                f"command: {cmd}\n"
                f"stderr: {result.stderr.strip() or '<empty>'}\n"
                f"stdout: {result.stdout.strip() or '<empty>'}"
            )

    def ensure_venv(self, system_python: str = "python") -> None:
        py = self.venv_python()
        if os.path.exists(py):
            return
        self._require_success(self.k.run(self.k.module_cmd(system_python, "venv", ".venv")), "venv bootstrap")

    def install_requirements(self, include_dev: bool | None = None) -> None:
        if include_dev is None:
            include_dev = os.path.exists(os.path.join(self.k.cwd, "requirements-dev.txt"))

        py = self.venv_python()
        self._require_success(self.k.run(self.k.module_cmd(py, "pip", "install", "-U", "pip")), "pip bootstrap")
        self._require_success(self.k.run(self.k.module_cmd(py, "pip", "install", "-r", "requirements.txt")), "requirements bootstrap")
        if include_dev:
            dev_file = os.path.join(self.k.cwd, "requirements-dev.txt")
            if os.path.exists(dev_file):
                self._require_success(
                    self.k.run(self.k.module_cmd(py, "pip", "install", "-r", "requirements-dev.txt")),
                    "requirements-dev bootstrap",
                )
