#!/usr/bin/env bash
set -euo pipefail

COSYVOICE_ROOT="${COSYVOICE_ROOT:-/opt/tts/CosyVoice}"
MODEL_DIR="${COSYVOICE_MODEL_DIR:-/data/models/tts/Fun-CosyVoice3-0.5B-2512}"

if command -v apt-get >/dev/null 2>&1; then
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Please run this script as root, or install system packages manually:"
    echo "  apt-get install -y git git-lfs ffmpeg sox libsox-dev unzip build-essential"
    exit 1
  fi
  apt-get update
  apt-get install -y git git-lfs ffmpeg sox libsox-dev unzip build-essential
fi

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
fi

echo "CosyVoice source and system packages are ready."
echo "Model dir: $MODEL_DIR"
echo "CosyVoice root: $COSYVOICE_ROOT"
echo
echo "Next, enter the Python environment manually and install Python deps:"
echo "  conda activate cosyvoice"
echo "  bash scripts/install_cosyvoice3_rl_deps.sh"
