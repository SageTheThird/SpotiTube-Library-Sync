import spotipy
from spotipy.oauth2 import SpotifyOAuth
import json
import logging
import time
from config import client_id, client_secret, redirect_uri, scope, SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE, SPOTIFY_SEARCH_CACHE_FILE
import csv
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth
import json
import time
import logging

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Spotify OAuth setup
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=client_id,
                                               client_secret=client_secret,
                                               redirect_uri=redirect_uri,
                                               scope=scope,
                                               cache_path=".spotify_cache"))

# ... (Include the Spotify-related functions from the original script)
def import_tracks_from_csv(file_path, max_songs=50, cache_file=SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE, search_cache_file=SPOTIFY_SEARCH_CACHE_FILE):
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


def add_tracks_to_spotify(track_ids, cache_file=SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE, max_retries=3):
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

def update_local_cache(song_id, cache_file='song_cache.json'):
    try:
        cache = load_local_cache(cache_file)
        cache.add(song_id)
        with open(cache_file, 'w') as file:
            json.dump(list(cache), file)
    except Exception as e:
        print(f"Error updating cache file: {e}")

def load_local_cache(cache_file=SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE):
    try:
        with open(cache_file, 'r') as file:
            return set(json.load(file))
    except FileNotFoundError:
        return set()
    except Exception as e:
        print(f"Error loading cache file: {e}")
        return set()