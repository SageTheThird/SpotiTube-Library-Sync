#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p data/logs

source_youtube_profile="${SOURCE_YOUTUBE_PROFILE:-ksajid505}"
target_youtube_profile="${TARGET_YOUTUBE_PROFILE:-nastygamer}"
timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "[$timestamp] starting BeatBridge music-target sync"

set +e
docker compose run --rm beatbridge \
  python main.py \
    --direction spotify-to-yt \
    --youtube-profile "$target_youtube_profile" \
    --include-reverse-imports \
    --no-browser
spotify_status=$?

docker compose run --rm beatbridge \
  python main.py \
    --direction yt-to-yt \
    --source-youtube-profile "$source_youtube_profile" \
    --target-youtube-profile "$target_youtube_profile" \
    --no-browser
youtube_status=$?
set -e

if [ "$spotify_status" -ne 0 ] || [ "$youtube_status" -ne 0 ]; then
  timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "[$timestamp] BeatBridge music-target sync failed: spotify=$spotify_status youtube=$youtube_status"
  docker compose run --rm beatbridge python - <<'PY' || true
from beatbridge.notifier import notify_sync_summary

notify_sync_summary(
    {
        "direction": "music-target",
        "mode": "scheduled",
        "failed": True,
        "workflows": [
            {
                "label": "Scheduled music-target sync",
                "processed": 0,
            }
        ],
    }
)
PY
  exit 1
fi

timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "[$timestamp] finished BeatBridge music-target sync"
