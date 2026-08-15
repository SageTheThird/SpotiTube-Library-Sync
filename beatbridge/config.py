import os
import re
from pathlib import Path

from dotenv import load_dotenv

# Paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Load environment variables before reading configurable paths.
load_dotenv(PROJECT_ROOT / ".env")
DATA_DIR = Path(os.getenv("BEATBRIDGE_DATA_DIR", PROJECT_ROOT / "data"))
AUTH_DIR = DATA_DIR / "auth"
CACHE_DIR = DATA_DIR / "cache"
SPOTIFY_CACHE_DIR = CACHE_DIR / "spotify"
YOUTUBE_CACHE_DIR = CACHE_DIR / "youtube"
PLAN_DIR = DATA_DIR / "plans"
SYNC_DIR = DATA_DIR / "sync"
EXPORT_DIR = DATA_DIR / "exports"
LOG_DIR = DATA_DIR / "logs"
ARCHIVE_DIR = DATA_DIR / "archive"
for directory in (
    AUTH_DIR,
    SPOTIFY_CACHE_DIR,
    YOUTUBE_CACHE_DIR,
    PLAN_DIR,
    SYNC_DIR,
    EXPORT_DIR,
    LOG_DIR,
    ARCHIVE_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)

client_id = os.getenv("SPOTIFY_CLIENT_ID")
client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")
REDIRECT_URI = "http://localhost:8080/callback"
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
NOTIFY_ON_PLAN_ONLY = os.getenv("NOTIFY_ON_PLAN_ONLY", "false").lower() in (
    "1",
    "true",
    "yes",
)

# Spotify configuration
scope = "user-library-modify,user-library-read"

# YouTube configuration
YOUTUBE_CLIENT_SECRET_FILE = os.getenv(
    "YOUTUBE_CLIENT_SECRET_FILE", str(AUTH_DIR / "secrets.json")
)
YOUTUBE_TOKEN_FILE = os.getenv("YOUTUBE_TOKEN_FILE", str(AUTH_DIR / "token.json"))
DEFAULT_YOUTUBE_PROFILE = os.getenv("DEFAULT_YOUTUBE_PROFILE", "").strip() or None
YTMUSIC_CLIENT_ID = os.getenv("YTMUSIC_CLIENT_ID")
YTMUSIC_CLIENT_SECRET = os.getenv("YTMUSIC_CLIENT_SECRET")
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

# Cache Files
SPOTIFY_AUTH_CACHE_FILE = os.getenv(
    "SPOTIFY_AUTH_CACHE_FILE", str(AUTH_DIR / "spotify_cache")
)
SPOTIFY_SEARCH_CACHE_FILE = str(SPOTIFY_CACHE_DIR / "search_queries.jsonl")
SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE = str(SPOTIFY_CACHE_DIR / "liked_track_ids.json")
YOUTUBE_SEARCH_CACHE_FILE = str(YOUTUBE_CACHE_DIR / "search_queries.jsonl")
LEGACY_SPOTIFY_SEARCH_CACHE_FILE = str(CACHE_DIR / "spotify_search_cache.json")
LEGACY_SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE = str(
    CACHE_DIR / "spotify_liked_cache.json"
)
LEGACY_YOUTUBE_SEARCH_CACHE_FILE = str(CACHE_DIR / "youtube_search_cache.json")
SPOTIFY_IMPORT_PLAN_FILE = str(PLAN_DIR / "yt_to_spotify_plan.json")
SPOTIFY_TO_YOUTUBE_PLAN_FILE = str(PLAN_DIR / "spotify_to_youtube_plan.json")
YT_TO_SPOTIFY_SYNC_FILE = str(SYNC_DIR / "yt_to_spotify_sync.json")
SPOTIFY_TO_YT_SYNC_FILE = str(SYNC_DIR / "spotify_to_yt_sync.json")
YOUTUBE_LIKED_SONGS_CACHE_FILE = str(EXPORT_DIR / "yt_liked_cache.csv")
SPOTIFY_LIKED_TRACKS_EXPORT_FILE = str(EXPORT_DIR / "spotify_liked_tracks.csv")

# Constants
NUMBER_OF_LIKED_SONGS_TO_FETCH_FROM_YT = 200
NUMBER_OF_SONGS_TO_IMPORT_INTO_SPOTIFY = 200
USE_IMPROVED_MATCHING = True
SPOTIFY_MATCH_SCORE_THRESHOLD = float(
    os.getenv("SPOTIFY_MATCH_SCORE_THRESHOLD", "0.55")
)
SPOTIFY_ADD_BATCH_SIZE = int(os.getenv("SPOTIFY_ADD_BATCH_SIZE", "20"))
SPOTIFY_SEARCH_WORKERS = int(os.getenv("SPOTIFY_SEARCH_WORKERS", "2"))
YOUTUBE_SEARCH_WORKERS = int(os.getenv("YOUTUBE_SEARCH_WORKERS", "1"))
YOUTUBE_MATCH_SCORE_THRESHOLD = float(
    os.getenv("YOUTUBE_MATCH_SCORE_THRESHOLD", "0.65")
)


def safe_profile_name(profile):
    if not profile:
        return None
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", profile.strip().lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    if not normalized:
        raise ValueError("YouTube profile name cannot be empty")
    return normalized


def profile_env_name(prefix, profile):
    safe = safe_profile_name(profile).replace("-", "_").upper()
    return f"{prefix}_{safe}"


def youtube_token_file(profile=None):
    safe = safe_profile_name(profile or DEFAULT_YOUTUBE_PROFILE)
    if not safe:
        return YOUTUBE_TOKEN_FILE
    return os.getenv(
        profile_env_name("YOUTUBE_TOKEN_FILE", safe),
        str(AUTH_DIR / f"youtube-{safe}-token.json"),
    )


def youtube_liked_songs_cache_file(profile=None):
    safe = safe_profile_name(profile)
    if not safe:
        return YOUTUBE_LIKED_SONGS_CACHE_FILE
    return str(EXPORT_DIR / f"yt_liked_{safe}_cache.csv")


def spotify_to_youtube_plan_file(profile=None):
    safe = safe_profile_name(profile)
    if not safe:
        return SPOTIFY_TO_YOUTUBE_PLAN_FILE
    return str(PLAN_DIR / f"spotify_to_youtube_{safe}_plan.json")


def spotify_to_youtube_sync_file(profile=None):
    safe = safe_profile_name(profile)
    if not safe:
        return SPOTIFY_TO_YT_SYNC_FILE
    return str(SYNC_DIR / f"spotify_to_yt_{safe}_sync.json")


def youtube_to_youtube_plan_file(source_profile, target_profile):
    source = safe_profile_name(source_profile)
    target = safe_profile_name(target_profile)
    return str(PLAN_DIR / f"youtube_{source}_to_youtube_{target}_plan.json")


def youtube_to_youtube_sync_file(source_profile, target_profile):
    source = safe_profile_name(source_profile)
    target = safe_profile_name(target_profile)
    return str(SYNC_DIR / f"youtube_{source}_to_youtube_{target}_sync.json")


def ytmusic_oauth_file(profile=None):
    safe = safe_profile_name(profile or DEFAULT_YOUTUBE_PROFILE)
    if not safe:
        return str(AUTH_DIR / "ytmusic-oauth.json")
    return os.getenv(
        profile_env_name("YTMUSIC_OAUTH_FILE", safe),
        str(AUTH_DIR / f"ytmusic-{safe}-oauth.json"),
    )


def ytmusic_browser_file(profile=None):
    safe = safe_profile_name(profile or DEFAULT_YOUTUBE_PROFILE)
    if not safe:
        return str(AUTH_DIR / "ytmusic-browser.json")
    return os.getenv(
        profile_env_name("YTMUSIC_BROWSER_FILE", safe),
        str(AUTH_DIR / f"ytmusic-{safe}-browser.json"),
    )


def ytmusic_raw_headers_file(profile=None):
    safe = safe_profile_name(profile or DEFAULT_YOUTUBE_PROFILE)
    if not safe:
        return str(AUTH_DIR / "ytmusic-headers.txt")
    return str(AUTH_DIR / f"ytmusic-{safe}-headers.txt")


def ytmusic_to_ytmusic_plan_file(source_profile, target_profile, source_kind):
    source = safe_profile_name(source_profile)
    target = safe_profile_name(target_profile)
    kind = safe_profile_name(source_kind)
    return str(PLAN_DIR / f"ytmusic_{source}_to_ytmusic_{target}_{kind}_plan.json")


def ytmusic_to_ytmusic_sync_file(source_profile, target_profile, source_kind):
    source = safe_profile_name(source_profile)
    target = safe_profile_name(target_profile)
    kind = safe_profile_name(source_kind)
    return str(SYNC_DIR / f"ytmusic_{source}_to_ytmusic_{target}_{kind}_sync.json")
