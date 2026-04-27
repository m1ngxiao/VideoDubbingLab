#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DEEPSEEK_API_KEY:-}" && -z "${LLM_API_KEY:-}" ]]; then
  echo "Please export DEEPSEEK_API_KEY before running the demo."
  exit 1
fi

python -m app.cli dub-youtube \
  --url "${1:?Usage: scripts/run_demo.sh YOUTUBE_URL}" \
  --output-dir ./data/output \
  --config ./configs/cosyvoice3_rl.yaml \
  --resume
