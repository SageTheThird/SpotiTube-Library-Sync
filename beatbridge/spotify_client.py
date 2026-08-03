import concurrent.futures
import csv
import logging
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import spotipy
from Levenshtein import distance as levenshtein_distance

from beatbridge.config import (
    SPOTIFY_ADD_BATCH_SIZE,
    SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE,
    SPOTIFY_IMPORT_PLAN_FILE,
    SPOTIFY_LIKED_TRACKS_EXPORT_FILE,
    SPOTIFY_MATCH_SCORE_THRESHOLD,
    SPOTIFY_SEARCH_CACHE_FILE,
    SPOTIFY_SEARCH_WORKERS,
    USE_IMPROVED_MATCHING,
)
from beatbridge.storage import (
    compact_spotify_track,
    load_json_file,
    load_search_cache,
    save_json_atomic,
    save_search_cache_atomic,
)
from beatbridge.utils import clean_title


logger = logging.getLogger(__name__)
cache_lock = threading.RLock()


def import_tracks_from_csv(
    spotify,
    file_path,
    max_songs=50,
    cache_file=SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE,
    search_cache_file=SPOTIFY_SEARCH_CACHE_FILE,
    videos=None,
    dry_run=False,
    add_oldest_first=False,
    plan_file=SPOTIFY_IMPORT_PLAN_FILE,
    sync_cache=None,
    limit=None,
    plan_only=False,
):
    """Plan and optionally apply a YouTube-to-Spotify liked-song import."""
    if USE_IMPROVED_MATCHING and videos:
        items_to_process = videos[: effective_limit(max_songs, limit)]
    else:
        with open(file_path, newline="", encoding="utf-8") as csvfile:
            reader = csv.reader(csvfile)
            next(reader)
            items_to_process = [row[0] for row in reader]
            items_to_process.reverse()
            items_to_process = items_to_process[: effective_limit(max_songs, limit)]

    plan = build_spotify_import_plan(
        spotify=spotify,
        items=items_to_process,
        search_cache_file=search_cache_file,
        local_liked_cache_file=cache_file,
        sync_cache=sync_cache,
        plan_file=plan_file,
        add_oldest_first=add_oldest_first,
    )

    if plan_only:
        logger.info("Plan-only mode: wrote %s", plan_file)
        return plan["summary"]["pending_track_ids"]

    return apply_spotify_import_plan(
        spotify=spotify,
        plan_file=plan_file,
        local_liked_cache_file=cache_file,
        sync_cache=sync_cache,
        dry_run=dry_run,
    )


def build_spotify_import_plan(
    spotify,
    items,
    search_cache_file=SPOTIFY_SEARCH_CACHE_FILE,
    local_liked_cache_file=SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE,
    sync_cache=None,
    plan_file=SPOTIFY_IMPORT_PLAN_FILE,
    add_oldest_first=True,
):
    """Match YouTube items to Spotify tracks and save a resumable import plan."""
    search_cache = load_spotify_search_cache(search_cache_file)
    initial_search_cache = dict(search_cache)
    local_liked_ids = load_local_cache(local_liked_cache_file)
    synced_video_ids, synced_candidate_keys = load_synced_source_keys(sync_cache)
    seen_candidate_keys = set()

    entries = []
    stats = {
        "items": len(items),
        "duplicates_in_run": 0,
        "already_synced": 0,
        "local_liked_cache_skips": 0,
        "spotify_liked_skips": 0,
        "spotify_track_duplicates": 0,
        "matched": 0,
        "not_found": 0,
        "search_cache_hits": 0,
        "spotify_searches": 0,
    }

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=SPOTIFY_SEARCH_WORKERS
    ) as executor:
        future_to_candidate = {}
        for source_index, item in enumerate(items):
            candidate = build_track_candidate(item, source_index)
            if candidate["video_id"] in synced_video_ids:
                stats["already_synced"] += 1
                entries.append(skipped_plan_entry(candidate, "already_synced_video"))
                continue
            if candidate["candidate_key"] in synced_candidate_keys:
                stats["already_synced"] += 1
                entries.append(skipped_plan_entry(candidate, "already_synced_track"))
                continue
            if candidate["candidate_key"] in seen_candidate_keys:
                stats["duplicates_in_run"] += 1
                entries.append(skipped_plan_entry(candidate, "duplicate_in_run"))
                continue

            seen_candidate_keys.add(candidate["candidate_key"])
            future = executor.submit(
                match_candidate_to_spotify,
                spotify,
                candidate,
                search_cache,
            )
            future_to_candidate[future] = candidate

        for future in concurrent.futures.as_completed(future_to_candidate):
            candidate = future_to_candidate[future]
            result = future.result()
            stats["search_cache_hits"] += result["cache_hits"]
            stats["spotify_searches"] += result["api_searches"]

            if not result["match"]:
                stats["not_found"] += 1
                entries.append(
                    {
                        **base_plan_entry(candidate),
                        "status": "not_found",
                        "reason": result["reason"],
                        "best_score": result["best_score"],
                        "queries": result["queries"],
                    }
                )
                continue

            track = result["match"]
            if track["id"] in local_liked_ids:
                stats["local_liked_cache_skips"] += 1
                entries.append(
                    {
                        **base_plan_entry(candidate),
                        "status": "skipped",
                        "reason": "already_liked_local_cache",
                        "spotify_track": serialize_spotify_track(track),
                        "score": result["score"],
                        "queries": result["queries"],
                    }
                )
                continue

            stats["matched"] += 1
            entries.append(
                {
                    **base_plan_entry(candidate),
                    "status": "pending",
                    "spotify_track": serialize_spotify_track(track),
                    "score": result["score"],
                    "queries": result["queries"],
                }
            )

    entries.sort(key=lambda entry: entry["source_index"])
    if search_cache != initial_search_cache:
        save_spotify_search_cache(search_cache, search_cache_file)

    plan = {
        "created_at": utc_now_iso(),
        "add_order": "oldest_first" if add_oldest_first else "source_order",
        "entries": entries,
        "add_queue": [],
        "summary": {
            **stats,
            "pending": 0,
            "pending_track_ids": [],
        },
    }
    save_json_atomic(plan, plan_file)

    refresh_spotify_liked_status(spotify, entries, stats)
    dedupe_pending_spotify_track_ids(entries, stats)
    entries_to_add = [entry for entry in entries if entry["status"] == "pending"]
    stats["matched"] = len(entries_to_add)
    if add_oldest_first:
        entries_to_add = list(reversed(entries_to_add))

    plan["entries"] = entries
    plan["add_queue"] = [entry["id"] for entry in entries_to_add]
    plan["summary"] = {
        **stats,
        "pending": len(entries_to_add),
        "pending_track_ids": [entry["spotify_track"]["id"] for entry in entries_to_add],
    }

    save_json_atomic(plan, plan_file)
    logger.info("Wrote Spotify import plan: %s", plan_file)
    logger.info("Plan summary: %s", plan["summary"])
    return plan


def apply_spotify_import_plan(
    spotify,
    plan_file=SPOTIFY_IMPORT_PLAN_FILE,
    local_liked_cache_file=SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE,
    sync_cache=None,
    dry_run=False,
    batch_size=SPOTIFY_ADD_BATCH_SIZE,
    max_retries=3,
):
    """Apply pending tracks from a saved import plan in resumable batches."""
    plan = load_json_file(plan_file, default=None)
    if not plan:
        logger.info("No Spotify import plan found at %s", plan_file)
        return []

    dedupe_plan_pending_tracks(plan)
    save_json_atomic(plan, plan_file)

    entries_by_id = {entry["id"]: entry for entry in plan["entries"]}
    pending_entries = [
        entries_by_id[entry_id]
        for entry_id in plan.get("add_queue", [])
        if entries_by_id.get(entry_id, {}).get("status") == "pending"
    ]

    if not pending_entries:
        logger.info("No pending Spotify tracks in %s", plan_file)
        return []

    added_track_ids = []
    for batch_start in range(0, len(pending_entries), batch_size):
        batch_entries = pending_entries[batch_start : batch_start + batch_size]
        track_ids = [entry["spotify_track"]["id"] for entry in batch_entries]

        if dry_run:
            logger.info("Dry run: would add %s Spotify tracks", len(track_ids))
            added_track_ids.extend(track_ids)
            continue

        add_track_batch_with_retries(
            spotify=spotify,
            track_ids=track_ids,
            max_retries=max_retries,
        )

        for entry in batch_entries:
            entry["status"] = "added"
            entry["added_at"] = utc_now_iso()
            update_local_cache(entry["spotify_track"]["id"], local_liked_cache_file)
            mark_source_synced(sync_cache, entry)
            added_track_ids.append(entry["spotify_track"]["id"])

        refresh_spotify_plan_pending_summary(plan)
        save_json_atomic(plan, plan_file)
        if sync_cache:
            save_sync_cache(sync_cache)
        logger.info(
            "Added Spotify batch %s-%s of %s",
            batch_start + 1,
            batch_start + len(batch_entries),
            len(pending_entries),
        )

    return added_track_ids


def match_candidate_to_spotify(spotify, candidate, search_cache):
    best_match = None
    best_score = -1
    queries_run = []
    cache_hits = 0
    api_searches = 0

    for query in candidate["queries"]:
        cached = has_usable_spotify_cached_value(search_cache.get(query))
        tracks = search_spotify_cached(spotify, query, search_cache)
        queries_run.append(query)
        cache_hits += 1 if cached else 0
        api_searches += 0 if cached else 1

        for track in tracks:
            score = score_spotify_match(candidate, track)
            if score > best_score:
                best_score = score
                best_match = track

        if best_match and best_score >= SPOTIFY_MATCH_SCORE_THRESHOLD:
            return {
                "match": best_match,
                "score": best_score,
                "best_score": best_score,
                "queries": queries_run,
                "cache_hits": cache_hits,
                "api_searches": api_searches,
                "reason": None,
            }

    return {
        "match": None,
        "score": None,
        "best_score": best_score,
        "queries": queries_run,
        "cache_hits": cache_hits,
        "api_searches": api_searches,
        "reason": "below_threshold",
    }


def search_spotify_cached(spotify, query, search_cache, limit=5):
    with cache_lock:
        if has_usable_spotify_cached_value(search_cache.get(query)):
            cached_value = search_cache[query]
            if isinstance(cached_value, list):
                return cached_value
            if isinstance(cached_value, str):
                return [{"id": cached_value, "name": "", "artists": [], "duration_ms": 0}]

    results = spotify.search(q=query, limit=limit, type="track")
    tracks = results["tracks"]["items"]
    compact_tracks = [compact_spotify_track(track) for track in tracks]
    with cache_lock:
        search_cache[query] = compact_tracks
    return compact_tracks


def has_usable_spotify_cached_value(cached_value):
    if cached_value is None:
        return False
    if cached_value == []:
        return True
    if isinstance(cached_value, str):
        return not USE_IMPROVED_MATCHING
    if isinstance(cached_value, list):
        if not USE_IMPROVED_MATCHING:
            return True
        return any(track.get("name") for track in cached_value if isinstance(track, dict))
    return False


def build_track_candidate(item, source_index):
    if isinstance(item, dict):
        snippet = item.get("snippet", {})
        content_details = item.get("contentDetails", {})
        raw_title = snippet.get("title", "")
        channel_title = snippet.get("channelTitle", "")
        cleaned = clean_title(raw_title, channel_title)
        video_id = item.get("id") or f"source-{source_index}"
        duration = parse_youtube_duration(content_details.get("duration", ""))
    else:
        raw_title = str(item)
        channel_title = ""
        cleaned = raw_title
        video_id = f"source-{source_index}"
        duration = 0

    title_part, artist_part = split_title_artist(cleaned, channel_title)
    candidate_key = normalize_key(f"{title_part}|{artist_part}")
    return {
        "source_index": source_index,
        "video_id": video_id,
        "raw_title": raw_title,
        "cleaned_title": cleaned,
        "title": title_part,
        "artist_hint": artist_part,
        "channel_title": channel_title,
        "duration_seconds": duration,
        "candidate_key": candidate_key,
        "queries": build_spotify_queries(
            raw_title=raw_title,
            cleaned_title=cleaned,
            title=title_part,
            artist_hint=artist_part,
        ),
    }


def build_spotify_queries(raw_title, cleaned_title, title, artist_hint):
    queries = []
    raw_title = raw_title.strip()
    cleaned_title = cleaned_title.strip()
    title = title.strip()
    artist_hint = artist_hint.strip()

    if raw_title:
        queries.append(raw_title)
    if title and artist_hint:
        queries.append(f'track:"{title}" artist:"{artist_hint}"')
        queries.append(f"{title} {artist_hint}")
    if cleaned_title:
        queries.append(cleaned_title)
    if title:
        queries.append(title)
    return dedupe_preserve_order(queries)


def split_title_artist(cleaned_title, channel_title):
    normalized_channel = strip_topic_suffix(channel_title)
    if " - " in cleaned_title:
        left, right = [part.strip() for part in cleaned_title.split(" - ", 1)]
        if normalized_channel and normalize_key(normalized_channel) in normalize_key(left):
            return right or cleaned_title, normalized_channel
        if normalized_channel and normalize_key(normalized_channel) in normalize_key(right):
            return left or cleaned_title, normalized_channel
        return right or cleaned_title, left or normalized_channel
    return cleaned_title, normalized_channel


def score_spotify_match(candidate, spotify_track):
    spotify_title = spotify_track.get("name", "")
    spotify_artists = [artist["name"] for artist in spotify_track.get("artists", [])]
    spotify_duration = spotify_track.get("duration_ms", 0) / 1000

    candidate_title = candidate["title"] or candidate["cleaned_title"]
    title_similarity = 1 - levenshtein_distance(
        candidate_title.lower(), spotify_title.lower()
    ) / max(len(candidate_title), len(spotify_title), 1)

    artist_match_score = 0
    artist_hint = candidate["artist_hint"].lower()
    raw_title = candidate["raw_title"].lower()
    channel_title = candidate["channel_title"].lower()
    for artist in spotify_artists:
        artist_lower = artist.lower()
        if (
            artist_lower in artist_hint
            or artist_hint in artist_lower
            or artist_lower in raw_title
            or artist_lower in channel_title
        ):
            artist_match_score = 1
            break

    duration_similarity = 0
    if candidate["duration_seconds"] > 0 and spotify_duration > 0:
        duration_similarity = max(
            0,
            1
            - abs(candidate["duration_seconds"] - spotify_duration)
            / candidate["duration_seconds"],
        )

    return (
        title_similarity * 0.45
        + artist_match_score * 0.35
        + duration_similarity * 0.20
    )


def refresh_spotify_liked_status(spotify, entries, stats):
    pending_entries = [entry for entry in entries if entry["status"] == "pending"]
    for start in range(0, len(pending_entries), SPOTIFY_ADD_BATCH_SIZE):
        batch = pending_entries[start : start + SPOTIFY_ADD_BATCH_SIZE]
        track_ids = [entry["spotify_track"]["id"] for entry in batch]
        contains = saved_tracks_contains_with_split(spotify, track_ids)
        for entry, already_liked in zip(batch, contains):
            if already_liked:
                entry["status"] = "skipped"
                entry["reason"] = "already_liked_spotify"
                stats["spotify_liked_skips"] += 1


def dedupe_pending_spotify_track_ids(entries, stats):
    seen_track_ids = set()
    for entry in entries:
        if entry["status"] != "pending":
            continue
        track_id = entry["spotify_track"]["id"]
        if track_id in seen_track_ids:
            entry["status"] = "skipped"
            entry["reason"] = "duplicate_spotify_track"
            stats["spotify_track_duplicates"] += 1
            continue
        seen_track_ids.add(track_id)


def dedupe_plan_pending_tracks(plan):
    stats = plan.setdefault("summary", {})
    stats.setdefault("spotify_track_duplicates", 0)
    before = stats["spotify_track_duplicates"]
    dedupe_pending_spotify_track_ids(plan["entries"], stats)

    refresh_spotify_plan_pending_summary(plan)
    if stats["spotify_track_duplicates"] != before:
        logger.info(
            "Skipped %s duplicate Spotify track matches in saved plan",
            stats["spotify_track_duplicates"] - before,
        )


def refresh_spotify_plan_pending_summary(plan):
    stats = plan.setdefault("summary", {})
    entries_by_id = {entry["id"]: entry for entry in plan["entries"]}
    plan["add_queue"] = [
        entry_id
        for entry_id in plan.get("add_queue", [])
        if entries_by_id.get(entry_id, {}).get("status") == "pending"
    ]
    stats["pending"] = len(plan["add_queue"])
    stats["pending_track_ids"] = [
        entries_by_id[entry_id]["spotify_track"]["id"]
        for entry_id in plan["add_queue"]
    ]


def saved_tracks_contains_with_split(spotify, track_ids):
    try:
        return spotify.current_user_saved_tracks_contains(tracks=track_ids)
    except spotipy.SpotifyException as exc:
        if is_too_many_uris_error(exc) and len(track_ids) > 1:
            midpoint = len(track_ids) // 2
            return saved_tracks_contains_with_split(
                spotify,
                track_ids[:midpoint],
            ) + saved_tracks_contains_with_split(
                spotify,
                track_ids[midpoint:],
            )
        raise


def add_track_batch_with_retries(spotify, track_ids, max_retries=3):
    retry_count = 0
    while retry_count < max_retries:
        try:
            spotify.current_user_saved_tracks_add(tracks=track_ids)
            return
        except spotipy.SpotifyException as exc:
            if is_too_many_uris_error(exc) and len(track_ids) > 1:
                midpoint = len(track_ids) // 2
                add_track_batch_with_retries(
                    spotify,
                    track_ids[:midpoint],
                    max_retries=max_retries,
                )
                add_track_batch_with_retries(
                    spotify,
                    track_ids[midpoint:],
                    max_retries=max_retries,
                )
                return
            if exc.http_status == 429:
                retry_after = int(exc.headers.get("Retry-After", 10))
                logger.warning(
                    "Spotify rate limit reached. Retrying after %s seconds.",
                    retry_after,
                )
                time.sleep(retry_after)
                retry_count += 1
                continue
            raise
    raise RuntimeError(f"Failed to add Spotify batch after {max_retries} retries")


def is_too_many_uris_error(exc):
    return exc.http_status == 400 and "Too many uris" in str(exc)


def add_tracks_to_spotify(
    spotify,
    track_ids,
    cache_file=SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE,
    max_retries=3,
    dry_run=False,
    batch_size=SPOTIFY_ADD_BATCH_SIZE,
):
    """Compatibility helper for adding raw track ID lists."""
    plan = {
        "created_at": utc_now_iso(),
        "add_order": "provided",
        "entries": [
            {
                "id": f"manual-{index}",
                "source_index": index,
                "status": "pending",
                "spotify_track": {"id": track_id},
            }
            for index, track_id in enumerate(track_ids)
        ],
        "add_queue": [f"manual-{index}" for index in range(len(track_ids))],
    }
    save_json_atomic(plan, SPOTIFY_IMPORT_PLAN_FILE)
    return apply_spotify_import_plan(
        spotify,
        plan_file=SPOTIFY_IMPORT_PLAN_FILE,
        local_liked_cache_file=cache_file,
        dry_run=dry_run,
        batch_size=batch_size,
        max_retries=max_retries,
    )


def skipped_plan_entry(candidate, reason):
    return {**base_plan_entry(candidate), "status": "skipped", "reason": reason}


def base_plan_entry(candidate):
    return {
        "id": f"yt-{candidate['source_index']}",
        "source_index": candidate["source_index"],
        "video_id": candidate["video_id"],
        "raw_title": candidate["raw_title"],
        "cleaned_title": candidate["cleaned_title"],
        "title": candidate["title"],
        "artist_hint": candidate["artist_hint"],
        "channel_title": candidate["channel_title"],
        "duration_seconds": candidate["duration_seconds"],
        "candidate_key": candidate["candidate_key"],
    }


def serialize_spotify_track(track):
    return {
        "id": track["id"],
        "name": track.get("name", ""),
        "artists": [artist["name"] for artist in track.get("artists", [])],
        "duration_ms": track.get("duration_ms"),
        "album": track.get("album", {}).get("name"),
    }


def load_synced_source_keys(sync_cache):
    if not sync_cache:
        return set(), set()
    synced_items = sync_cache.get("synced_items", []) + sync_cache.get(
        "skip_synced_items", []
    )
    return (
        {item.get("youtube_id") for item in synced_items if item.get("youtube_id")},
        {
            item.get("candidate_key")
            for item in synced_items
            if item.get("candidate_key")
        },
    )


def mark_source_synced(sync_cache, entry):
    if not sync_cache:
        return
    sync_cache.setdefault("synced_items", []).append(
        {
            "youtube_id": entry.get("video_id"),
            "candidate_key": entry.get("candidate_key"),
            "youtube_title": entry.get("raw_title"),
            "spotify_id": entry["spotify_track"]["id"],
            "spotify_name": entry["spotify_track"].get("name"),
            "spotify_artists": entry["spotify_track"].get("artists", []),
            "sync_date": utc_now_iso(),
        }
    )
    sync_cache["last_sync"] = utc_now_iso()


def save_sync_cache(sync_cache):
    cache_file = sync_cache["cache_file"]
    data_to_save = {
        key: value for key, value in sync_cache.items() if key != "cache_file"
    }
    save_json_atomic(data_to_save, cache_file)


def parse_youtube_duration(duration):
    total_seconds = 0
    matches = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not matches:
        return total_seconds

    hours, minutes, seconds = matches.groups()
    if hours:
        total_seconds += int(hours) * 3600
    if minutes:
        total_seconds += int(minutes) * 60
    if seconds:
        total_seconds += int(seconds)
    return total_seconds


def get_all_saved_tracks(spotify, filename=SPOTIFY_LIKED_TRACKS_EXPORT_FILE):
    """Retrieve all saved Spotify tracks and save them to a CSV file."""
    offset = 0
    all_tracks = []
    total_tracks = None

    Path(filename).parent.mkdir(parents=True, exist_ok=True)
    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(
            ["Artist", "Track Name", "Track ID", "Album Name", "Popularity", "Added At"]
        )

        while True:
            results = spotify.current_user_saved_tracks(limit=50, offset=offset)
            if total_tracks is None:
                total_tracks = results["total"]
                logger.info("Total Spotify tracks to retrieve: %s", total_tracks)

            if not results["items"]:
                break

            for item in results["items"]:
                track = item["track"]
                artists = ", ".join(artist["name"] for artist in track["artists"])
                writer.writerow(
                    [
                        artists,
                        track["name"],
                        track["id"],
                        track["album"]["name"],
                        track.get("popularity"),
                        item.get("added_at"),
                    ]
                )
                all_tracks.append(track)

            offset += 50
            if offset >= total_tracks:
                break
            time.sleep(0.5)

    logger.info("Successfully saved %s tracks to %s", len(all_tracks), filename)
    return all_tracks


def load_spotify_search_cache(cache_file=SPOTIFY_SEARCH_CACHE_FILE):
    with cache_lock:
        return load_search_cache(cache_file, service="spotify")


def save_spotify_search_cache(cache, cache_file=SPOTIFY_SEARCH_CACHE_FILE):
    with cache_lock:
        save_search_cache_atomic(cache, cache_file, service="spotify")


def update_spotify_search_cache(track_name, tracks, cache_file=SPOTIFY_SEARCH_CACHE_FILE):
    with cache_lock:
        cache = load_spotify_search_cache(cache_file)
        cache[track_name] = tracks
        save_spotify_search_cache(cache, cache_file)


def search_spotify(
    spotify,
    track_name,
    cache_file=SPOTIFY_SEARCH_CACHE_FILE,
    limit=5,
    update_cache=True,
):
    cache = load_spotify_search_cache(cache_file)
    tracks = search_spotify_cached(spotify, track_name, cache, limit=limit)
    if update_cache:
        save_spotify_search_cache(cache, cache_file)
    if USE_IMPROVED_MATCHING:
        return tracks
    return tracks[0]["id"] if tracks else None


def update_local_cache(song_id, cache_file=SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE):
    with cache_lock:
        try:
            cache = load_local_cache(cache_file)
            cache.add(song_id)
            save_json_atomic(sorted(cache), cache_file)
        except Exception as exc:
            logger.warning("Error updating cache file %s: %s", cache_file, exc)


def load_local_cache(cache_file=SPOTIFY_ALREADY_ADDED_SONGS_CACHE_FILE):
    with cache_lock:
        try:
            return set(load_json_file(cache_file, default=[]))
        except Exception as exc:
            logger.warning("Error loading cache file %s: %s", cache_file, exc)
            return set()


def get_spotify_liked_songs(spotify, limit=50, offset=0):
    """Get a page of Spotify liked songs."""
    results = spotify.current_user_saved_tracks(limit=limit, offset=offset)
    songs = []
    for item in results["items"]:
        track = item["track"]
        songs.append(
            {
                "id": track["id"],
                "name": track["name"],
                "artists": [artist["name"] for artist in track["artists"]],
                "added_at": item["added_at"],
            }
        )
    return songs


def get_all_spotify_liked_songs(spotify, max_songs=200):
    """Get all liked songs up to max_songs limit."""
    all_songs = []
    offset = 0
    limit = 50

    while len(all_songs) < max_songs:
        batch = get_spotify_liked_songs(spotify, limit=limit, offset=offset)
        if not batch:
            break
        all_songs.extend(batch)
        offset += limit

    return all_songs[:max_songs]


def effective_limit(max_songs, limit):
    if limit is None:
        return max_songs
    return min(max_songs, limit)


def strip_topic_suffix(value):
    return re.sub(r"\s*-\s*Topic$", "", value or "", flags=re.IGNORECASE).strip()


def normalize_key(value):
    value = strip_topic_suffix(value)
    value = re.sub(r"[^\w\s]+", " ", value.lower(), flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def dedupe_preserve_order(values):
    seen = set()
    result = []
    for value in values:
        key = value.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()
