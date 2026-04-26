#!/usr/bin/env bash
set -euo pipefail

COSYVOICE_ROOT="${COSYVOICE_ROOT:-/opt/tts/CosyVoice}"
MODEL_DIR="${COSYVOICE_MODEL_DIR:-/data/models/tts/Fun-CosyVoice3-0.5B-2512}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

sudo apt-get update
sudo apt-get install -y git git-lfs ffmpeg sox libsox-dev unzip build-essential
git lfs install

mkdir -p "$(dirname "$COSYVOICE_ROOT")" "$(dirname "$MODEL_DIR")"
if [[ ! -d "$COSYVOICE_ROOT/.git" ]]; then
  git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git "$COSYVOICE_ROOT"
fi

cd "$COSYVOICE_ROOT"
git submodule update --init --recursive

if command -v conda >/dev/null 2>&1; then
  if ! conda env list | awk '{print $1}' | grep -qx cosyvoice; then
    conda create -n cosyvoice python=3.10 -y
  fi
  # shellcheck disable=SC1091
  source "$(conda info --base)/etc/profile.d/conda.sh"
  conda activate cosyvoice
fi

python -m pip install -U pip
python -m pip install -r requirements.txt
python -m pip install -r "$PROJECT_ROOT/requirements-cosyvoice3.txt" 2>/dev/null || true
python -m pip install -U modelscope fastapi "uvicorn[standard]"

python "$PROJECT_ROOT/scripts/download_cosyvoice3_rl.py" --provider modelscope --output-dir "$MODEL_DIR"

echo "CosyVoice3 RL is ready."
echo "Model dir: $MODEL_DIR"
echo "CosyVoice root: $COSYVOICE_ROOT"
