#!/usr/bin/env bash
set -euo pipefail

export COSYVOICE_ROOT="${COSYVOICE_ROOT:-/opt/tts/CosyVoice}"
export COSYVOICE_MODEL_DIR="${COSYVOICE_MODEL_DIR:-/data/models/tts/Fun-CosyVoice3-0.5B-2512}"
export COSYVOICE_USE_RL="${COSYVOICE_USE_RL:-1}"
export COSYVOICE_HOST="${COSYVOICE_HOST:-127.0.0.1}"
export COSYVOICE_PORT="${COSYVOICE_PORT:-9880}"
export COSYVOICE_PROMPT_TEXT="${COSYVOICE_PROMPT_TEXT:-You are a helpful assistant.<|endofprompt|>希望你以后能够做的比我还好呦。}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

python "$PROJECT_ROOT/tts_servers/cosyvoice3_http_server.py" \
  --host "$COSYVOICE_HOST" \
  --port "$COSYVOICE_PORT" \
  --model-dir "$COSYVOICE_MODEL_DIR" \
  --cosyvoice-root "$COSYVOICE_ROOT" \
  --use-rl
