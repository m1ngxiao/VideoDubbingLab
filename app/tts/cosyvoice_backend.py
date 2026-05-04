from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx

from app.audio.convert import convert_audio_to_wav
from app.tts.base import TTSBackend


class CosyVoiceHTTPBackend(TTSBackend):
    def __init__(
        self,
        endpoint: str,
        sample_rate: int = 24000,
        prompt_text: str | None = None,
        timeout_seconds: int = 120,
        batch_endpoint: str | None = None,
    ):
        self.endpoint = endpoint
        self.batch_endpoint = batch_endpoint
        self.sample_rate = sample_rate
        self.prompt_text = prompt_text
        self.timeout_seconds = timeout_seconds
        self._client: httpx.AsyncClient | None = None

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout_seconds)
        return self._client

    async def synthesize(
        self,
        text: str,
        out_path: Path,
        speaker: str = "default",
        ref_audio: str | None = None,
        target_duration: float | None = None,
    ) -> Path:
        del target_duration
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = self._payload(text=text, speaker=speaker, ref_audio=ref_audio)
        response = await self._get_client().post(self.endpoint, json=payload)
        response.raise_for_status()
        return _write_response_wav(response.content, out_path, self.sample_rate)

    async def synthesize_batch(self, items: list[dict[str, Any]]) -> list[Path]:
        if not self.batch_endpoint:
            return await super().synthesize_batch(items)
        if not items:
            return []
        request_items = []
        for item in items:
            request_items.append(
                {
                    "id": str(item.get("id")),
                    **self._payload(
                        text=str(item["text"]),
                        speaker=str(item.get("speaker") or "default"),
                        ref_audio=item.get("ref_audio"),
                    ),
                }
            )
        response = await self._get_client().post(self.batch_endpoint, json={"items": request_items})
        response.raise_for_status()
        payload = response.json()
        outputs_by_id = {str(item.get("id")): item for item in payload.get("items", [])}
        paths: list[Path] = []
        for item in items:
            out_path = Path(item["out_path"])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            result = outputs_by_id.get(str(item.get("id")))
            if not result:
                raise RuntimeError(f"Missing TTS batch result for item {item.get('id')}")
            if result.get("error"):
                raise RuntimeError(f"TTS batch item {item.get('id')} failed: {result['error']}")
            audio_base64 = result.get("audio_base64")
            if not audio_base64:
                raise RuntimeError(f"TTS batch item {item.get('id')} returned no audio")
            paths.append(_write_response_wav(base64.b64decode(audio_base64), out_path, self.sample_rate))
        return paths

    def _payload(self, text: str, speaker: str, ref_audio: str | None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "text": text,
            "speaker": speaker,
            "ref_audio": ref_audio,
            "sample_rate": self.sample_rate,
        }
        if self.prompt_text:
            payload["prompt_text"] = self.prompt_text
        return payload


def _write_response_wav(content: bytes, out_path: Path, sample_rate: int) -> Path:
    tmp_wav = out_path.with_suffix(".raw.wav")
    tmp_wav.write_bytes(content)
    convert_audio_to_wav(tmp_wav, out_path, sample_rate=sample_rate)
    tmp_wav.unlink(missing_ok=True)
    return out_path
