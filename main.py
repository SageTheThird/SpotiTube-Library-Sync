from youtube_client import authenticate_youtube, get_liked_videos
from spotify_client import import_tracks_from_csv
from utils import save_to_csv
from config import NUMBER_OF_LIKED_SONGS_TO_FETCH_FROM_YT, NUMBER_OF_SONGS_TO_IMPORT_INTO_SPOTIFY, YOUTUBE_LIKED_SONGS_CACHE_FILE

def main():
    youtube = authenticate_youtube()
    liked_videos = get_liked_videos(youtube, max_results=NUMBER_OF_LIKED_SONGS_TO_FETCH_FROM_YT) 
    save_to_csv(liked_videos)
    import_tracks_from_csv(YOUTUBE_LIKED_SONGS_CACHE_FILE, max_songs=NUMBER_OF_SONGS_TO_IMPORT_INTO_SPOTIFY)

if __name__ == '__main__':
    main()
