from __future__ import annotations

import html
import re

_TAG_RE = re.compile(r"<[^>]+>")
_AUTOCAPTION_ARTIFACT_RE = re.compile(
    r"(?i)(?:^\s*(?:\[|\()?\s*(?:music|applause|laughter|noise|silence)\s*(?:\]|\))?\s*$)"
)
_LEADING_SPEAKER_MARK_RE = re.compile(r"^\s*(?:>>+|[-–—])\s*")
_WEBVTT_TAG_RE = re.compile(r"<(?:c|v|lang|ruby|rt|rp)(?:\.[^ >]+)?(?: [^>]*)?>|</(?:c|v|lang|ruby|rt|rp)>")


def normalize_subtitle_text(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("&nbsp;", " ")
    text = _WEBVTT_TAG_RE.sub("", text)
    text = _TAG_RE.sub("", text)
    text = text.replace("♪", " ")
    text = text.replace("\ufeff", "")
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    cleaned_lines: list[str] = []
    for line in lines:
        if not line or _AUTOCAPTION_ARTIFACT_RE.match(line):
            continue
        line = _LEADING_SPEAKER_MARK_RE.sub("", line)
        cleaned_lines.append(line)
    text = " ".join(cleaned_lines)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
