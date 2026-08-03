import argparse
import logging

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from beatbridge.config import (
    SPOTIFY_AUTH_CACHE_FILE,
    client_id,
    client_secret,
    redirect_uri,
    scope,
)
from beatbridge.notifier import notify_sync_summary
from beatbridge.sync_manager import SyncDirection, TwoWaySync
from beatbridge.youtube_client import authenticate_youtube


def build_spotify_client(open_browser=True):
    return spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            cache_path=SPOTIFY_AUTH_CACHE_FILE,
            open_browser=open_browser,
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
        help="Build the import plan without applying changes.",
    )
    parser.add_argument(
        "--apply-plan",
        action="store_true",
        help="Apply the saved plan for the selected direction without rebuilding matches.",
    )
    parser.add_argument(
        "--check-auth",
        action="store_true",
        help="Validate Spotify and YouTube auth, then exit without syncing.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Disable browser auth prompts for scheduled/non-interactive runs.",
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Do not send Discord notifications for this run.",
    )
    return parser.parse_args(argv)


def check_auth(spotify, youtube):
    spotify_user = spotify.current_user()
    youtube.channels().list(part="id", mine=True, maxResults=1).execute()
    logging.info("Spotify auth OK for %s", spotify_user.get("display_name"))
    logging.info("YouTube auth OK")


def main(argv=None):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    args = parse_args(argv)
    open_browser = not args.no_browser

    spotify = build_spotify_client(open_browser=open_browser)

    if args.check_auth:
        youtube = authenticate_youtube(open_browser=open_browser)
        check_auth(spotify, youtube)
        return

    if args.apply_plan:
        direction = SyncDirection(args.direction)
        if direction == SyncDirection.YT_TO_SPOTIFY:
            sync_manager = TwoWaySync(None, spotify)
            workflow = sync_manager.apply_saved_youtube_to_spotify_plan(
                dry_run=args.dry_run
            )
            maybe_notify(build_run_summary(args, [workflow]), args.no_notify)
            return
        if direction == SyncDirection.SPOTIFY_TO_YT:
            youtube = authenticate_youtube(open_browser=open_browser)
            sync_manager = TwoWaySync(youtube, spotify)
            workflow = sync_manager.apply_saved_spotify_to_youtube_plan(
                dry_run=args.dry_run
            )
            maybe_notify(build_run_summary(args, [workflow]), args.no_notify)
            return
        raise ValueError("--apply-plan requires yt-to-spotify or spotify-to-yt")

    youtube = authenticate_youtube(open_browser=open_browser)
    sync_manager = TwoWaySync(youtube, spotify)
    summary = sync_manager.run_sync(
        direction=SyncDirection(args.direction),
        dry_run=args.dry_run,
        limit=args.limit,
        plan_only=args.plan_only,
    )
    maybe_notify(summary, args.no_notify)


def build_run_summary(args, workflows):
    return {
        "direction": args.direction,
        "mode": "apply-plan" if args.apply_plan else "sync",
        "dry_run": args.dry_run,
        "plan_only": args.plan_only,
        "workflows": workflows,
    }


def maybe_notify(summary, no_notify):
    if no_notify:
        return
    notify_sync_summary(summary)
