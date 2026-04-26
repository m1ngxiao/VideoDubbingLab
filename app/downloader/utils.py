from __future__ import annotations

from pathlib import Path


def subtitle_candidates(work_dir: Path) -> list[Path]:
    preferred_names = [
        "source.en.srt",
        "source.en-US.srt",
        "source.en.vtt",
        "source.zh-Hans.srt",
        "source.zh-Hant.srt",
    ]
    candidates = [work_dir / name for name in preferred_names]
    candidates.extend(sorted(work_dir.glob("source.*.srt")))
    candidates.extend(sorted(work_dir.glob("source.*.vtt")))
    seen: set[Path] = set()
    unique: list[Path] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique
