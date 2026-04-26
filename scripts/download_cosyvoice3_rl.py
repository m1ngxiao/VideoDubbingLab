from __future__ import annotations

import argparse
import filecmp
import shutil
from pathlib import Path


def activate_rl(model_dir: Path) -> None:
    llm = model_dir / "llm.pt"
    rl = model_dir / "llm.rl.pt"
    backup = model_dir / "llm.base.pt"
    if not llm.exists():
        raise FileNotFoundError(f"Missing {llm}")
    if not rl.exists():
        raise FileNotFoundError(f"Missing {rl}")
    if filecmp.cmp(llm, rl, shallow=False):
        print("RL weight already active.")
        return
    if not backup.exists():
        shutil.copy2(llm, backup)
        print(f"Backed up base weight: {backup}")
    shutil.copy2(rl, llm)
    print(f"Activated RL weight: {rl} -> {llm}")


def download_modelscope(model_id: str, output_dir: Path) -> None:
    try:
        from modelscope import snapshot_download
    except ImportError as exc:
        raise RuntimeError("Please install modelscope first: pip install -U modelscope") from exc
    snapshot_download(model_id, local_dir=str(output_dir))


def download_huggingface(repo_id: str, output_dir: Path) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError("Please install huggingface_hub first: pip install -U huggingface_hub") from exc
    snapshot_download(repo_id=repo_id, local_dir=str(output_dir), local_dir_use_symlinks=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and activate Fun-CosyVoice3-0.5B-2512_RL weights.")
    parser.add_argument("--provider", choices=["modelscope", "huggingface"], default="modelscope")
    parser.add_argument("--output-dir", default="/data/models/tts/Fun-CosyVoice3-0.5B-2512")
    parser.add_argument("--no-activate-rl", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.provider == "modelscope":
        download_modelscope("FunAudioLLM/Fun-CosyVoice3-0.5B-2512", output_dir)
    else:
        download_huggingface("FunAudioLLM/Fun-CosyVoice3-0.5B-2512", output_dir)

    if not args.no_activate_rl:
        activate_rl(output_dir)


if __name__ == "__main__":
    main()
