# from youtube_client import authenticate_youtube, get_liked_videos
# from spotify_client import import_tracks_from_csv
# from utils import save_to_csv
# from config import (
#     NUMBER_OF_LIKED_SONGS_TO_FETCH_FROM_YT,
#     NUMBER_OF_SONGS_TO_IMPORT_INTO_SPOTIFY,
#     YOUTUBE_LIKED_SONGS_CACHE_FILE,
# )


# def main():
#     # add_tracks_to_youtube()
#     # return
#     youtube = authenticate_youtube()
#     liked_videos = get_liked_videos(
#         youtube, max_results=NUMBER_OF_LIKED_SONGS_TO_FETCH_FROM_YT
#     )
#     save_to_csv(liked_videos)
#     import_tracks_from_csv(
#         YOUTUBE_LIKED_SONGS_CACHE_FILE, max_songs=NUMBER_OF_SONGS_TO_IMPORT_INTO_SPOTIFY
#     )


# if __name__ == "__main__":
#     main()

from youtube_client import authenticate_youtube, get_liked_videos
from spotify_client import import_tracks_from_csv
from utils import save_to_csv
from sync_manager import TwoWaySync
from config import (
    NUMBER_OF_LIKED_SONGS_TO_FETCH_FROM_YT,
    NUMBER_OF_SONGS_TO_IMPORT_INTO_SPOTIFY,
)
from config import (
    client_id,
    client_secret,
    redirect_uri,
    scope,
    SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE,
    SPOTIFY_SEARCH_CACHE_FILE,
)
import spotipy

from spotipy.oauth2 import SpotifyOAuth


def main():
    # Initialize clients
    youtube = authenticate_youtube()
    sp = spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            cache_path=".spotify_cache",
        )
    )

    # Create sync manager
    sync_manager = TwoWaySync(youtube, sp)

    # Run two-way sync
    sync_manager.run_two_way_sync()


if __name__ == "__main__":
    main()
