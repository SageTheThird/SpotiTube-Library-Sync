#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p data/logs

source_youtube_profile="${SOURCE_YOUTUBE_PROFILE:-ksajid505}"
target_youtube_profile="${TARGET_YOUTUBE_PROFILE:-nastygamer}"
timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "[$timestamp] starting BeatBridge music-target YouTube sync"

plan_file="data/plans/youtube_${source_youtube_profile}_to_youtube_${target_youtube_profile}_plan.json"
pending_count="0"
if [ -f "$plan_file" ]; then
  pending_count="$(python3 - "$plan_file" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as file:
    plan = json.load(file)

print(plan.get("summary", {}).get("pending", 0))
PY
)"
fi

set +e
if [ "$pending_count" -gt 0 ]; then
  echo "[$timestamp] resuming YouTube backfill plan with $pending_count pending items"
  docker compose run --rm beatbridge \
    python main.py \
      --direction yt-to-yt \
      --source-youtube-profile "$source_youtube_profile" \
      --target-youtube-profile "$target_youtube_profile" \
      --apply-plan \
      --no-browser
  youtube_status=$?
else
  docker compose run --rm beatbridge \
    python main.py \
      --direction yt-to-yt \
      --source-youtube-profile "$source_youtube_profile" \
      --target-youtube-profile "$target_youtube_profile" \
      --no-browser
  youtube_status=$?
fi
set -e

if [ "$youtube_status" -ne 0 ]; then
  timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "[$timestamp] BeatBridge music-target YouTube sync failed: youtube=$youtube_status"
  docker compose run --rm beatbridge python - <<'PY' || true
from beatbridge.notifier import notify_sync_summary

notify_sync_summary(
    {
        "direction": "yt-to-yt",
        "mode": "scheduled",
        "failed": True,
        "workflows": [
            {
                "label": "Scheduled music-target YouTube sync",
                "processed": 0,
            }
        ],
    }
)
PY
  exit 1
fi

timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "[$timestamp] finished BeatBridge music-target YouTube sync"
