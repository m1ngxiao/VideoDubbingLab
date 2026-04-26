#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${LLM_API_KEY:-}" ]]; then
  echo "Please export LLM_API_KEY before running the demo."
  exit 1
fi

python -m app.cli dub-youtube \
  --url "${1:?Usage: scripts/run_demo.sh YOUTUBE_URL}" \
  --output-dir ./data/output \
  --config ./configs/default.yaml \
  --resume
