# SpotiTube-Library-Sync

SpotiTube-Library-Sync is a Python-based tool that automates the synchronization of liked songs from YouTube Music to Spotify. It also includes a Chrome extension for easy control and monitoring of the synchronization process.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

- Python 3.x
- Pip (Python package manager)
- A Spotify Developer account
- A Google Cloud Platform account with YouTube Data API v3 enabled

### Installing

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/SageTheThird/SpotiTube-Library-Sync.git
   cd SpotiTube-Library-Sync
   ```

2. **Install Required Python Libraries:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Environment Variables:**

   Create a `.env` file in the project root directory and populate it with the following variables:

   ```plaintext
   SPOTIFY_CLIENT_ID=your_spotify_client_id
   SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
   SPOTIFY_REDIRECT_URI=http://localhost:8080/callback
   ```

   Replace `your_spotify_client_id` and `your_spotify_client_secret` with your Spotify API credentials.

4. **YouTube API Credentials:**

   Download your `secrets.json` file from Google Cloud Console and place it in the project root directory.

5. **Run the Application:**

   ```bash
   python main.py
   ```
---

## Features

### OAuth Caching Mechanism

This tool employs OAuth caching for both YouTube and Spotify, ensuring a seamless user experience with minimal authentication hassle.

#### Spotify OAuth Caching

- **User Authentication**: The user authenticates with Spotify once. This process grants the application access to the user's Spotify account to perform actions on their behalf.
- **Token Storage**: Post-authentication, the access tokens are stored locally.
- **Automatic Token Refresh**: When the access token expires, the application automatically refreshes it using the stored refresh token. This process happens in the background, and the user is not required to re-authenticate unless the refresh token itself expires or becomes invalid.

#### YouTube OAuth Caching

- **Initial Authentication**: Similar to Spotify, the user logs into their Google account once to allow access to their YouTube data.
- **Token Storage and Refresh**: The application stores the Google OAuth tokens and handles their refresh automatically, mirroring the Spotify OAuth mechanism.

#### Configuration for OAuth Caching

- **Spotify**: The `.spotify_cache` file is created after initial authentication and stores the necessary tokens.
- **YouTube**: The `token.json` file stores Google OAuth tokens and is created after the user first logs into their Google account.

#### Troubleshooting

- **OAuth Issues**: If there are issues with authentication or token refresh, consider re-authenticating by logging in again. Delete the `.spotify_cache` or `token.json` files to force re-authentication.

### Caching Mechanism for API Calls

SpotiTube-Library-Sync implements a robust caching system to enhance efficiency and prevent hitting API rate limits. The caching mechanism involves three key cache stores:

1. **Spotify Search Cache (`spotify_already_searched_cache.json`)**:
   - Caches the results of Spotify track searches.
   - Reduces the number of API calls made to Spotify by storing the search results of previously queried tracks.
   - Format: JSON file storing track names and their corresponding Spotify track IDs.

2. **Spotify Already Added Songs Cache (`spotify_already_liked_cache.json`)**:
   - Tracks which songs have already been added to the user's Spotify Liked Songs.
   - Prevents redundant additions to Spotify, reducing unnecessary API requests.
   - Format: JSON file storing a list of Spotify track IDs that have been added to Liked Songs.

3. **YouTube Liked Songs Cache (`yt_liked_cache.csv`)**:
   - Stores a list of liked songs fetched from YouTube Music.
   - The cache is updated with each execution to reflect the latest liked songs from YouTube Music.
   - Format: CSV file containing titles of liked songs.

#### How Caching Improves Efficiency

- **Minimizes API Calls**: By storing previous search results and tracks statuses, the number of API calls made during each synchronization process is significantly reduced.
- **Reduces Risk of Hitting Quotas**: Frequent API calls can lead to hitting the rate limits imposed by Spotify and YouTube. Caching effectively lowers the risk of reaching these limits.
- **Speeds Up Synchronization**: Retrieving data from local cache is faster than making API calls, thus speeding up the synchronization process.

#### Usage and Configuration

All the cache stores's names are stored in config.py. 

#### Configuration for Caching

- The cache files are automatically created and managed by the script.
- Users can clear the cache manually if needed by deleting the respective `.json` or `.csv` files.

#### Troubleshooting

- **Caching Issues**: If you suspect caching-related problems (e.g., outdated data), try clearing the cache by deleting the cache files.

## Setting Up the Chrome Extension

1. **Load the Extension in Chrome:**

   - Open Chrome and navigate to `chrome://extensions/`
   - Enable "Developer mode"
   - Click "Load unpacked" and select the `chrome_extension` folder within the project

2. **Running the Extension:**

   - Click the extension icon in Chrome to open the popup
   - Click "Sync Liked Songs" to start the synchronization process

## Running the Backend Server in Background (Windows)

1. **Create a Batch File:**

   There's already a run.bat file in root, you can take hints from that on how to run it.

2. **Use Windows Task Scheduler:**

   - Create a new task to run the batch file at system startup.

## Usage

- The script fetches liked songs from YouTube Music and adds them to your Spotify Liked Songs.
- Use the Chrome extension to start the synchronization process and view the log.

## Configuration

- **Spotify**: Set up a Spotify Developer account and create an application to obtain `client_id` and `client_secret`.
- **YouTube**: Enable the YouTube Data API v3 in Google Cloud Console and download the credentials file.

## Troubleshooting

- **Ensure all environment variables are set correctly.**
- **Check the API limits for Spotify and YouTube if encountering rate limit errors.**
