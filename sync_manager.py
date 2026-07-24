import logging
from datetime import datetime, timedelta
import json
from config import (
    NUMBER_OF_LIKED_SONGS_TO_FETCH_FROM_YT,
    NUMBER_OF_SONGS_TO_IMPORT_INTO_SPOTIFY,
    YOUTUBE_LIKED_SONGS_CACHE_FILE,
)

from spotify_client import import_tracks_from_csv, get_all_spotify_liked_songs
from youtube_client import (
    authenticate_youtube,
    get_liked_videos,
    search_youtube,
    like_youtube_video,
)
from utils import save_to_csv
import os

YOUTUBE_SEARCH_CACHE_FILE = "youtube_search_cache.json"


class TwoWaySync:
    def __init__(self, youtube_client, spotify_client):
        self.youtube = youtube_client
        self.spotify = spotify_client
        self.yt_to_spotify_cache = "yt_to_spotify_sync.json"
        self.spotify_to_yt_cache = "spotify_to_yt_sync.json"

    def load_sync_cache(self, cache_file):
        try:
            with open(cache_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"last_sync": None, "synced_items": []}

    def save_sync_cache(self, data, cache_file):
        with open(cache_file, "w") as f:
            json.dump(data, f)

    def load_youtube_search_cache():
        """Load cached YouTube search results."""
        if os.path.exists(YOUTUBE_SEARCH_CACHE_FILE):
            with open(YOUTUBE_SEARCH_CACHE_FILE, "r") as f:
                return json.load(f)
        return {}

    def save_youtube_search_cache(cache):
        """Save updated cache to file."""
        with open(YOUTUBE_SEARCH_CACHE_FILE, "w") as f:
            json.dump(cache, f)

    def sync_spotify_to_youtube(self):
        """Sync Spotify liked songs to YouTube"""
        cache = self.load_sync_cache(self.spotify_to_yt_cache)
        last_sync = cache["last_sync"]

        # Get recently liked Spotify songs
        spotify_songs = get_all_spotify_liked_songs(
            max_songs=NUMBER_OF_SONGS_TO_IMPORT_INTO_SPOTIFY
        )

        # Filter for new songs since last sync
        if last_sync:
            last_sync_date = datetime.fromisoformat(last_sync)
            spotify_songs = [
                song
                for song in spotify_songs
                if datetime.fromisoformat(song["added_at"]) > last_sync_date
            ]

        for song in spotify_songs:
            # Create search query
            artists_str = ", ".join(song["artists"])
            query = f"{song['name']} {artists_str}"

            # Search on YouTube
            video_id = search_youtube(self.youtube, query)
            if video_id:
                # Like the video if found
                if like_youtube_video(self.youtube, video_id):
                    logging.info(f"Liked on YouTube: {song['name']}")
                    cache["synced_items"].append(
                        {
                            "spotify_name": song["name"],
                            "youtube_id": video_id,
                            "sync_date": datetime.now().isoformat(),
                        }
                    )

        # Update last sync time
        cache["last_sync"] = datetime.now().isoformat()
        self.save_sync_cache(cache, self.spotify_to_yt_cache)

    def run_two_way_sync(self):
        """Run both YouTube->Spotify and Spotify->YouTube sync"""
        logging.info("Starting two-way sync...")

        # First sync YouTube likes to Spotify (existing functionality)
        liked_videos = get_liked_videos(
            self.youtube, max_results=NUMBER_OF_LIKED_SONGS_TO_FETCH_FROM_YT
        )
        save_to_csv(liked_videos)
        import_tracks_from_csv(
            YOUTUBE_LIKED_SONGS_CACHE_FILE,
            max_songs=NUMBER_OF_SONGS_TO_IMPORT_INTO_SPOTIFY,
            videos=liked_videos,
        )

        # Then sync Spotify likes to YouTube
        # self.sync_spotify_to_youtube()

        logging.info("Two-way sync completed")
