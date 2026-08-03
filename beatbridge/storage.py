import json
from pathlib import Path


def load_json_file(file_path, default):
    path = Path(file_path)
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json_atomic(data, file_path, indent=2):
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=indent, ensure_ascii=False)
    temp_path.replace(path)


def load_search_cache(cache_file, service):
    path = Path(cache_file)
    if not path.exists():
        return {}
    if path.suffix.lower() == ".jsonl":
        return load_search_cache_jsonl(path, service)
    return compact_search_cache(load_json_file(path, default={}), service)


def save_search_cache_atomic(cache, cache_file, service):
    path = Path(cache_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        for query in sorted(cache):
            record = {
                "query": query,
                "results": compact_search_results(cache[query], service),
            }
            file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            file.write("\n")
    temp_path.replace(path)


def load_search_cache_jsonl(path, service):
    cache = {}
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSONL cache record in {path} at line {line_number}"
                ) from exc
            query = record.get("query")
            if not query:
                continue
            cache[query] = compact_search_results(record.get("results", []), service)
    return cache


def compact_search_cache(cache, service):
    return {
        query: compact_search_results(results, service)
        for query, results in cache.items()
    }


def compact_search_results(results, service):
    if isinstance(results, str):
        results = [{"id": results}]
    if not isinstance(results, list):
        return []
    if service == "spotify":
        return [compact_spotify_track(track) for track in results if track]
    if service == "youtube":
        return [compact_youtube_video(video) for video in results if video]
    raise ValueError(f"Unsupported search cache service: {service}")


def compact_spotify_track(track):
    if isinstance(track, str):
        track = {"id": track}
    artists = track.get("artists") or []
    artist_names = []
    for artist in artists:
        if isinstance(artist, dict):
            name = artist.get("name")
        else:
            name = str(artist)
        if name:
            artist_names.append({"name": name})

    album = track.get("album") or {}
    album_name = album.get("name") if isinstance(album, dict) else str(album)
    return {
        "id": track.get("id"),
        "name": track.get("name", ""),
        "artists": artist_names,
        "duration_ms": track.get("duration_ms") or 0,
        "album": {"name": album_name or ""},
    }


def compact_youtube_video(video):
    video_id = extract_youtube_video_id(video)
    snippet = video.get("snippet") or {}
    return {
        "id": {"videoId": video_id},
        "snippet": {
            "title": snippet.get("title", ""),
            "channelTitle": snippet.get("channelTitle", ""),
            "publishedAt": snippet.get("publishedAt") or snippet.get("publishTime"),
        },
    }


def extract_youtube_video_id(video):
    video_id = video.get("id")
    if isinstance(video_id, dict):
        return video_id.get("videoId") or video_id.get("id")
    return video_id
