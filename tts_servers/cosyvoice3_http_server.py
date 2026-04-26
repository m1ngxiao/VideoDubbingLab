from __future__ import annotations

import argparse
import filecmp
import logging
import os
import shutil
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

import torch
import torchaudio
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

logger = logging.getLogger("cosyvoice3_http_server")


DEFAULT_PROMPT_TEXT = "You are a helpful assistant.<|endofprompt|>希望你以后能够做的比我还好呦。"


@dataclass
class ServerSettings:
    model_dir: Path
    cosyvoice_root: Path
    ref_audio: Path | None
    prompt_text: str
    use_rl: bool


class TTSRequest(BaseModel):
    text: str
    speaker: str = "default"
    ref_audio: str | None = None
    prompt_text: str | None = None
    sample_rate: int = 24000


def activate_rl_weight(model_dir: Path) -> None:
    base = model_dir / "llm.pt"
    rl = model_dir / "llm.rl.pt"
    backup = model_dir / "llm.base.pt"
    if not rl.exists():
        raise FileNotFoundError(f"RL weight not found: {rl}")
    if not base.exists():
        raise FileNotFoundError(f"Base llm.pt not found: {base}")
    if filecmp.cmp(base, rl, shallow=False):
        logger.info("RL weight is already active: %s", base)
        return
    if not backup.exists():
        logger.info("Backing up base llm.pt to %s", backup)
        shutil.copy2(base, backup)
    logger.info("Activating RL weight by copying %s to %s", rl, base)
    shutil.copy2(rl, base)


def import_cosyvoice(cosyvoice_root: Path):
    cosyvoice_root = cosyvoice_root.resolve()
    sys.path.insert(0, str(cosyvoice_root))
    sys.path.insert(0, str(cosyvoice_root / "third_party" / "Matcha-TTS"))
    from cosyvoice.cli.cosyvoice import AutoModel  # noqa: PLC0415

    return AutoModel


def create_app(settings: ServerSettings) -> FastAPI:
    if settings.use_rl:
        activate_rl_weight(settings.model_dir)
    AutoModel = import_cosyvoice(settings.cosyvoice_root)
    logger.info("Loading Fun-CosyVoice3 model from %s", settings.model_dir)
    model = AutoModel(model_dir=str(settings.model_dir))
    lock = threading.Lock()
    app = FastAPI(title="Fun-CosyVoice3 RL HTTP Server")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "model_dir": str(settings.model_dir),
            "variant": "Fun-CosyVoice3-0.5B-2512_RL" if settings.use_rl else "Fun-CosyVoice3-0.5B-2512",
        }

    @app.post("/tts")
    def tts(req: TTSRequest) -> Response:
        text = req.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="text must not be empty")

        ref_audio = Path(req.ref_audio) if req.ref_audio else settings.ref_audio
        if ref_audio is None:
            ref_audio = settings.cosyvoice_root / "asset" / "zero_shot_prompt.wav"
        if not ref_audio.exists():
            raise HTTPException(status_code=400, detail=f"ref_audio not found: {ref_audio}")

        prompt_text = req.prompt_text or settings.prompt_text
        try:
            chunks: list[torch.Tensor] = []
            with lock:
                for item in model.inference_zero_shot(
                    text,
                    prompt_text,
                    str(ref_audio),
                    stream=False,
                ):
                    chunks.append(item["tts_speech"].detach().cpu())
            if not chunks:
                raise RuntimeError("CosyVoice returned no audio chunks")

            audio = torch.cat(chunks, dim=1) if len(chunks) > 1 else chunks[0]
            sample_rate = int(model.sample_rate)
            if req.sample_rate and req.sample_rate != sample_rate:
                audio = torchaudio.functional.resample(audio, sample_rate, req.sample_rate)
                sample_rate = req.sample_rate

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
                wav_path = Path(handle.name)
            torchaudio.save(str(wav_path), audio, sample_rate)
            payload = wav_path.read_bytes()
            wav_path.unlink(missing_ok=True)
            return Response(content=payload, media_type="audio/wav")
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("TTS request failed")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve Fun-CosyVoice3-0.5B-2512_RL as a local HTTP TTS service.")
    parser.add_argument("--host", default=os.getenv("COSYVOICE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("COSYVOICE_PORT", "9880")))
    parser.add_argument("--model-dir", default=os.getenv("COSYVOICE_MODEL_DIR", "/data/models/tts/Fun-CosyVoice3-0.5B-2512"))
    parser.add_argument("--cosyvoice-root", default=os.getenv("COSYVOICE_ROOT", "/opt/tts/CosyVoice"))
    parser.add_argument("--ref-audio", default=os.getenv("COSYVOICE_REF_AUDIO"))
    parser.add_argument("--prompt-text", default=os.getenv("COSYVOICE_PROMPT_TEXT", DEFAULT_PROMPT_TEXT))
    parser.add_argument("--use-rl", action=argparse.BooleanOptionalAction, default=os.getenv("COSYVOICE_USE_RL", "1") != "0")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    ref_audio = Path(args.ref_audio) if args.ref_audio else None
    settings = ServerSettings(
        model_dir=Path(args.model_dir),
        cosyvoice_root=Path(args.cosyvoice_root),
        ref_audio=ref_audio,
        prompt_text=args.prompt_text,
        use_rl=args.use_rl,
    )
    app = create_app(settings)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
