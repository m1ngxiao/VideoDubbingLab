from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

logger = logging.getLogger(__name__)


class ShellCommandError(RuntimeError):
    def __init__(self, command: Sequence[str], returncode: int, stdout: str, stderr: str):
        self.command = list(command)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        message = (
            f"Command failed with exit code {returncode}: {' '.join(self.command)}\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}"
        )
        super().__init__(message)


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run_command(
    command: Sequence[str],
    cwd: Path | None = None,
    check: bool = True,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    logger.debug("Running command: %s", " ".join(command))
    completed = subprocess.run(
        list(command),
        cwd=str(cwd) if cwd else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
    )
    if check and completed.returncode != 0:
        raise ShellCommandError(command, completed.returncode, completed.stdout, completed.stderr)
    return completed
