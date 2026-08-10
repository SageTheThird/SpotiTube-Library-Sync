#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
project_dir="$(pwd)"
log_file="$project_dir/data/logs/scheduled.log"
mkdir -p "$(dirname "$log_file")"

cron_line_1="15 0 * * * cd $project_dir && ./scripts/run_two_way_sync.sh >> $log_file 2>&1"
cron_line_2="15 12 * * * cd $project_dir && ./scripts/run_two_way_sync.sh >> $log_file 2>&1"
cron_line_3="25 0 * * * cd $project_dir && ./scripts/run_music_target_sync.sh >> $log_file 2>&1"
cron_line_4="25 12 * * * cd $project_dir && ./scripts/run_music_target_sync.sh >> $log_file 2>&1"

tmp_file="$(mktemp)"
crontab -l 2>/dev/null |
  grep -vF "./scripts/run_two_way_sync.sh" |
  grep -vF "./scripts/run_music_target_sync.sh" > "$tmp_file" || true
{
  cat "$tmp_file"
  echo "$cron_line_1"
  echo "$cron_line_2"
  echo "$cron_line_3"
  echo "$cron_line_4"
} | crontab -
rm -f "$tmp_file"

echo "Installed BeatBridge cron schedule:"
crontab -l | grep -F "./scripts/run_two_way_sync.sh"
crontab -l | grep -F "./scripts/run_music_target_sync.sh"
