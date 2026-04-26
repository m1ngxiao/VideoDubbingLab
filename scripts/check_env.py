from __future__ import annotations

import subprocess
import sys
from pathlib import Path


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    raise SystemExit(
        subprocess.run(
            [sys.executable, "-m", "app.cli", "check-env", "--config", str(root / "configs" / "default.yaml")],
            cwd=root,
            check=False,
        ).returncode
    )
