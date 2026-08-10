import json
import logging
from datetime import datetime, timezone
from enum import Enum

from beatbridge.config import (
    NUMBER_OF_LIKED_SONGS_TO_FETCH_FROM_YT,
    NUMBER_OF_SONGS_TO_IMPORT_INTO_SPOTIFY,
    SPOTIFY_IMPORT_PLAN_FILE,
    YT_TO_SPOTIFY_SYNC_FILE,
    spotify_to_youtube_plan_file,
    spotify_to_youtube_sync_file,
    youtube_liked_songs_cache_file,
)
from beatbridge.spotify_to_youtube import (
    apply_spotify_to_youtube_plan,
    build_spotify_to_youtube_plan,
)
from beatbridge.spotify_client import (
    apply_spotify_import_plan,
    get_all_spotify_liked_songs,
    import_tracks_from_csv,
)
from beatbridge.storage import load_json_file, save_json_atomic
from beatbridge.utils import save_to_csv
from beatbridge.youtube_client import get_liked_video_ids, get_liked_videos


logger = logging.getLogger(__name__)


class SyncDirection(Enum):
    YT_TO_SPOTIFY = "yt-to-spotify"
    SPOTIFY_TO_YT = "spotify-to-yt"
    YT_TO_YT = "yt-to-yt"
    TWO_WAY = "two-way"


class TwoWaySync:
    def __init__(self, youtube_client, spotify_client, youtube_profile=None):
        self.youtube = youtube_client
        self.spotify = spotify_client
        self.youtube_profile = youtube_profile
        self.yt_to_spotify_cache = YT_TO_SPOTIFY_SYNC_FILE
        self.spotify_to_yt_cache = spotify_to_youtube_sync_file(youtube_profile)
        self.spotify_to_youtube_plan = spotify_to_youtube_plan_file(youtube_profile)
        self.youtube_liked_cache = youtube_liked_songs_cache_file(youtube_profile)

    def run_sync(
        self,
        direction=SyncDirection.YT_TO_SPOTIFY,
        dry_run=False,
        limit=None,
        plan_only=False,
        skip_reverse_imports=True,
    ):
        logger.info(
            "Starting %s sync%s",
            direction.value,
            " in dry-run mode" if dry_run else "",
        )

        workflows = []

        if direction in (SyncDirection.YT_TO_SPOTIFY, SyncDirection.TWO_WAY):
            workflows.append(
                self.sync_youtube_to_spotify(
                    dry_run=dry_run,
                    limit=limit,
                    plan_only=plan_only,
                )
            )

        if direction in (SyncDirection.SPOTIFY_TO_YT, SyncDirection.TWO_WAY):
            workflows.append(
                self.sync_spotify_to_youtube(
                    dry_run=dry_run,
                    limit=limit,
                    plan_only=plan_only,
                    skip_reverse_imports=skip_reverse_imports,
                )
            )

        logger.info("Sync completed")
        return {
            "direction": direction.value,
            "mode": "sync",
            "dry_run": dry_run,
            "plan_only": plan_only,
            "workflows": workflows,
        }

    def sync_youtube_to_spotify(self, dry_run=False, limit=None, plan_only=False):
        liked_videos = get_liked_videos(
            self.youtube,
            max_results=limit or NUMBER_OF_LIKED_SONGS_TO_FETCH_FROM_YT,
        )
        save_to_csv(liked_videos, self.youtube_liked_cache)
        sync_cache = self.load_sync_cache(self.yt_to_spotify_cache)
        opposite_cache = self.load_sync_cache(self.spotify_to_yt_cache)
        sync_cache["skip_synced_items"] = opposite_cache.get("synced_items", [])
        track_ids = import_tracks_from_csv(
            self.spotify,
            self.youtube_liked_cache,
            max_songs=limit or NUMBER_OF_SONGS_TO_IMPORT_INTO_SPOTIFY,
            videos=liked_videos,
            dry_run=dry_run,
            add_oldest_first=True,
            sync_cache=sync_cache,
            limit=limit,
            plan_only=plan_only,
        )
        if not dry_run and not plan_only:
            self.save_sync_cache(sync_cache, self.yt_to_spotify_cache)
        logger.info(
            "%s %s Spotify tracks from YouTube likes",
            "Would add" if dry_run or plan_only else "Processed",
            len(track_ids),
        )
        plan_summary = load_plan_summary(SPOTIFY_IMPORT_PLAN_FILE)
        return {
            "direction": SyncDirection.YT_TO_SPOTIFY.value,
            "label": "YouTube -> Spotify",
            "dry_run": dry_run,
            "plan_only": plan_only,
            "source_items": len(liked_videos),
            "processed": len(track_ids),
            "planned": len(track_ids) if plan_only else plan_summary.get("pending"),
            "skipped": count_plan_statuses(SPOTIFY_IMPORT_PLAN_FILE, "skipped"),
            "not_found": plan_summary.get("not_found"),
        }

    def apply_saved_youtube_to_spotify_plan(self, dry_run=False):
        sync_cache = self.load_sync_cache(self.yt_to_spotify_cache)
        track_ids = apply_spotify_import_plan(
            self.spotify,
            plan_file=SPOTIFY_IMPORT_PLAN_FILE,
            sync_cache=sync_cache,
            dry_run=dry_run,
        )
        if not dry_run:
            self.save_sync_cache(sync_cache, self.yt_to_spotify_cache)
        logger.info("Applied %s Spotify tracks from saved plan", len(track_ids))
        return {
            "direction": SyncDirection.YT_TO_SPOTIFY.value,
            "label": "YouTube -> Spotify",
            "dry_run": dry_run,
            "plan_only": False,
            "processed": len(track_ids),
            "planned": load_plan_summary(SPOTIFY_IMPORT_PLAN_FILE).get("pending"),
            "skipped": count_plan_statuses(SPOTIFY_IMPORT_PLAN_FILE, "skipped"),
            "not_found": load_plan_summary(SPOTIFY_IMPORT_PLAN_FILE).get("not_found"),
        }

    def apply_saved_spotify_to_youtube_plan(self, dry_run=False):
        sync_cache = self.load_sync_cache(self.spotify_to_yt_cache)
        video_ids = apply_spotify_to_youtube_plan(
            self.youtube,
            sync_cache,
            plan_file=self.spotify_to_youtube_plan,
            dry_run=dry_run,
        )
        if not dry_run:
            self.save_sync_cache(sync_cache, self.spotify_to_yt_cache)
        logger.info("Applied %s YouTube likes from saved plan", len(video_ids))
        return {
            "direction": SyncDirection.SPOTIFY_TO_YT.value,
            "label": self.spotify_to_youtube_label(),
            "dry_run": dry_run,
            "plan_only": False,
            "processed": len(video_ids),
            "planned": load_plan_summary(self.spotify_to_youtube_plan).get("pending"),
            "skipped": count_plan_statuses(self.spotify_to_youtube_plan, "skipped"),
            "not_found": load_plan_summary(self.spotify_to_youtube_plan).get("not_found"),
        }

    def sync_spotify_to_youtube(
        self,
        dry_run=False,
        limit=None,
        plan_only=False,
        skip_reverse_imports=True,
    ):
        cache = self.load_sync_cache(self.spotify_to_yt_cache)
        opposite_cache = self.load_sync_cache(self.yt_to_spotify_cache)
        spotify_songs = get_all_spotify_liked_songs(
            self.spotify,
            max_songs=limit or NUMBER_OF_SONGS_TO_IMPORT_INTO_SPOTIFY,
        )
        target_liked_youtube_ids = get_liked_video_ids(
            self.youtube,
            max_results=limit or NUMBER_OF_LIKED_SONGS_TO_FETCH_FROM_YT,
        )

        plan = build_spotify_to_youtube_plan(
            self.youtube,
            spotify_songs,
            sync_cache=cache,
            reverse_sync_cache=opposite_cache,
            target_liked_youtube_ids=target_liked_youtube_ids,
            skip_reverse_imports=skip_reverse_imports,
            plan_file=self.spotify_to_youtube_plan,
        )
        if plan_only:
            logger.info("Plan-only mode: wrote %s", self.spotify_to_youtube_plan)
            return {
                "direction": SyncDirection.SPOTIFY_TO_YT.value,
                "label": self.spotify_to_youtube_label(),
                "dry_run": dry_run,
                "plan_only": True,
                "source_items": len(spotify_songs),
                "processed": 0,
                "planned": plan["summary"].get("pending", 0),
                "skipped": count_plan_statuses(self.spotify_to_youtube_plan, "skipped"),
                "not_found": plan["summary"].get("not_found"),
                "already_liked_on_target": plan["summary"].get(
                    "already_liked_on_target"
                ),
                "direct_reverse_matches": plan["summary"].get(
                    "direct_reverse_matches"
                ),
            }

        video_ids = apply_spotify_to_youtube_plan(
            self.youtube,
            cache,
            plan_file=self.spotify_to_youtube_plan,
            dry_run=dry_run,
        )
        if not dry_run:
            self.save_sync_cache(cache, self.spotify_to_yt_cache)
        logger.info("Synced %s Spotify tracks to YouTube", len(video_ids))
        return {
            "direction": SyncDirection.SPOTIFY_TO_YT.value,
            "label": self.spotify_to_youtube_label(),
            "dry_run": dry_run,
            "plan_only": plan_only,
            "source_items": len(spotify_songs),
            "processed": len(video_ids),
            "planned": plan["summary"].get("pending", 0),
            "skipped": count_plan_statuses(self.spotify_to_youtube_plan, "skipped"),
            "not_found": plan["summary"].get("not_found"),
            "already_liked_on_target": plan["summary"].get(
                "already_liked_on_target"
            ),
            "direct_reverse_matches": plan["summary"].get("direct_reverse_matches"),
        }

    def spotify_to_youtube_label(self):
        if self.youtube_profile:
            return f"Spotify -> YouTube ({self.youtube_profile})"
        return "Spotify -> YouTube"

    def filter_new_spotify_songs(self, spotify_songs, cache):
        synced_spotify_ids = {
            item.get("spotify_id")
            for item in cache.get("synced_items", [])
            if item.get("spotify_id")
        }
        filtered_songs = [
            song for song in spotify_songs if song.get("id") not in synced_spotify_ids
        ]

        last_sync = cache.get("last_sync")
        if not last_sync:
            return filtered_songs

        last_sync_date = parse_iso_datetime(last_sync)
        return [
            song
            for song in filtered_songs
            if parse_iso_datetime(song["added_at"]) > last_sync_date
        ]

    def load_sync_cache(self, cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as file:
                data = json.load(file)
        except FileNotFoundError:
            data = {"last_sync": None, "synced_items": []}
        data["cache_file"] = cache_file
        return data

    def save_sync_cache(self, data, cache_file):
        data_to_save = {key: value for key, value in data.items() if key != "cache_file"}
        save_json_atomic(data_to_save, cache_file)


def parse_iso_datetime(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_plan_summary(plan_file):
    plan = load_json_file(plan_file, default={})
    return plan.get("summary", {})


def count_plan_statuses(plan_file, status):
    plan = load_json_file(plan_file, default={})
    return sum(1 for entry in plan.get("entries", []) if entry.get("status") == status)
