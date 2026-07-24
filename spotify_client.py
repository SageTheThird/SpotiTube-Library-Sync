import spotipy
from spotipy.oauth2 import SpotifyOAuth
import json
import logging
import time
from config import (
    client_id,
    client_secret,
    redirect_uri,
    scope,
    SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE,
    SPOTIFY_SEARCH_CACHE_FILE,
    USE_IMPROVED_MATCHING,
)
import csv
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth
import json
import time
import logging
import re
from Levenshtein import distance as levenshtein_distance
import concurrent.futures
import threading

# Initialize logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Spotify OAuth setup
sp = spotipy.Spotify(
    auth_manager=SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=scope,
        cache_path=".spotify_cache",
    )
)

# Lock for thread-safe cache access
cache_lock = threading.RLock()


def process_song(item, videos, search_cache_file):
    already_liked_songs = load_local_cache(SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE)
    track_name = ""
    track_id = None

    if USE_IMPROVED_MATCHING and videos:
        track_name = item["snippet"]["title"]
        track_id = find_best_match(item)
    else:
        track_name = item
        track_id = search_spotify(track_name, search_cache_file)

    if track_id and track_id not in already_liked_songs:
        logging.info(f"Found track on Spotify: {track_name}")
        return track_id
    elif track_id:
        logging.info(f"Already liked on Spotify: {track_name}")
    else:
        logging.warning(f"Track not found on Spotify: {track_name}")
    return None


def import_tracks_from_csv(
    file_path,
    max_songs=50,
    cache_file=SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE,
    search_cache_file=SPOTIFY_SEARCH_CACHE_FILE,
    videos=None,
):
    """
    Import tracks from a CSV file into Spotify, up to a specified limit, in reverse order.
    """
    items_to_process = []
    if USE_IMPROVED_MATCHING and videos:
        items_to_process = videos[:max_songs]
    else:
        with open(file_path, newline="", encoding="utf-8") as csvfile:
            reader = csv.reader(csvfile)
            next(reader)  # Skip header row
            items_to_process = [row[0] for row in reader]
            items_to_process.reverse()
            items_to_process = items_to_process[:max_songs]

    track_ids = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_song = {
            executor.submit(process_song, item, videos, search_cache_file): item
            for item in items_to_process
        }
        for future in concurrent.futures.as_completed(future_to_song):
            track_id = future.result()
            if track_id:
                track_ids.append(track_id)

    add_tracks_to_spotify(track_ids, cache_file)


def find_best_match(video):
    """
    Find the best Spotify match for a YouTube video using a scoring algorithm.
    """
    yt_title = video["snippet"]["title"]
    yt_channel = video["snippet"]["channelTitle"]
    yt_duration_str = video["contentDetails"]["duration"]

    # Convert ISO 8601 duration to seconds
    yt_duration = 0
    matches = re.match(r"PT(\d+H)?(\d+M)?(\d+S)?", yt_duration_str)
    if matches:
        h, m, s = matches.groups()
        if h:
            yt_duration += int(h[:-1]) * 3600
        if m:
            yt_duration += int(m[:-1]) * 60
        if s:
            yt_duration += int(s[:-1])

    potential_matches = search_spotify(yt_title)
    if not potential_matches:
        return None

    best_match = None
    highest_score = -1

    for sp_track in potential_matches:
        sp_title = sp_track["name"]
        sp_artists = [artist["name"] for artist in sp_track["artists"]]
        sp_duration = sp_track["duration_ms"] / 1000

        # Score calculation
        title_similarity = 1 - levenshtein_distance(yt_title.lower(), sp_title.lower()) / max(
            len(yt_title), len(sp_title)
        )

        artist_match_score = 0
        for artist in sp_artists:
            if artist.lower() in yt_channel.lower() or artist.lower() in yt_title.lower():
                artist_match_score = 1
                break

        duration_similarity = (
            1 - abs(yt_duration - sp_duration) / yt_duration if yt_duration > 0 else 0
        )

        # Weighted score
        score = (
            (title_similarity * 0.4)
            + (artist_match_score * 0.4)
            + (duration_similarity * 0.2)
        )

        if score > highest_score:
            highest_score = score
            best_match = sp_track

    if best_match:
        return best_match["id"]
    else:
        return None


def add_tracks_to_spotify(
    track_ids, cache_file=SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE, max_retries=3
):
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
                logging.info(
                    f"Added batch of tracks {start+1} to {end} to your Spotify Liked"
                )
                break
            except spotipy.SpotifyException as e:
                if e.http_status == 429:
                    retry_after = int(
                        e.headers.get("Retry-After", 10)
                    )  # Default to 10 seconds if header is missing
                    logging.warning(
                        f"Rate limit reached. Retrying after {retry_after} seconds."
                    )
                    time.sleep(retry_after)
                    retry_count += 1
                else:
                    logging.error(f"Spotify API error: {e}")
                    raise e

        for track_id in batch:
            update_local_cache(track_id, cache_file)


def get_all_saved_tracks(filename="spotify_liked_tracks.csv"):
    """
    Retrieves all saved tracks from a Spotify user and saves them to a CSV file.

    Args:
        sp: The Spotipy client object.
        filename: The name of the CSV file to save the tracks to.
    """

    offset = 0
    all_tracks = []
    total_tracks = None  # Initialize total_tracks

    try:
        with open(filename, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(
                [
                    "Artist",
                    "Track Name",
                    "Track ID",
                    "Album Name",
                    "Popularity",
                    "Added At",
                ]
            )  # Write header row

            while True:
                results = sp.current_user_saved_tracks(limit=50, offset=offset)

                if total_tracks is None:
                    total_tracks = results["total"]
                    print(f"Total tracks to retrieve: {total_tracks}")

                if not results["items"]:
                    break  # No more tracks

                for item in results["items"]:
                    track = item["track"]
                    artists = ", ".join(
                        [artist["name"] for artist in track["artists"]]
                    )  # Handle multiple artists
                    added_at = item.get("added_at")
                    writer.writerow(
                        [
                            artists,
                            track["name"],
                            track["id"],
                            track["album"]["name"],
                            track.get("popularity"),
                            added_at,
                        ]
                    )
                    # print(f"Saving: {artists} - {track['name']}") #Optional print statment for each track
                    all_tracks.append(track)

                offset += 50
                print(f"Retrieved {offset} of {total_tracks} tracks.")

                if offset >= total_tracks:
                    break
                time.sleep(0.5)  # Be nice to Spotify's API

        print(f"Successfully saved {len(all_tracks)} tracks to {filename}")

    except spotipy.exceptions.SpotifyException as e:
        print(f"Spotify API Error: {e}")
        if e.http_status == 429:  # Check for rate limiting
            print("Rate limit hit. Waiting and retrying...")
            time.sleep(60)  # Wait for a minute before retrying
            get_all_saved_tracks(sp, filename)  # Recursive call to retry
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


def load_spotify_search_cache(cache_file=SPOTIFY_SEARCH_CACHE_FILE):
    with cache_lock:
        try:
            with open(cache_file, "r") as file:
                return json.load(file)
        except FileNotFoundError:
            return {}


def update_spotify_search_cache(
    track_name, track_id, cache_file=SPOTIFY_SEARCH_CACHE_FILE
):
    with cache_lock:
        cache = load_spotify_search_cache(cache_file)
        cache[track_name] = track_id
        with open(cache_file, "w") as file:
            json.dump(cache, file)


def search_spotify(track_name, cache_file=SPOTIFY_SEARCH_CACHE_FILE, limit=5):
    with cache_lock:
        cache = load_spotify_search_cache(cache_file)
        if track_name in cache:
            cached_value = cache[track_name]
            if isinstance(cached_value, list):  # New format
                if USE_IMPROVED_MATCHING:
                    return cached_value
                else:
                    return cached_value[0]["id"] if cached_value else None
            # Old format (string), treat as cache miss and fall through

    results = sp.search(q=track_name, limit=limit, type="track")
    tracks = results["tracks"]["items"]

    with cache_lock:
        update_spotify_search_cache(track_name, tracks, cache_file)

    if not USE_IMPROVED_MATCHING:
        if tracks:
            return tracks[0]["id"]
        return None

    return tracks


def update_local_cache(song_id, cache_file="song_cache.json"):
    with cache_lock:
        try:
            cache = load_local_cache(cache_file)
            cache.add(song_id)
            with open(cache_file, "w") as file:
                json.dump(list(cache), file)
        except Exception as e:
            print(f"Error updating cache file: {e}")


def load_local_cache(cache_file=SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE):
    with cache_lock:
        try:
            with open(cache_file, "r") as file:
                return set(json.load(file))
        except FileNotFoundError:
            return set()
        except Exception as e:
            print(f"Error loading cache file: {e}")
            return set()


def get_spotify_liked_songs(limit=50, offset=0):
    """
    Get user's Spotify liked songs
    Returns list of {name, artist} dictionaries
    """
    results = sp.current_user_saved_tracks(limit=limit, offset=offset)
    songs = []
    for item in results["items"]:
        track = item["track"]
        songs.append(
            {
                "name": track["name"],
                "artists": [artist["name"] for artist in track["artists"]],
                "added_at": item["added_at"],
            }
        )
    return songs


def get_all_spotify_liked_songs(max_songs=200):
    """Get all liked songs up to max_songs limit"""
    all_songs = []
    offset = 0
    limit = 50  # Spotify API limit per request

    while len(all_songs) < max_songs:
        batch = get_spotify_liked_songs(limit=limit, offset=offset)
        if not batch:
            break
        all_songs.extend(batch)
        offset += limit

    return all_songs[:max_songs]
