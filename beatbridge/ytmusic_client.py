import logging
import json
from pathlib import Path

from ytmusicapi import OAuthCredentials, YTMusic, setup, setup_oauth

from beatbridge.config import (
    YTMUSIC_CLIENT_ID,
    YTMUSIC_CLIENT_SECRET,
    ytmusic_browser_file,
    ytmusic_oauth_file,
    ytmusic_raw_headers_file,
)


logger = logging.getLogger(__name__)


def build_ytmusic_client(profile=None):
    browser_file = ytmusic_browser_file(profile)
    if Path(browser_file).exists():
        return YTMusic(browser_file)

    auth_file = ytmusic_oauth_file(profile)
    if Path(auth_file).exists():
        return YTMusic(
            auth_file,
            oauth_credentials=ytmusic_oauth_credentials(),
        )

    raise RuntimeError(
        f"YouTube Music auth is missing for profile {profile or 'default'}. "
        "Run --setup-ytmusic-auth or --setup-ytmusic-browser-auth once for that profile."
    )


def setup_ytmusic_browser_auth(profile=None):
    raw_headers_file = ytmusic_raw_headers_file(profile)
    browser_file = ytmusic_browser_file(profile)
    if not Path(raw_headers_file).exists():
        raise RuntimeError(
            f"Raw YouTube Music headers are missing at {raw_headers_file}. "
            "Save copied request headers there, then rerun --setup-ytmusic-browser-auth."
        )
    raw_headers = Path(raw_headers_file).read_text(encoding="utf-8")
    Path(browser_file).parent.mkdir(parents=True, exist_ok=True)
    setup(filepath=browser_file, headers_raw=raw_headers)
    sanitize_browser_auth_file(browser_file)
    logger.info(
        "YouTube Music browser auth saved for %s at %s",
        profile or "default",
        browser_file,
    )
    return build_ytmusic_client(profile)


def sanitize_browser_auth_file(browser_file):
    auth_path = Path(browser_file)
    headers = json.loads(auth_path.read_text(encoding="utf-8"))
    drop_headers = {
        "content-encoding",
        "content-length",
        "accept-encoding",
        "priority",
        "cache-control",
        "pragma",
        "decoded",
    }
    sanitized = {}
    for key, value in headers.items():
        lower_key = key.lower()
        if lower_key in drop_headers:
            continue
        if lower_key.startswith(":"):
            continue
        if lower_key.startswith("/"):
            continue
        if "\n" in key or "\r" in key:
            continue
        if key in {"music.youtube.com"}:
            continue
        sanitized[key] = value

    auth_path.write_text(
        json.dumps(sanitized, ensure_ascii=True, indent=4, sort_keys=True),
        encoding="utf-8",
    )


def setup_ytmusic_auth(profile=None, open_browser=True):
    auth_file = ytmusic_oauth_file(profile)
    Path(auth_file).parent.mkdir(parents=True, exist_ok=True)
    setup_oauth(
        client_id=YTMUSIC_CLIENT_ID,
        client_secret=YTMUSIC_CLIENT_SECRET,
        filepath=auth_file,
        open_browser=open_browser,
    )
    logger.info("YouTube Music auth saved for %s at %s", profile or "default", auth_file)
    return build_ytmusic_client(profile)


def ytmusic_oauth_credentials():
    if not YTMUSIC_CLIENT_ID or not YTMUSIC_CLIENT_SECRET:
        raise RuntimeError("YTMUSIC_CLIENT_ID and YTMUSIC_CLIENT_SECRET are required")
    return OAuthCredentials(
        client_id=YTMUSIC_CLIENT_ID,
        client_secret=YTMUSIC_CLIENT_SECRET,
    )


def check_ytmusic_auth(ytmusic, profile=None):
    liked = ytmusic.get_liked_songs(limit=1)
    count = len(liked.get("tracks", []))
    logger.info(
        "YouTube Music auth OK for profile %s; liked-song probe returned %s item(s)",
        profile or "default",
        count,
    )
    return liked
