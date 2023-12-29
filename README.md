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

   There's already a run.bat file, you can take hints from that on how to run it.

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
