import argparse
import logging

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from beatbridge.config import (
    NUMBER_OF_LIKED_SONGS_TO_FETCH_FROM_YT,
    SPOTIFY_AUTH_CACHE_FILE,
    client_id,
    client_secret,
    redirect_uri,
    scope,
    youtube_to_youtube_sync_file,
)
from beatbridge.notifier import notify_sync_summary
from beatbridge.storage import load_json_file
from beatbridge.sync_manager import SyncDirection, TwoWaySync
from beatbridge.youtube_client import authenticate_youtube, get_liked_video_ids
from beatbridge.youtube_to_youtube import (
    apply_youtube_to_youtube_plan,
    build_youtube_to_youtube_plan,
)


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
        "--youtube-profile",
        help="Named YouTube profile token to use for the YouTube side of the sync.",
    )
    parser.add_argument(
        "--source-youtube-profile",
        help="Named source YouTube profile for yt-to-yt syncs.",
    )
    parser.add_argument(
        "--target-youtube-profile",
        help="Named target YouTube profile for yt-to-yt and spotify-to-yt syncs.",
    )
    parser.add_argument(
        "--check-auth",
        action="store_true",
        help="Validate Spotify and YouTube auth, then exit without syncing.",
    )
    parser.add_argument(
        "--check-youtube-auth",
        action="store_true",
        help="Validate YouTube auth for the selected profile, then exit without syncing.",
    )
    parser.add_argument(
        "--include-reverse-imports",
        action="store_true",
        help="For Spotify-to-YouTube, include tracks originally imported from YouTube.",
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


def check_auth(spotify, youtube, youtube_profile=None):
    spotify_user = spotify.current_user()
    check_youtube_auth(youtube, youtube_profile)
    logging.info("Spotify auth OK for %s", spotify_user.get("display_name"))


def check_youtube_auth(youtube, youtube_profile=None):
    response = youtube.channels().list(
        part="id,snippet",
        mine=True,
        maxResults=1,
    ).execute()
    channel = response.get("items", [{}])[0]
    title = channel.get("snippet", {}).get("title") or channel.get("id") or "unknown"
    profile_suffix = f" for profile {youtube_profile}" if youtube_profile else ""
    logging.info("YouTube auth OK%s: %s", profile_suffix, title)


def main(argv=None):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    args = parse_args(argv)
    open_browser = not args.no_browser

    youtube_profile = selected_youtube_profile(args)

    if args.check_youtube_auth:
        youtube = authenticate_youtube(
            open_browser=open_browser,
            profile=youtube_profile,
        )
        check_youtube_auth(youtube, youtube_profile)
        return

    if args.check_auth:
        spotify = build_spotify_client(open_browser=open_browser)
        youtube = authenticate_youtube(open_browser=open_browser, profile=youtube_profile)
        check_auth(spotify, youtube, youtube_profile)
        return

    direction = SyncDirection(args.direction)

    if direction == SyncDirection.YT_TO_YT and not args.apply_plan:
        workflow = run_youtube_to_youtube(args, open_browser)
        maybe_notify(build_run_summary(args, [workflow]), args.no_notify)
        return

    if direction == SyncDirection.YT_TO_YT and args.apply_plan:
        workflow = apply_youtube_to_youtube(args, open_browser)
        maybe_notify(build_run_summary(args, [workflow]), args.no_notify)
        return

    spotify = build_spotify_client(open_browser=open_browser)

    if args.apply_plan:
        if direction == SyncDirection.YT_TO_SPOTIFY:
            sync_manager = TwoWaySync(None, spotify)
            workflow = sync_manager.apply_saved_youtube_to_spotify_plan(
                dry_run=args.dry_run
            )
            maybe_notify(build_run_summary(args, [workflow]), args.no_notify)
            return
        if direction == SyncDirection.SPOTIFY_TO_YT:
            target_profile = selected_target_youtube_profile(args)
            youtube = authenticate_youtube(
                open_browser=open_browser,
                profile=target_profile,
            )
            sync_manager = TwoWaySync(youtube, spotify, youtube_profile=target_profile)
            workflow = sync_manager.apply_saved_spotify_to_youtube_plan(
                dry_run=args.dry_run
            )
            maybe_notify(build_run_summary(args, [workflow]), args.no_notify)
            return
        raise ValueError("--apply-plan requires yt-to-spotify, spotify-to-yt, or yt-to-yt")

    youtube = authenticate_youtube(open_browser=open_browser, profile=youtube_profile)
    sync_manager = TwoWaySync(youtube, spotify, youtube_profile=youtube_profile)
    summary = sync_manager.run_sync(
        direction=direction,
        dry_run=args.dry_run,
        limit=args.limit,
        plan_only=args.plan_only,
        skip_reverse_imports=not args.include_reverse_imports,
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


def selected_youtube_profile(args):
    return args.target_youtube_profile or args.youtube_profile


def selected_target_youtube_profile(args):
    return args.target_youtube_profile or args.youtube_profile


def selected_youtube_pair(args):
    source_profile = args.source_youtube_profile
    target_profile = args.target_youtube_profile or args.youtube_profile
    if not source_profile or not target_profile:
        raise ValueError(
            "yt-to-yt requires --source-youtube-profile and --target-youtube-profile"
        )
    if source_profile == target_profile:
        raise ValueError("yt-to-yt source and target profiles must be different")
    return source_profile, target_profile


def load_sync_cache(cache_file):
    data = load_json_file(cache_file, default=None)
    if not data:
        data = {"last_sync": None, "synced_items": []}
    data.setdefault("synced_items", [])
    data.setdefault("blocked_items", [])
    data["cache_file"] = cache_file
    return data


def run_youtube_to_youtube(args, open_browser):
    source_profile, target_profile = selected_youtube_pair(args)
    sync_cache = load_sync_cache(
        youtube_to_youtube_sync_file(source_profile, target_profile)
    )

    source_youtube = authenticate_youtube(
        open_browser=open_browser,
        profile=source_profile,
    )
    target_youtube = None
    target_liked_youtube_ids = set()
    if not args.plan_only:
        target_youtube = authenticate_youtube(
            open_browser=open_browser,
            profile=target_profile,
        )
        target_liked_youtube_ids = get_liked_video_ids(
            target_youtube,
            max_results=args.limit or NUMBER_OF_LIKED_SONGS_TO_FETCH_FROM_YT,
        )

    plan = build_youtube_to_youtube_plan(
        source_youtube,
        source_profile,
        target_profile,
        sync_cache,
        limit=args.limit,
        target_liked_youtube_ids=target_liked_youtube_ids,
    )
    if args.plan_only:
        return youtube_to_youtube_workflow(
            source_profile,
            target_profile,
            dry_run=args.dry_run,
            plan_only=True,
            processed=0,
            planned=plan["summary"].get("pending", 0),
            source_items=plan["summary"].get("items", 0),
            skipped=plan["summary"].get("already_synced", 0)
            + plan["summary"].get("already_liked_on_target", 0)
            + plan["summary"].get("blocked_youtube_rating", 0),
        )

    video_ids = apply_youtube_to_youtube_plan(
        target_youtube,
        source_profile,
        target_profile,
        sync_cache,
        dry_run=args.dry_run,
    )
    return youtube_to_youtube_workflow(
        source_profile,
        target_profile,
        dry_run=args.dry_run,
        plan_only=False,
        processed=len(video_ids),
        planned=plan["summary"].get("pending", 0),
        source_items=plan["summary"].get("items", 0),
        skipped=plan["summary"].get("already_synced", 0)
        + plan["summary"].get("blocked_youtube_rating", 0),
    )


def apply_youtube_to_youtube(args, open_browser):
    source_profile, target_profile = selected_youtube_pair(args)
    sync_cache = load_sync_cache(
        youtube_to_youtube_sync_file(source_profile, target_profile)
    )
    target_youtube = authenticate_youtube(
        open_browser=open_browser,
        profile=target_profile,
    )
    video_ids = apply_youtube_to_youtube_plan(
        target_youtube,
        source_profile,
        target_profile,
        sync_cache,
        dry_run=args.dry_run,
    )
    return youtube_to_youtube_workflow(
        source_profile,
        target_profile,
        dry_run=args.dry_run,
        plan_only=False,
        processed=len(video_ids),
        planned=0,
        source_items=None,
        skipped=None,
    )


def youtube_to_youtube_workflow(
    source_profile,
    target_profile,
    dry_run,
    plan_only,
    processed,
    planned,
    source_items,
    skipped,
):
    workflow = {
        "direction": SyncDirection.YT_TO_YT.value,
        "label": f"YouTube ({source_profile}) -> YouTube ({target_profile})",
        "dry_run": dry_run,
        "plan_only": plan_only,
        "processed": processed,
        "planned": planned,
    }
    if source_items is not None:
        workflow["source_items"] = source_items
    if skipped is not None:
        workflow["skipped"] = skipped
    return workflow
