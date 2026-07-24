# Improved Song Matching Feature

This document outlines the plan to implement an improved song matching feature for BeatBridge, ensuring backward compatibility with the existing system.

## 1. Current Matching Logic

The current matching logic is straightforward but has limitations:

-   It primarily relies on the cleaned-up title of a YouTube video to search for a track on Spotify.
-   The `clean_title` function in `utils.py` removes common superfluous text like "(Official Music Video)" and appends the channel title if a hyphen is not present.
-   The `search_spotify` function in `spotify_client.py` then uses the cleaned title to search on Spotify and picks the first result.

This approach is fast but can be inaccurate, especially for songs with common names, remixes, or covers.

## 2. Proposed Improvements

To improve matching accuracy, we will move to a more sophisticated, score-based system that leverages more metadata from both YouTube and Spotify.

### Metadata to be Used:

-   **From YouTube:**
    -   Video Title
    -   Video Description (often contains track and artist information)
    -   Channel Title (often the artist's name)
-   **From Spotify:**
    -   Track Name
    -   Artist Name(s)
    -   Album Name
    -   Track Duration

### Scoring Algorithm:

We will implement a new function, `find_best_match`, which will take the metadata of a YouTube video and return the best-matching Spotify track. The algorithm will work as follows:

1.  **Initial Search:** Perform a search on Spotify using the cleaned YouTube video title, but instead of just taking the first result, we will retrieve the top 5-10 results.
2.  **Scoring:** For each potential match from Spotify, a score will be calculated based on the following criteria:
    -   **Title Similarity:** Use a string similarity algorithm (e.g., Levenshtein distance) to compare the cleaned YouTube title with the Spotify track name.
    -   **Artist Match:** Check if the YouTube channel title or artist names mentioned in the video description match the artist(s) of the Spotify track. This will be a significant part of the score.
    -   **Album Match:** If the album name is mentioned in the YouTube video's metadata, compare it with the Spotify track's album name.
    -   **Duration Similarity:** Compare the duration of the YouTube video with the Spotify track's duration. A small difference will result in a higher score.
3.  **Best Match Selection:** The Spotify track with the highest score will be selected as the best match. A minimum score threshold will be established to avoid false positives.

## 3. Implementation Steps

The implementation will be broken down into the following steps:

1.  **`youtube_client.py` modifications:**
    -   Update the `get_liked_videos` function to retrieve more metadata for each video, including the description and duration. The YouTube API's `videos().list` endpoint can provide this information.

2.  **`spotify_client.py` modifications:**
    -   Modify the `search_spotify` function to return a list of potential matches (e.g., the top 5) instead of just the first one. Each item in the list should include the track name, artist(s), album, and duration.
    -   Create a new function, `find_best_match`, that implements the scoring algorithm described above. This function will take the YouTube video metadata as input and use the modified `search_spotify` to find and score potential matches.
    -   Update the `import_tracks_from_csv` function to use `find_best_match` instead of the old `search_spotify` logic.

3.  **`utils.py` modifications:**
    -   Enhance the `clean_title` function to be more robust in extracting artist and track names from video titles. This could involve using more advanced regex or pattern matching.
    -   Add a new function to calculate the string similarity score (e.g., Levenshtein distance).

## 4. Backwards Compatibility

To ensure backward compatibility, the following measures will be taken:

-   **Configuration Flag:** A new option will be added to `config.py`, such as `USE_IMPROVED_MATCHING = True`. This will allow users to switch between the old and new matching logic. The `import_tracks_from_csv` function will check this flag to decide which matching method to use.
-   **Cache Compatibility:** The existing cache files (`spotify_already_searched_cache.json` and `spotify_already_liked_cache.json`) will continue to work as they are. The new logic will still result in a Spotify track ID, which is what the cache stores. No changes to the cache structure are needed.
-   **Default Behavior:** The default behavior will be to use the new improved matching logic, but the option to fall back to the old logic will be maintained for users who prefer it or for debugging purposes.

## 5. Testing

A thorough testing strategy will be essential to validate the new feature:

1.  **Unit Tests:**
    -   Write unit tests for the `find_best_match` function with various scenarios, including perfect matches, remixes, covers, and cases with no good match.
    -   Write unit tests for the enhanced `clean_title` function.

2.  **Integration Tests:**
    -   Create a test suite that runs the `import_tracks_from_csv` function with a sample CSV file and verifies that the correct Spotify tracks are identified and added.

3.  **Manual Testing:**
    -   Manually test the system with a variety of YouTube playlists to ensure the matching accuracy has improved and that there are no regressions. A "dry run" mode could be added that logs the proposed matches without actually adding them to Spotify, which would be useful for testing.
