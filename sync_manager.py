import json
import logging
from datetime import datetime, timezone
from enum import Enum

from config import (
    NUMBER_OF_LIKED_SONGS_TO_FETCH_FROM_YT,
    NUMBER_OF_SONGS_TO_IMPORT_INTO_SPOTIFY,
    SPOTIFY_IMPORT_PLAN_FILE,
    YOUTUBE_LIKED_SONGS_CACHE_FILE,
)
from spotify_client import (
    apply_spotify_import_plan,
    get_all_spotify_liked_songs,
    import_tracks_from_csv,
)
from utils import save_to_csv
from youtube_client import get_liked_videos, like_youtube_video, search_youtube


logger = logging.getLogger(__name__)


class SyncDirection(Enum):
    YT_TO_SPOTIFY = "yt-to-spotify"
    SPOTIFY_TO_YT = "spotify-to-yt"
    TWO_WAY = "two-way"


class TwoWaySync:
    def __init__(self, youtube_client, spotify_client):
        self.youtube = youtube_client
        self.spotify = spotify_client
        self.yt_to_spotify_cache = "yt_to_spotify_sync.json"
        self.spotify_to_yt_cache = "spotify_to_yt_sync.json"

    def run_sync(
        self,
        direction=SyncDirection.YT_TO_SPOTIFY,
        dry_run=False,
        limit=None,
        plan_only=False,
    ):
        logger.info(
            "Starting %s sync%s",
            direction.value,
            " in dry-run mode" if dry_run else "",
        )

        if direction in (SyncDirection.YT_TO_SPOTIFY, SyncDirection.TWO_WAY):
            self.sync_youtube_to_spotify(
                dry_run=dry_run,
                limit=limit,
                plan_only=plan_only,
            )

        if direction in (SyncDirection.SPOTIFY_TO_YT, SyncDirection.TWO_WAY):
            self.sync_spotify_to_youtube(dry_run=dry_run)

        logger.info("Sync completed")

    def sync_youtube_to_spotify(self, dry_run=False, limit=None, plan_only=False):
        liked_videos = get_liked_videos(
            self.youtube,
            max_results=limit or NUMBER_OF_LIKED_SONGS_TO_FETCH_FROM_YT,
        )
        save_to_csv(liked_videos)
        sync_cache = self.load_sync_cache(self.yt_to_spotify_cache)
        track_ids = import_tracks_from_csv(
            self.spotify,
            YOUTUBE_LIKED_SONGS_CACHE_FILE,
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
        return track_ids

    def sync_spotify_to_youtube(self, dry_run=False):
        cache = self.load_sync_cache(self.spotify_to_yt_cache)
        spotify_songs = get_all_spotify_liked_songs(
            self.spotify,
            max_songs=NUMBER_OF_SONGS_TO_IMPORT_INTO_SPOTIFY,
        )
        spotify_songs = self.filter_new_spotify_songs(spotify_songs, cache)

        synced_count = 0
        for song in spotify_songs:
            artists_str = ", ".join(song["artists"])
            query = f"{song['name']} {artists_str}"

            video_id = search_youtube(self.youtube, query)
            if not video_id:
                logger.warning("No YouTube result found for Spotify track: %s", query)
                continue

            if dry_run:
                logger.info(
                    "Dry run: would like YouTube video %s for %s",
                    video_id,
                    query,
                )
                synced_count += 1
                continue

            if like_youtube_video(self.youtube, video_id):
                logger.info("Liked on YouTube: %s", query)
                cache["synced_items"].append(
                    {
                        "spotify_id": song["id"],
                        "spotify_name": song["name"],
                        "spotify_artists": song["artists"],
                        "youtube_id": video_id,
                        "sync_date": utc_now_iso(),
                    }
                )
                synced_count += 1

        if dry_run:
            logger.info("Dry run: would sync %s Spotify tracks to YouTube", synced_count)
            return

        cache["last_sync"] = utc_now_iso()
        self.save_sync_cache(cache, self.spotify_to_yt_cache)
        logger.info("Synced %s Spotify tracks to YouTube", synced_count)

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
        with open(cache_file, "w", encoding="utf-8") as file:
            json.dump(data_to_save, file, indent=2)


def parse_iso_datetime(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()
