from __future__ import annotations

import asyncio
import json
import logging

import httpx

from app.schemas import Segment
from app.translator.base import Translator
from app.translator.prompt import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from app.translator.utils import chunked, ensure_ids_match, parse_json_array_loose

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

    async def translate_segments(self, segments: list[Segment]) -> list[Segment]:
        translated: list[Segment] = []
        for batch_index, batch in enumerate(chunked(segments, self.batch_size), start=1):
            logger.info("[translate] batch %s", batch_index)
            translated.extend(await self._translate_batch(batch))
        return translated

    async def _translate_batch(self, segments: list[Segment]) -> list[Segment]:
        segments_json = json.dumps(
            [{"id": item.id, "text": item.source_text} for item in segments],
            ensure_ascii=False,
        )
        user_prompt = USER_PROMPT_TEMPLATE.format(segments_json=segments_json)
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
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
                content = response.json()["choices"][0]["message"]["content"]
                items = parse_json_array_loose(content)
                ensure_ids_match((segment.id for segment in segments), items)
                by_id = {int(item["id"]): str(item["zh_text"]).strip() for item in items}
                for segment in segments:
                    segment.target_text = by_id[segment.id]
                return segments
            except Exception as exc:  # noqa: BLE001 - retry boundary preserves clear final error
                last_error = exc
                logger.warning("[translate] attempt %s/%s failed: %s", attempt, self.max_retries, exc)
                if attempt < self.max_retries:
                    await asyncio.sleep(min(2**attempt, 10))
        raise RuntimeError(f"Translation failed after {self.max_retries} attempts: {last_error}") from last_error
