#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p data/logs

timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "[$timestamp] starting BeatBridge two-way sync"

docker compose run --rm beatbridge \
  python main.py --direction two-way --no-browser

timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "[$timestamp] finished BeatBridge two-way sync"
