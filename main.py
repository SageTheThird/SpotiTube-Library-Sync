import argparse
import logging

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from config import client_id, client_secret, redirect_uri, scope
from sync_manager import SyncDirection, TwoWaySync
from youtube_client import authenticate_youtube


def build_spotify_client():
    return spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            cache_path=".spotify_cache",
        )
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Sync liked songs between YouTube Music and Spotify."
    )
    parser.add_argument(
        "--direction",
        choices=[direction.value for direction in SyncDirection],
        default=SyncDirection.YT_TO_SPOTIFY.value,
        help="Sync direction to run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Search and log planned changes without liking or saving tracks.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit how many source items to fetch/process for diagnostics.",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Build the Spotify import plan without adding tracks.",
    )
    parser.add_argument(
        "--apply-plan",
        action="store_true",
        help="Apply the saved Spotify import plan without rebuilding matches.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    args = parse_args(argv)

    spotify = build_spotify_client()

    if args.apply_plan:
        sync_manager = TwoWaySync(None, spotify)
        sync_manager.apply_saved_youtube_to_spotify_plan(dry_run=args.dry_run)
        return

    youtube = authenticate_youtube()
    sync_manager = TwoWaySync(youtube, spotify)
    sync_manager.run_sync(
        direction=SyncDirection(args.direction),
        dry_run=args.dry_run,
        limit=args.limit,
        plan_only=args.plan_only,
    )


if __name__ == "__main__":
    main()
