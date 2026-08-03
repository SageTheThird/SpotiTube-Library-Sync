from datetime import datetime
from pathlib import Path
import shutil
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from beatbridge.config import (
    ARCHIVE_DIR,
    LEGACY_SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE,
    LEGACY_SPOTIFY_SEARCH_CACHE_FILE,
    LEGACY_YOUTUBE_SEARCH_CACHE_FILE,
    SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE,
    SPOTIFY_SEARCH_CACHE_FILE,
    YOUTUBE_SEARCH_CACHE_FILE,
)
from beatbridge.storage import (
    load_json_file,
    load_search_cache,
    save_json_atomic,
    save_search_cache_atomic,
)


def main():
    archive_dir = Path(ARCHIVE_DIR) / (
        "cache-layout-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    archived = []

    spotify_search_count = migrate_search_cache(
        legacy_file=LEGACY_SPOTIFY_SEARCH_CACHE_FILE,
        new_file=SPOTIFY_SEARCH_CACHE_FILE,
        service="spotify",
        archive_dir=archive_dir,
        archived=archived,
    )
    youtube_search_count = migrate_search_cache(
        legacy_file=LEGACY_YOUTUBE_SEARCH_CACHE_FILE,
        new_file=YOUTUBE_SEARCH_CACHE_FILE,
        service="youtube",
        archive_dir=archive_dir,
        archived=archived,
    )
    liked_count = migrate_id_list_cache(
        legacy_file=LEGACY_SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE,
        new_file=SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE,
        archive_dir=archive_dir,
        archived=archived,
    )

    print(f"Spotify search cache entries: {spotify_search_count}")
    print(f"YouTube search cache entries: {youtube_search_count}")
    print(f"Spotify liked-track ID cache entries: {liked_count}")
    if archived:
        print(f"Archived legacy cache files in: {archive_dir}")
        for path in archived:
            print(f"- {path.name}")
    else:
        print("No legacy cache files needed archiving.")


def migrate_search_cache(legacy_file, new_file, service, archive_dir, archived):
    legacy_path = Path(legacy_file)
    new_path = Path(new_file)
    merged = {}

    if legacy_path.exists():
        merged.update(load_search_cache(legacy_path, service=service))
    if new_path.exists():
        merged.update(load_search_cache(new_path, service=service))

    if merged:
        save_search_cache_atomic(merged, new_path, service=service)
    if legacy_path.exists():
        archive_file(legacy_path, archive_dir, archived)
    return len(merged)


def migrate_id_list_cache(legacy_file, new_file, archive_dir, archived):
    legacy_path = Path(legacy_file)
    new_path = Path(new_file)
    ids = set()

    if legacy_path.exists():
        ids.update(load_json_file(legacy_path, default=[]))
    if new_path.exists():
        ids.update(load_json_file(new_path, default=[]))

    if ids:
        save_json_atomic(sorted(ids), new_path, indent=2)
    if legacy_path.exists():
        archive_file(legacy_path, archive_dir, archived)
    return len(ids)


def archive_file(path, archive_dir, archived):
    archive_dir.mkdir(parents=True, exist_ok=True)
    destination = archive_dir / path.name
    counter = 1
    while destination.exists():
        destination = archive_dir / f"{path.stem}-{counter}{path.suffix}"
        counter += 1
    shutil.move(str(path), str(destination))
    archived.append(destination)


if __name__ == "__main__":
    main()
