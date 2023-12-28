import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from config import YOUTUBE_CLIENT_SECRET_FILE, YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION

def authenticate_youtube():
    """
    Authenticate with YouTube API and return the YouTube service object.
    Returns:
        A built YouTube service object authenticated with user credentials. """
    scopes = ["https://www.googleapis.com/auth/youtube.force-ssl"]
    token_file = 'token.json'
    credentials = None

    if os.path.exists(token_file):
        credentials = Credentials.from_authorized_user_file(token_file, scopes)
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(YOUTUBE_CLIENT_SECRET_FILE, scopes)
            credentials = flow.run_local_server(port=8080)
        with open(token_file, 'w') as token:
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
        part="snippet,contentDetails",
        myRating="like",
        maxResults=50
    )

    liked_videos = []
    while request and len(liked_videos) < max_results:
        response = request.execute()
        liked_videos += response.get("items", [])
        # Sort the videos by published date in descending order
        # liked_videos.sort(key=lambda video: video['snippet']['publishedAt'], reverse=True)
        request = youtube.videos().list_next(request, response)

    return liked_videos[:max_results]
