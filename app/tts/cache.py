from __future__ import annotations

import hashlib
from pathlib import Path


def ref_audio_hash(ref_audio: str | None) -> str:
    if not ref_audio:
        return ""
    path = Path(ref_audio)
    if not path.exists():
        return hashlib.sha256(str(ref_audio).encode("utf-8")).hexdigest()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tts_cache_key(
    text: str,
    voice: str,
    speaker: str,
    ref_audio_digest: str,
    model_version: str,
    prompt_text: str | None,
) -> str:
    payload = "\n".join(
        [
            text,
            voice,
            speaker,
            ref_audio_digest,
            model_version,
            prompt_text or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
