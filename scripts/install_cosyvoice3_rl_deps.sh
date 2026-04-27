#!/usr/bin/env bash
set -euo pipefail

COSYVOICE_ROOT="${COSYVOICE_ROOT:-/opt/tts/CosyVoice}"
MODEL_DIR="${COSYVOICE_MODEL_DIR:-/data/models/tts/Fun-CosyVoice3-0.5B-2512}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if command -v conda >/dev/null 2>&1 && [[ "${CONDA_DEFAULT_ENV:-}" != "cosyvoice" ]]; then
  echo "Please activate the CosyVoice environment first:"
  echo "  conda activate cosyvoice"
  echo "  bash scripts/install_cosyvoice3_rl_deps.sh"
  exit 1
fi

if [[ ! -d "$COSYVOICE_ROOT" ]]; then
  echo "CosyVoice root not found: $COSYVOICE_ROOT"
  echo "Run scripts/setup_cosyvoice3_rl_ubuntu.sh first."
  exit 1
fi

cd "$COSYVOICE_ROOT"

python -m pip install -U pip wheel packaging
python -m pip install "setuptools<81"
python -m pip install --no-build-isolation openai-whisper
python -m pip install -r requirements.txt
python -m pip install -r "$PROJECT_ROOT/requirements-cosyvoice3.txt"
python -m pip install -U modelscope fastapi "uvicorn[standard]"

python "$PROJECT_ROOT/scripts/download_cosyvoice3_rl.py" --provider modelscope --output-dir "$MODEL_DIR"

echo "CosyVoice3 RL Python dependencies and model are ready."
echo "Model dir: $MODEL_DIR"
echo "CosyVoice root: $COSYVOICE_ROOT"
