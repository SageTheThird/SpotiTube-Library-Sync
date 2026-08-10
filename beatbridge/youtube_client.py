import os
import logging
from pathlib import Path
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from beatbridge.config import (
    YOUTUBE_CLIENT_SECRET_FILE,
    YOUTUBE_TOKEN_FILE,
    YOUTUBE_API_SERVICE_NAME,
    YOUTUBE_API_VERSION,
)


logger = logging.getLogger(__name__)
NON_RETRYABLE_RATE_REASONS = {
    "videoRatingDisabled",
    "forbidden",
    "videoNotFound",
}


def authenticate_youtube(open_browser=True):
    """
    Authenticate with YouTube API and return the YouTube service object.
    Returns:
        A built YouTube service object authenticated with user credentials."""
    scopes = ["https://www.googleapis.com/auth/youtube.force-ssl"]
    token_file = YOUTUBE_TOKEN_FILE
    credentials = None

    if os.path.exists(token_file):
        credentials = Credentials.from_authorized_user_file(token_file, scopes)
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
            except RefreshError as exc:
                if not open_browser:
                    raise RuntimeError(
                        "YouTube token refresh failed and browser auth is disabled. "
                        "Run once without --no-browser to reauthorize."
                    ) from exc
                credentials = None
        if not credentials or not credentials.valid:
            if not open_browser:
                raise RuntimeError(
                    "YouTube credentials are missing or expired. "
                    "Run once without --no-browser to authorize."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                YOUTUBE_CLIENT_SECRET_FILE, scopes
            )
            credentials = flow.run_local_server(port=8080, open_browser=open_browser)
        Path(token_file).parent.mkdir(parents=True, exist_ok=True)
        with open(token_file, "w") as token:
            token.write(credentials.to_json())

    return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, credentials=credentials)


# Retrieve your YouTube playlist
def get_liked_videos(youtube, max_results=100):
    """
    Fetch liked videos from YouTube and sort them by their published date in descending order.

    Parameters:
        max_results (int): Maximum number of liked videos to fetch.

    Returns:
        List of liked videos sorted by published date.
    """
    request = youtube.videos().list(
        part="snippet,contentDetails", myRating="like", maxResults=50
    )

    liked_videos = []
    while request and len(liked_videos) < max_results:
        response = request.execute()
        liked_videos += response.get("items", [])
        # Sort the videos by published date in descending order
        # liked_videos.sort(key=lambda video: video['snippet']['publishedAt'], reverse=True)
        request = youtube.videos().list_next(request, response)

    return liked_videos[:max_results]


def search_youtube_videos(youtube, query, max_results=5):
    """
    Search YouTube for videos and return result items.
    """
    try:
        search_response = (
            youtube.search()
            .list(q=query, part="id,snippet", maxResults=max_results, type="video")
            .execute()
        )
        return search_response.get("items", [])
    except Exception as e:
        print(f"YouTube search error: {e}")
        return []


def search_youtube(youtube, query, max_results=1):
    """
    Search YouTube for a track and return first result.
    Returns video ID if found, None otherwise.
    """
    items = search_youtube_videos(youtube, query, max_results=max_results)
    if items:
        return items[0]["id"]["videoId"]
    return None


def like_youtube_video(youtube, video_id):
    """Add video to liked videos on YouTube"""
    return like_youtube_video_result(youtube, video_id)["ok"]


def like_youtube_video_result(youtube, video_id):
    """Add video to liked videos on YouTube and return a structured result."""
    try:
        youtube.videos().rate(id=video_id, rating="like").execute()
        return {"ok": True, "reason": None, "message": None, "retryable": False}
    except HttpError as exc:
        reason = extract_youtube_error_reason(exc)
        logger.warning("YouTube rate failed for %s with reason %s", video_id, reason)
        return {
            "ok": False,
            "reason": reason,
            "message": str(exc),
            "retryable": reason not in NON_RETRYABLE_RATE_REASONS,
        }
    except Exception as exc:
        logger.warning("YouTube rate failed for %s: %s", video_id, exc)
        return {
            "ok": False,
            "reason": type(exc).__name__,
            "message": str(exc),
            "retryable": True,
        }


def extract_youtube_error_reason(exc):
    try:
        errors = exc.error_details
    except AttributeError:
        errors = None
    if errors:
        return errors[0].get("reason", "unknown")
    return "unknown"
