from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def translation_cache_key(
    source_text: str,
    context_hash: str,
    model: str,
    prompt_version: str,
) -> str:
    payload = {
        "source_text": source_text,
        "context_hash": context_hash,
        "model": model,
        "prompt_version": prompt_version,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TranslationCache:
    def __init__(self, cache_dir: str | Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> dict[str, Any] | None:
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def set(self, key: str, value: dict[str, Any]) -> None:
        path = self.cache_dir / f"{key}.json"
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
