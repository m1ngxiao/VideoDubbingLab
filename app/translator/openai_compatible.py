from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from app.schemas import Segment
from app.translator.base import Translator
from app.translator.prompt import CONTEXT_PROMPT_TEMPLATE, REFLECT_ADAPT_PROMPT_TEMPLATE, SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
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
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.batch_size = batch_size
        self.max_retries = max_retries

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
        translated: list[Segment] = []
        for batch_index, batch in enumerate(chunked(segments, self.batch_size), start=1):
            logger.info("[translate] batch %s", batch_index)
            translated.extend(await self._translate_batch(batch, summary=summary, terms=terms or [], reflect_adapt=reflect_adapt))
        return translated

    async def _translate_batch(
        self,
        segments: list[Segment],
        summary: str,
        terms: list[dict[str, str]],
        reflect_adapt: bool,
    ) -> list[Segment]:
        segments_json = json.dumps(
            [{"id": item.id, "text": item.source_text} for item in segments],
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
        draft_by_id = {int(item["id"]): str(item["zh_text"]).strip() for item in items}

        if reflect_adapt:
            draft_json = json.dumps(
                [
                    {"id": segment.id, "source": segment.source_text, "draft_zh": draft_by_id[segment.id]}
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
                draft_by_id = {int(item["id"]): str(item["zh_text"]).strip() for item in items}
            except Exception as exc:  # noqa: BLE001 - draft translation is still usable
                logger.warning("[translate] reflect/adapt failed, using draft translation: %s", exc)

        for segment in segments:
            segment.target_text = draft_by_id[segment.id]
        return segments

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
