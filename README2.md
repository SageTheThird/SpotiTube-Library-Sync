# BeatBridge: YouTube Music to Spotify Sync

BeatBridge is a Python-based tool designed to synchronize your music library between YouTube Music and Spotify. This document provides an overview of how the code operates, what it achieves in its current state, and the future direction of the project.

## How it Works

The application is structured into several modules, each with a specific responsibility:

- **`main.py`**: The entry point of the application. It initializes the YouTube and Spotify clients and orchestrates the synchronization process using the `TwoWaySync` class.

- **`sync_manager.py`**: This is the core of the application, containing the `TwoWaySync` class that manages the synchronization logic. It is designed to perform a two-way sync, but currently only the YouTube to Spotify direction is fully implemented.

- **`youtube_client.py`**: This module is responsible for all interactions with the YouTube Data API. It handles authentication, fetching liked videos, searching for videos, and liking videos on behalf of the user.

- **`spotify_client.py`**: This module manages all interactions with the Spotify Web API. It handles authentication, searching for tracks, adding tracks to the user's library, and retrieving the user's liked songs. It also implements a caching mechanism to avoid re-adding songs that are already in the user's library and to speed up searches.

- **`config.py`**: This file centralizes all the configuration for the application. It loads API credentials from a `.env` file and defines constants such as the number of songs to process and the names of cache files.

- **`utils.py`**: A collection of utility functions, primarily for cleaning up song titles extracted from YouTube videos to improve the accuracy of Spotify searches.

The synchronization process is as follows:

1.  The user's liked videos are fetched from YouTube.
2.  The video titles are cleaned to extract the song title and artist.
3.  Each song is then searched for on Spotify.
4.  If a match is found, the song is added to the user's "Liked Songs" on Spotify.
5.  A cache is used to keep track of songs that have already been processed to avoid duplicates.

## What it Achieves

In its current state, BeatBridge provides a one-way synchronization from YouTube Music to Spotify. It automates the otherwise manual and time-consuming process of transferring a music library between these two services. This is particularly useful for users who are migrating from YouTube Music to Spotify or who use both services and want to keep their libraries consistent.

## The Next Evolution

The future development of BeatBridge will focus on the following enhancements:

-   **Full Two-Way Synchronization**: The most significant upcoming feature is the implementation of a full two-way sync. This will not only transfer liked songs from YouTube to Spotify but also from Spotify back to YouTube, creating a seamless and automatic synchronization between the two platforms. The foundation for this is already in place with the `sync_spotify_to_youtube` method in the `sync_manager.py` file, which needs to be enabled and potentially refined.

-   **Improved Song Matching**: The current title-based matching algorithm is effective but can sometimes be inaccurate. The next evolution will incorporate a more sophisticated matching logic that considers not only the title but also the artist and other metadata to ensure more accurate matches between the two services.

-   **User-Friendly Interface**: To make the tool more accessible to a wider audience, a simple user interface is planned. The existing `chrome_extension` folder and HTML files suggest that a browser extension is the likely direction for this, which would allow users to manage the synchronization process directly from their browser.

-   **Real-Time Sync**: The ultimate goal is to transform BeatBridge into a "set it and forget it" service. This would involve modifying the script to run periodically in the background, automatically keeping the user's libraries in sync without any manual intervention.
