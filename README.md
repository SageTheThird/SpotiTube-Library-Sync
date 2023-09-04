

Before using this code, make sure you have the following:

- :white_check_mark: Spotify Developer Account: Obtain the Client ID and Client Secret from the Spotify Developer Dashboard.
- :white_check_mark: YouTube Developer Account: Generate the YouTube API credentials JSON file from the Google Cloud Console.
- :white_check_mark: Python 3: Install Python 3 on your machine.

## Installation :computer:

1. Clone this repository to your local machine:
   ```bash
   https://github.com/Hasnainzxc/Spotify-Playlist-Automation.git
  

Navigate to the project directory:

bash
Copy code
cd Spotify-Playlist-Automation
Install the required Python packages:

bash
Copy code
pip install -r requirements.txt
Usage :rocket:
Configure the credentials:
Open the config.py file in a text editor.

Replace the SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET variables with your Spotify credentials. These can be obtained from the Spotify Developer Dashboard.

Replace the YOUTUBE_CLIENT_SECRET_FILE variable with the path to your YouTube API credentials JSON file. This JSON file can be obtained by following the instructions below.

 :rocket:
Set up a Spotify app and obtain the Client ID:
## Go to the Spotify Developer Dashboard.

Log in with your Spotify account or create a new account.

Click on "Create an App" and fill in the required information.

Once your app is created, you will see the Client ID and Client Secret.

Open the config.py file in a text editor.

Replace the SPOTIFY_CLIENT_ID variable with your Spotify app's Client ID.

Replace the SPOTIFY_CLIENT_SECRET variable with your Spotify app's Client Secret.

## Obtain YouTube API credentials:
Go to the Google Cloud Console.

Create a new project or select an existing project.

Enable the YouTube Data API v3 for your project.

Go to the "Credentials" section in the left sidebar.

Click on "Create credentials" and select "OAuth client ID".

Select "Web application" as the application type.

Enter a name for the OAuth client ID.

In the "Authorized redirect URIs" section, add the following redirect URI:

http://localhost:8080/callback
Click on "Create" to generate the OAuth client ID.

Download the JSON file for the created OAuth client ID.

Move the downloaded JSON file to a location on your machine.

Update the YOUTUBE_CLIENT_SECRET_FILE variable in the config.py file with the path to the downloaded JSON file.


Run the script:
bash
Copy code
python spotify.py
Follow the prompts and authorize the required permissions.

The script will automatically retrieve your Spotify playlist and merge it with your YouTube playlist. :notes::arrows_counterclockwise::tv:

#Contributing :raised_hands:
Contributions are welcome! If you have any improvements, bug fixes, or new features, feel free to open a pull request. :sparkles:
<<<<<<< HEAD

License :page_with_curl:
This project is licensed under the MIT License. :scroll:



Feel free to copy and paste this content into your README.md file on GitHub. 
