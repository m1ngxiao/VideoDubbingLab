from __future__ import annotations

import html
import re

_TAG_RE = re.compile(r"<[^>]+>")


def normalize_subtitle_text(text: str) -> str:
    text = html.unescape(text)
    text = _TAG_RE.sub("", text)
    text = text.replace("\ufeff", "")
    lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    text = " ".join(line for line in lines if line)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
