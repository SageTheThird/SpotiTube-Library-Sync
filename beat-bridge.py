import spotipy
import os
import csv
import re
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import json
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()
client_id = os.getenv('SPOTIFY_CLIENT_ID')
client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
redirect_uri = os.getenv('SPOTIFY_REDIRECT_URI')
REDIRECT_URI = 'http://localhost:8080/callback'

# Scope for modifying user's Liked Songs for Spotify
scope = "user-library-modify"

# YouTube credentials
YOUTUBE_CLIENT_SECRET_FILE = 'secrets.json'
YOUTUBE_API_SERVICE_NAME = 'youtube'
YOUTUBE_API_VERSION = 'v3'
NUMBER_OF_LIKED_SONGS_TO_FETCH_FROM_YT = 200
NUMBER_OF_SONGS_TO_IMPORT_INTO_SPOTIFY = 200

# Cache Files (to avoid hitting quota)
SPOTIFY_SEARCH_CACHE_FILE = 'spotify_already_searched_cache.json'
SPOTIFY_ALREADY_ADDED_SONGS_CACHCE_FILE = 'spotify_already_liked_cache.json'
YOUTUBE_LIKED_SONGS_CACHE_FILE = 'yt_liked_cache.csv'


# Spotify OAuth setup
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=client_id,
                                               client_secret=client_secret,
                                               redirect_uri=redirect_uri,
                                               scope=scope,
                                               cache_path=".spotify_cache"))


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
def get_liked_videos(max_results=100):
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

def clean_title(title, channel_title):
    """Clean the title by removing unwanted phrases and formatting"""
    # Removing phrases like "Official Music Video", "Official Video", etc.
    title = re.sub(r'\(Official.*?\)|\[Official.*?\]|- Official.*|Official Music Video|Official Video', '', title, flags=re.IGNORECASE)
    # Removing double quotes
    title = title.replace('"', '')
    # Appending channel title if '-' is not in the title
    if "-" not in title:
        title = f"{title} - {channel_title}"
    # Removing '- Topic' and trimming extra whitespace
    return title.replace('- Topic', '').strip()


def save_to_csv(videos, filename=YOUTUBE_LIKED_SONGS_CACHE_FILE):
    """Save the video data to a CSV file"""
    with open(filename, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Title'])

        for video in videos:
            title = video['snippet']['title']
            channel_title = video['snippet']['channelTitle']
            formatted_title = clean_title(title, channel_title)
            writer.writerow([formatted_title])


            
def add_tracks_to_spotify(track_ids, cache_file=SPOTIFY_ALREADY_ADDED_SONGS_CACHCE_FILE, max_retries=3):
    """
    Add tracks to Spotify in batches of up to 50 IDs and handle rate limits.
    """
    for start in range(0, len(track_ids), 50):
        end = start + 50
        batch = track_ids[start:end]
        retry_count = 0

        while retry_count < max_retries:
            try:
                sp.current_user_saved_tracks_add(tracks=batch)
                logging.info(f"Added batch of tracks {start+1} to {end} to your Spotify Liked")
                break
            except spotipy.SpotifyException as e:
                if e.http_status == 429:
                    retry_after = int(e.headers.get('Retry-After', 10))  # Default to 10 seconds if header is missing
                    logging.warning(f"Rate limit reached. Retrying after {retry_after} seconds.")
                    time.sleep(retry_after)
                    retry_count += 1
                else:
                    logging.error(f"Spotify API error: {e}")
                    raise e

        for track_id in batch:
            update_local_cache(track_id, cache_file)
        
def import_tracks_from_csv(file_path, max_songs=50, cache_file=SPOTIFY_ALREADY_ADDED_SONGS_CACHCE_FILE, search_cache_file=SPOTIFY_SEARCH_CACHE_FILE):
    """
    Import tracks from a CSV file into Spotify, up to a specified limit, in reverse order.

    Parameters:
        file_path (str): Path to the CSV file containing song titles.
        max_songs (int): Maximum number of songs to import into Spotify.
        cache_file (str): Path to the local cache file for already added songs.
        search_cache_file (str): Path to the local cache file for Spotify search results.
    """
    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        next(reader)  # Skip header row
        all_track_titles = [row[0] for row in reader]

    # Reverse the list and process up to max_songs
    track_titles_to_process = all_track_titles[::-1][:max_songs]

    track_ids = []
    for i, track_name in enumerate(track_titles_to_process, 1):  # Start counting from 1
        already_liked_songs = load_local_cache(cache_file)
        track_id = search_spotify(track_name, search_cache_file)

        if track_id and track_id not in already_liked_songs:
            track_ids.append(track_id)
            logging.info(f"Processing track #{i}: Found track on Spotify: {track_name}")
        elif track_id:
            logging.info(f"Processing track #{i}: Already liked on Spotify: {track_name}")
        else:
            logging.warning(f"Processing track #{i}: Track not found on Spotify: {track_name}")

    add_tracks_to_spotify(track_ids, cache_file)


def load_spotify_search_cache(cache_file=SPOTIFY_SEARCH_CACHE_FILE):
    try:
        with open(cache_file, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

def update_spotify_search_cache(track_name, track_id, cache_file=SPOTIFY_SEARCH_CACHE_FILE):
    cache = load_spotify_search_cache(cache_file)
    cache[track_name] = track_id
    with open(cache_file, 'w') as file:
        json.dump(cache, file)

def search_spotify(track_name, cache_file=SPOTIFY_SEARCH_CACHE_FILE):
    cache = load_spotify_search_cache(cache_file)
    if track_name in cache:
        return cache[track_name]
    
    results = sp.search(q=track_name, limit=1, type='track')
    tracks = results['tracks']['items']
    if tracks:
        track_id = tracks[0]['id']
        update_spotify_search_cache(track_name, track_id, cache_file)
        return track_id
    return None


def load_local_cache(cache_file=SPOTIFY_ALREADY_ADDED_SONGS_CACHCE_FILE):
    try:
        with open(cache_file, 'r') as file:
            return set(json.load(file))
    except FileNotFoundError:
        return set()
    except Exception as e:
        print(f"Error loading cache file: {e}")
        return set()

def update_local_cache(song_id, cache_file='song_cache.json'):
    try:
        cache = load_local_cache(cache_file)
        cache.add(song_id)
        with open(cache_file, 'w') as file:
            json.dump(list(cache), file)
    except Exception as e:
        print(f"Error updating cache file: {e}")


# Main script
if __name__ == '__main__':
    youtube = authenticate_youtube()
    liked_videos = get_liked_videos(max_results=NUMBER_OF_LIKED_SONGS_TO_FETCH_FROM_YT) 
    save_to_csv(liked_videos)

    import_tracks_from_csv(YOUTUBE_LIKED_SONGS_CACHE_FILE, max_songs=NUMBER_OF_SONGS_TO_IMPORT_INTO_SPOTIFY) 



