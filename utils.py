import json
import csv
import re
from config import YOUTUBE_LIKED_SONGS_CACHE_FILE


def save_to_csv(videos, filename=YOUTUBE_LIKED_SONGS_CACHE_FILE):
    """Save the video data to a CSV file"""
    with open(filename, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Title'])

        for video in videos:
            title = video['snippet']['title']
            channel_title = video['snippet']['channelTitle']
            formatted_title = clean_title(title, channel_title)
            writer.writerow([formatted_title])

def clean_title(title, channel_title):
    """Clean the title by removing unwanted phrases and formatting"""
    # Removing phrases like "Official Music Video", "Official Video", etc.
    title = re.sub(r'\(Official.*?\)|\[Official.*?\]|- Official.*|Official Music Video|Official Video', '', title, flags=re.IGNORECASE)
    # Removing double quotes
    title = title.replace('"', '')
    # Appending channel title if '-' is not in the title
    if "-" not in title:
        title = f"{title} - {channel_title}"
    # Removing '- Topic' and trimming extra whitespace
    return title.replace('- Topic', '').strip()