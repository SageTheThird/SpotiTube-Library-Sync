import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
client_id = os.getenv('SPOTIFY_CLIENT_ID')
client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
redirect_uri = os.getenv('SPOTIFY_REDIRECT_URI')
REDIRECT_URI = 'http://localhost:8080/callback'

# Spotify configuration
scope = "user-library-modify"

# YouTube configuration
YOUTUBE_CLIENT_SECRET_FILE = 'secrets.json'
YOUTUBE_API_SERVICE_NAME = 'youtube'
YOUTUBE_API_VERSION = 'v3'

# Cache Files
SPOTIFY_SEARCH_CACHE_FILE = 'spotify_already_searched_cache.json'
SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE = 'spotify_already_liked_cache.json'
YOUTUBE_LIKED_SONGS_CACHE_FILE = 'yt_liked_cache.csv'

# Constants
NUMBER_OF_LIKED_SONGS_TO_FETCH_FROM_YT = 200
NUMBER_OF_SONGS_TO_IMPORT_INTO_SPOTIFY = 200
