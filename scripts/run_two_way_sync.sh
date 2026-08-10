#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p data/logs

timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "[$timestamp] starting BeatBridge two-way sync"

set +e
docker compose run --rm beatbridge \
  python main.py --direction two-way --no-browser
status=$?
set -e

if [ "$status" -ne 0 ]; then
  timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "[$timestamp] BeatBridge two-way sync failed with exit code $status"
  docker compose run --rm beatbridge python - <<'PY' || true
from beatbridge.notifier import notify_sync_summary

notify_sync_summary(
    {
        "direction": "two-way",
        "mode": "scheduled",
        "failed": True,
        "workflows": [
            {
                "label": "Scheduled sync",
                "processed": 0,
            }
        ],
    }
)
PY
  exit "$status"
fi

timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "[$timestamp] finished BeatBridge two-way sync"
