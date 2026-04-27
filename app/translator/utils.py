from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from typing import TypeVar

T = TypeVar("T")


def chunked(values: list[T], size: int) -> Iterator[list[T]]:
    if size <= 0:
        raise ValueError("Chunk size must be positive")
    for index in range(0, len(values), size):
        yield values[index : index + size]


def strip_markdown_fence(text: str) -> str:
    text = text.strip()
    fence = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)
    match = fence.match(text)
    return match.group(1).strip() if match else text


def parse_json_array_loose(text: str) -> list[dict]:
    text = strip_markdown_fence(text)
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Translator response does not contain a JSON array")
    payload = text[start : end + 1]
    parsed = json.loads(payload)
    if not isinstance(parsed, list):
        raise ValueError("Translator response JSON must be an array")
    if not all(isinstance(item, dict) for item in parsed):
        raise ValueError("Translator response array items must be objects")
    return parsed


def parse_json_object_loose(text: str) -> dict:
    text = strip_markdown_fence(text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Translator response does not contain a JSON object")
    payload = text[start : end + 1]
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("Translator response JSON must be an object")
    return parsed


def ensure_ids_match(expected: Iterable[int], items: list[dict]) -> None:
    expected_ids = list(expected)
    actual_ids = [int(item.get("id")) for item in items if "id" in item]
    if sorted(expected_ids) != sorted(actual_ids):
        raise ValueError(f"Translator response ids mismatch: expected {expected_ids}, got {actual_ids}")
