import json
import os
import logging
import webbrowser
import wsgiref.simple_server
from pathlib import Path
from urllib.parse import urlparse

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from beatbridge.config import (
    YOUTUBE_CLIENT_SECRET_FILE,
    YOUTUBE_API_SERVICE_NAME,
    YOUTUBE_API_VERSION,
    youtube_token_file,
)


logger = logging.getLogger(__name__)
NON_RETRYABLE_RATE_REASONS = {
    "videoRatingDisabled",
    "forbidden",
    "videoNotFound",
}


def authenticate_youtube(open_browser=True, profile=None):
    """
    Authenticate with YouTube API and return the YouTube service object.
    Returns:
        A built YouTube service object authenticated with user credentials."""
    scopes = ["https://www.googleapis.com/auth/youtube.force-ssl"]
    token_file = youtube_token_file(profile)
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
            credentials = run_youtube_oauth(flow, open_browser=open_browser)
        Path(token_file).parent.mkdir(parents=True, exist_ok=True)
        with open(token_file, "w") as token:
            token.write(credentials.to_json())

    return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, credentials=credentials)


def run_youtube_oauth(flow, open_browser=True):
    redirect_uri = configured_local_redirect_uri()
    if not redirect_uri:
        return flow.run_local_server(port=8080, open_browser=open_browser)

    parsed = urlparse(redirect_uri)
    if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1"):
        return flow.run_local_server(port=8080, open_browser=open_browser)

    port = parsed.port or 80
    return run_local_server_with_redirect(
        flow,
        host=parsed.hostname,
        port=port,
        redirect_uri=redirect_uri,
        open_browser=open_browser,
    )


def configured_local_redirect_uri():
    try:
        with open(YOUTUBE_CLIENT_SECRET_FILE, "r", encoding="utf-8") as file:
            config = json.load(file)
    except (OSError, json.JSONDecodeError):
        return None

    client_config = config.get("web") or config.get("installed") or {}
    for redirect_uri in client_config.get("redirect_uris", []):
        parsed = urlparse(redirect_uri)
        if parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1"):
            return redirect_uri
    return None


def run_local_server_with_redirect(
    flow,
    host,
    port,
    redirect_uri,
    open_browser=True,
    success_message="The authentication flow has completed. You may close this window.",
):
    wsgi_app = LocalOAuthRedirectApp(success_message)
    wsgiref.simple_server.WSGIServer.allow_reuse_address = False
    local_server = wsgiref.simple_server.make_server(
        host,
        port,
        wsgi_app,
        handler_class=QuietWSGIRequestHandler,
    )

    try:
        flow.redirect_uri = redirect_uri
        auth_url, _ = flow.authorization_url(prompt="consent")

        if open_browser:
            webbrowser.open(auth_url, new=1, autoraise=True)

        print(f"Please visit this URL to authorize this application: {auth_url}")
        local_server.handle_request()

        try:
            authorization_response = wsgi_app.last_request_uri.replace(
                "http",
                "https",
                1,
            )
        except AttributeError as exc:
            raise TimeoutError(
                "Timed out waiting for response from authorization server"
            ) from exc

        flow.fetch_token(authorization_response=authorization_response)
    finally:
        local_server.server_close()

    return flow.credentials


class LocalOAuthRedirectApp:
    def __init__(self, success_message):
        self.last_request_uri = None
        self.success_message = success_message

    def __call__(self, environ, start_response):
        start_response("200 OK", [("Content-type", "text/plain; charset=utf-8")])
        self.last_request_uri = wsgiref.util.request_uri(environ)
        return [self.success_message.encode("utf-8")]


class QuietWSGIRequestHandler(wsgiref.simple_server.WSGIRequestHandler):
    def log_message(self, format, *args):
        logger.info(format, *args)


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


def get_liked_video_ids(youtube, max_results=100):
    video_ids = []
    for video in get_liked_videos(youtube, max_results=max_results):
        video_id = extract_video_id(video)
        if video_id:
            video_ids.append(video_id)
    return set(video_ids)


def extract_video_id(video):
    video_id = video.get("id")
    if isinstance(video_id, dict):
        return video_id.get("videoId")
    return video_id


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
