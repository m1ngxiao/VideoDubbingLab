from __future__ import annotations

import re
from pathlib import Path


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(value: str, max_length: int = 80) -> str:
    normalized = re.sub(r"[\\/:*?\"<>|]+", "_", value)
    normalized = re.sub(r"\s+", "_", normalized).strip("._ ")
    return (normalized or "untitled")[:max_length]


def find_first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None
