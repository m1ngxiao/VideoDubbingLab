from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any

import httpx

from app.schemas import Segment
from app.translator.base import Translator
from app.translator.cache import TranslationCache, translation_cache_key
from app.translator.prompt import (
    COMPRESS_PROMPT_TEMPLATE,
    CONTEXT_PROMPT_TEMPLATE,
    REFLECT_ADAPT_PROMPT_TEMPLATE,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)
from app.translator.utils import chunked, ensure_ids_match, parse_json_array_loose, parse_json_object_loose

logger = logging.getLogger(__name__)


class OpenAICompatibleTranslator(Translator):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.2,
        timeout_seconds: int = 120,
        batch_size: int = 20,
        max_retries: int = 3,
        cache_dir: str | None = None,
        cache_enabled: bool = True,
        prompt_version: str = "duration-aware-v1",
        over_duration_ratio: float = 1.10,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.cache = TranslationCache(cache_dir) if cache_dir and cache_enabled else None
        self.prompt_version = prompt_version
        self.over_duration_ratio = over_duration_ratio

    async def prepare_context(
        self,
        segments: list[Segment],
        preserve_terms: list[str],
        max_chars: int = 8000,
        enable_summary: bool = True,
        enable_terms: bool = True,
    ) -> tuple[str, list[dict[str, str]]]:
        if not enable_summary and not enable_terms:
            return "", [{"source": term, "target": term} for term in preserve_terms]
        transcript = "\n".join(f"{segment.id}. {segment.source_text}" for segment in segments)
        transcript = transcript[:max_chars]
        prompt = CONTEXT_PROMPT_TEMPLATE.format(
            preserve_terms=", ".join(preserve_terms) or "无",
            transcript=transcript,
        )
        try:
            content = await self._chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ]
            )
            parsed = parse_json_object_loose(content)
            summary = str(parsed.get("summary") or "") if enable_summary else ""
            raw_terms = parsed.get("terms") if enable_terms else []
            terms = _normalize_terms(raw_terms, preserve_terms)
            return summary, terms
        except Exception as exc:  # noqa: BLE001 - context should improve quality, not block the whole run
            logger.warning("[translate] context generation failed, using fallback context: %s", exc)
            fallback_summary = " ".join(segment.source_text for segment in segments[:20])[:500] if enable_summary else ""
            return fallback_summary, [{"source": term, "target": term} for term in preserve_terms]

    async def translate_segments(
        self,
        segments: list[Segment],
        summary: str = "",
        terms: list[dict[str, str]] | None = None,
        reflect_adapt: bool = True,
    ) -> list[Segment]:
        context_hash = _context_hash(summary, terms or [])
        translated_by_id: dict[int, Segment] = {}
        pending: list[Segment] = []
        for segment in segments:
            key = translation_cache_key(segment.source_text, context_hash, self.model, self.prompt_version)
            segment.translation_cache_key = key
            cached = self.cache.get(key) if self.cache else None
            if cached:
                _apply_translation_item(segment, cached, self.over_duration_ratio)
                translated_by_id[segment.id] = segment
            else:
                pending.append(segment)

        pending_ids = {segment.id for segment in pending}
        for batch_index, batch in enumerate(chunked(segments, self.batch_size), start=1):
            batch = [segment for segment in batch if segment.id in pending_ids]
            if not batch:
                continue
            logger.info("[translate] batch %s", batch_index)
            translated = await self._translate_batch_resilient(
                batch,
                summary=summary,
                terms=terms or [],
                reflect_adapt=reflect_adapt,
            )
            for segment in translated:
                translated_by_id[segment.id] = segment
                if self.cache and segment.translation_cache_key and segment.target_text:
                    self.cache.set(segment.translation_cache_key, _segment_cache_payload(segment))

        return [translated_by_id.get(segment.id, segment) for segment in segments]

    async def _translate_batch_resilient(
        self,
        segments: list[Segment],
        summary: str,
        terms: list[dict[str, str]],
        reflect_adapt: bool,
    ) -> list[Segment]:
        try:
            return await self._translate_batch(segments, summary=summary, terms=terms, reflect_adapt=reflect_adapt)
        except Exception as exc:  # noqa: BLE001 - retry smaller units to avoid losing the whole film
            logger.warning("[translate] batch failed, retrying locally by segment: %s", exc)
            if len(segments) == 1:
                segment = segments[0]
                warning = f"Translation failed for segment {segment.id}: {exc}"
                segment.warnings.append(warning)
                segment.target_text = segment.source_text
                segment.short_target_text = segment.source_text
                segment.translation_notes.append("fallback_to_source_after_translation_failure")
                return [segment]
            translated: list[Segment] = []
            for segment in segments:
                translated.extend(
                    await self._translate_batch_resilient([segment], summary=summary, terms=terms, reflect_adapt=reflect_adapt)
                )
            return translated

    async def _translate_batch(
        self,
        segments: list[Segment],
        summary: str,
        terms: list[dict[str, str]],
        reflect_adapt: bool,
    ) -> list[Segment]:
        segments_json = json.dumps(
            [
                {
                    "id": item.id,
                    "text": item.source_text,
                    "duration": round(item.duration, 3),
                    "max_zh_chars": item.max_zh_chars,
                }
                for item in segments
            ],
            ensure_ascii=False,
        )
        terms_json = json.dumps(terms, ensure_ascii=False)
        user_prompt = USER_PROMPT_TEMPLATE.format(
            summary=summary or "无",
            terms_json=terms_json,
            segments_json=segments_json,
        )
        content = await self._chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
        )
        items = parse_json_array_loose(content)
        ensure_ids_match((segment.id for segment in segments), items)
        draft_by_id = {int(item["id"]): item for item in items}

        if reflect_adapt:
            draft_json = json.dumps(
                [
                    {
                        "id": segment.id,
                        "source": segment.source_text,
                        "duration": round(segment.duration, 3),
                        "max_zh_chars": segment.max_zh_chars,
                        "draft_zh": str(draft_by_id[segment.id].get("zh_text") or "").strip(),
                        "draft_short_zh": str(draft_by_id[segment.id].get("short_zh_text") or "").strip(),
                    }
                    for segment in segments
                ],
                ensure_ascii=False,
            )
            reflect_prompt = REFLECT_ADAPT_PROMPT_TEMPLATE.format(
                summary=summary or "无",
                terms_json=terms_json,
                draft_json=draft_json,
            )
            try:
                reflected = await self._chat(
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": reflect_prompt},
                    ]
                )
                items = parse_json_array_loose(reflected)
                ensure_ids_match((segment.id for segment in segments), items)
                draft_by_id = {int(item["id"]): item for item in items}
            except Exception as exc:  # noqa: BLE001 - draft translation is still usable
                logger.warning("[translate] reflect/adapt failed, using draft translation: %s", exc)

        for segment in segments:
            _apply_translation_item(segment, draft_by_id[segment.id], self.over_duration_ratio)
        return segments

    async def compress_segment(self, segment: Segment) -> Segment:
        segment_json = json.dumps(
            {
                "id": segment.id,
                "source": segment.source_text,
                "zh_text": segment.target_text or segment.short_target_text or segment.source_text,
                "duration": round(segment.duration, 3),
                "max_zh_chars": segment.max_zh_chars,
            },
            ensure_ascii=False,
        )
        prompt = COMPRESS_PROMPT_TEMPLATE.format(
            duration=segment.duration,
            max_zh_chars=segment.max_zh_chars or 0,
            segment_json=segment_json,
        )
        content = await self._chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
        )
        item = parse_json_object_loose(content)
        _apply_translation_item(segment, item, self.over_duration_ratio)
        segment.translation_notes.append("compressed_by_llm")
        return segment

    async def _chat(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": messages,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()
                return str(response.json()["choices"][0]["message"]["content"])
            except Exception as exc:  # noqa: BLE001 - retry boundary preserves clear final error
                last_error = exc
                logger.warning("[translate] chat attempt %s/%s failed: %s", attempt, self.max_retries, exc)
                if attempt < self.max_retries:
                    await asyncio.sleep(min(2**attempt, 10))
        raise RuntimeError(f"LLM request failed after {self.max_retries} attempts: {last_error}") from last_error


def _normalize_terms(raw_terms: Any, preserve_terms: list[str]) -> list[dict[str, str]]:
    terms: list[dict[str, str]] = [{"source": term, "target": term} for term in preserve_terms]
    if isinstance(raw_terms, list):
        for item in raw_terms:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source") or item.get("term") or "").strip()
            target = str(item.get("target") or item.get("translation") or source).strip()
            if source:
                terms.append({"source": source, "target": target})
    deduped: dict[str, dict[str, str]] = {}
    for item in terms:
        deduped[item["source"].lower()] = item
    return list(deduped.values())


def _context_hash(summary: str, terms: list[dict[str, str]]) -> str:
    payload = json.dumps({"summary": summary, "terms": terms}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _apply_translation_item(segment: Segment, item: dict[str, Any], over_duration_ratio: float) -> None:
    zh_text = str(item.get("zh_text") or "").strip()
    short_zh_text = str(item.get("short_zh_text") or zh_text).strip()
    if not zh_text:
        raise ValueError(f"Translation item for segment {segment.id} missing zh_text")
    estimated_seconds = _optional_float(item.get("estimated_seconds"))
    notes = item.get("notes")
    if isinstance(notes, list):
        segment.translation_notes.extend(str(note) for note in notes if str(note).strip())
    elif notes:
        segment.translation_notes.append(str(notes))
    segment.short_target_text = short_zh_text or zh_text
    segment.estimated_seconds = estimated_seconds
    if estimated_seconds is not None and estimated_seconds > segment.duration * over_duration_ratio and short_zh_text:
        segment.target_text = short_zh_text
        segment.translation_notes.append("used_short_zh_text_for_duration")
    else:
        segment.target_text = zh_text


def _segment_cache_payload(segment: Segment) -> dict[str, Any]:
    return {
        "id": segment.id,
        "zh_text": segment.target_text,
        "short_zh_text": segment.short_target_text or segment.target_text,
        "estimated_seconds": segment.estimated_seconds,
        "notes": " | ".join(segment.translation_notes),
    }


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
