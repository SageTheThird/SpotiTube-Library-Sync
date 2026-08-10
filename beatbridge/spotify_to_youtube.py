import concurrent.futures
import logging

from Levenshtein import distance as levenshtein_distance

from beatbridge.config import (
    SPOTIFY_TO_YOUTUBE_PLAN_FILE,
    YOUTUBE_MATCH_SCORE_THRESHOLD,
    YOUTUBE_SEARCH_CACHE_FILE,
    YOUTUBE_SEARCH_WORKERS,
)
from beatbridge.spotify_client import (
    dedupe_preserve_order,
    normalize_key,
    utc_now_iso,
)
from beatbridge.storage import (
    compact_youtube_video,
    load_json_file,
    load_search_cache,
    save_json_atomic,
    save_search_cache_atomic,
)
from beatbridge.youtube_client import like_youtube_video_result, search_youtube_videos


logger = logging.getLogger(__name__)


def build_spotify_to_youtube_plan(
    youtube,
    spotify_songs,
    sync_cache,
    reverse_sync_cache=None,
    target_liked_youtube_ids=None,
    skip_reverse_imports=True,
    plan_file=SPOTIFY_TO_YOUTUBE_PLAN_FILE,
    search_cache_file=YOUTUBE_SEARCH_CACHE_FILE,
):
    """Match Spotify liked songs to YouTube videos and save a resumable plan."""
    search_cache = load_youtube_search_cache(search_cache_file)
    initial_search_cache = dict(search_cache)
    synced_spotify_ids = load_synced_spotify_ids(sync_cache)
    synced_youtube_ids = load_synced_youtube_ids(sync_cache)
    blocked_youtube_ids = load_blocked_youtube_ids(sync_cache)
    reverse_imported_spotify_ids = load_synced_spotify_ids(reverse_sync_cache)
    reverse_youtube_matches = load_reverse_youtube_matches(reverse_sync_cache)
    target_liked_youtube_ids = set(target_liked_youtube_ids or [])
    seen_candidate_keys = set()

    entries = []
    stats = {
        "items": len(spotify_songs),
        "already_synced": 0,
        "reverse_import_skips": 0,
        "duplicates_in_run": 0,
        "already_synced_youtube": 0,
        "already_liked_on_target": 0,
        "blocked_youtube_rating": 0,
        "direct_reverse_matches": 0,
        "matched": 0,
        "not_found": 0,
        "search_cache_hits": 0,
        "youtube_searches": 0,
        "youtube_video_duplicates": 0,
    }

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=YOUTUBE_SEARCH_WORKERS
    ) as executor:
        future_to_candidate = {}
        for source_index, song in enumerate(spotify_songs):
            candidate = build_spotify_candidate(song, source_index)
            if candidate["spotify_id"] in synced_spotify_ids:
                stats["already_synced"] += 1
                entries.append(skipped_plan_entry(candidate, "already_synced_spotify"))
                continue
            if skip_reverse_imports and candidate["spotify_id"] in reverse_imported_spotify_ids:
                stats["reverse_import_skips"] += 1
                entries.append(skipped_plan_entry(candidate, "imported_from_youtube"))
                continue
            if candidate["candidate_key"] in seen_candidate_keys:
                stats["duplicates_in_run"] += 1
                entries.append(skipped_plan_entry(candidate, "duplicate_in_run"))
                continue

            seen_candidate_keys.add(candidate["candidate_key"])

            reverse_match = reverse_youtube_matches.get(
                candidate["spotify_id"]
            ) or reverse_youtube_matches.get(candidate["candidate_key"])
            if reverse_match:
                youtube_video = youtube_video_from_reverse_match(reverse_match)
                maybe_entry = build_candidate_youtube_entry(
                    candidate,
                    youtube_video,
                    synced_youtube_ids,
                    target_liked_youtube_ids,
                    blocked_youtube_ids,
                    stats,
                    score=1,
                    queries=[],
                    reason_prefix="original_youtube",
                )
                if maybe_entry["status"] == "pending":
                    stats["direct_reverse_matches"] += 1
                    stats["matched"] += 1
                entries.append(maybe_entry)
                continue

            future = executor.submit(
                match_spotify_candidate_to_youtube,
                youtube,
                candidate,
                search_cache,
            )
            future_to_candidate[future] = candidate

        for future in concurrent.futures.as_completed(future_to_candidate):
            candidate = future_to_candidate[future]
            result = future.result()
            stats["search_cache_hits"] += result["cache_hits"]
            stats["youtube_searches"] += result["api_searches"]

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

            youtube_video = serialize_youtube_video(result["match"])
            entry = build_candidate_youtube_entry(
                candidate,
                youtube_video,
                synced_youtube_ids,
                target_liked_youtube_ids,
                blocked_youtube_ids,
                stats,
                score=result["score"],
                queries=result["queries"],
            )
            if entry["status"] == "pending":
                stats["matched"] += 1
            entries.append(entry)

    entries.sort(key=lambda entry: entry["source_index"])
    if search_cache != initial_search_cache:
        save_youtube_search_cache(search_cache, search_cache_file)

    dedupe_pending_youtube_video_ids(entries, stats)
    entries_to_apply = [entry for entry in entries if entry["status"] == "pending"]
    stats["matched"] = len(entries_to_apply)

    plan = {
        "created_at": utc_now_iso(),
        "entries": entries,
        "apply_queue": [entry["id"] for entry in entries_to_apply],
        "summary": {
            **stats,
            "pending": len(entries_to_apply),
            "pending_youtube_ids": [
                entry["youtube_video"]["id"] for entry in entries_to_apply
            ],
        },
    }
    save_json_atomic(plan, plan_file)
    logger.info("Wrote Spotify-to-YouTube plan: %s", plan_file)
    logger.info("Plan summary: %s", plan["summary"])
    return plan


def apply_spotify_to_youtube_plan(
    youtube,
    sync_cache,
    plan_file=SPOTIFY_TO_YOUTUBE_PLAN_FILE,
    dry_run=False,
):
    """Like pending YouTube videos from a saved Spotify-to-YouTube plan."""
    plan = load_json_file(plan_file, default=None)
    if not plan:
        logger.info("No Spotify-to-YouTube plan found at %s", plan_file)
        return []

    dedupe_plan_pending_youtube_videos(plan)
    save_json_atomic(plan, plan_file)

    entries_by_id = {entry["id"]: entry for entry in plan["entries"]}
    pending_entries = [
        entries_by_id[entry_id]
        for entry_id in plan.get("apply_queue", [])
        if entries_by_id.get(entry_id, {}).get("status") == "pending"
    ]

    if not pending_entries:
        logger.info("No pending YouTube videos in %s", plan_file)
        return []

    liked_video_ids = []
    for index, entry in enumerate(pending_entries, start=1):
        video_id = entry["youtube_video"]["id"]
        if dry_run:
            logger.info(
                "Dry run: would like YouTube video %s for Spotify track '%s'",
                video_id,
                entry["spotify_name"],
            )
            liked_video_ids.append(video_id)
            continue

        rate_result = like_youtube_video_result(youtube, video_id)
        if rate_result["ok"]:
            entry["status"] = "liked"
            entry["liked_at"] = utc_now_iso()
            mark_spotify_to_youtube_synced(sync_cache, entry)
            liked_video_ids.append(video_id)
            refresh_youtube_plan_pending_summary(plan)
            save_json_atomic(plan, plan_file)
            save_sync_cache(sync_cache)
            logger.info(
                "Liked YouTube video %s of %s: %s",
                index,
                len(pending_entries),
                video_id,
            )
            continue

        if not rate_result["retryable"]:
            entry["status"] = "skipped"
            entry["reason"] = f"youtube_rate_{rate_result['reason']}"
            entry["error"] = rate_result["message"]
            entry["skipped_at"] = utc_now_iso()
            mark_spotify_to_youtube_blocked(sync_cache, entry, rate_result)
            refresh_youtube_plan_pending_summary(plan)
            save_json_atomic(plan, plan_file)
            save_sync_cache(sync_cache)
            logger.info(
                "Skipped unrateable YouTube video %s of %s: %s",
                index,
                len(pending_entries),
                video_id,
            )

    return liked_video_ids


def match_spotify_candidate_to_youtube(youtube, candidate, search_cache):
    best_match = None
    best_score = -1
    queries_run = []
    cache_hits = 0
    api_searches = 0

    for query in candidate["queries"]:
        cached = query in search_cache
        videos = search_youtube_cached(youtube, query, search_cache)
        queries_run.append(query)
        cache_hits += 1 if cached else 0
        api_searches += 0 if cached else 1

        for video in videos:
            score = score_youtube_match(candidate, video)
            if score > best_score:
                best_score = score
                best_match = video

        if best_match and best_score >= YOUTUBE_MATCH_SCORE_THRESHOLD:
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


def search_youtube_cached(youtube, query, search_cache, max_results=5):
    if query in search_cache:
        return search_cache[query]

    videos = search_youtube_videos(youtube, query, max_results=max_results)
    compact_videos = [compact_youtube_video(video) for video in videos]
    search_cache[query] = compact_videos
    return compact_videos


def load_youtube_search_cache(cache_file=YOUTUBE_SEARCH_CACHE_FILE):
    return load_search_cache(cache_file, service="youtube")


def save_youtube_search_cache(cache, cache_file=YOUTUBE_SEARCH_CACHE_FILE):
    save_search_cache_atomic(cache, cache_file, service="youtube")


def build_spotify_candidate(song, source_index):
    artists = song.get("artists", [])
    artists_str = ", ".join(artists)
    title = song.get("name", "")
    candidate_key = normalize_key(f"{title}|{artists_str}")
    return {
        "id": f"spotify-{source_index}",
        "source_index": source_index,
        "spotify_id": song["id"],
        "spotify_name": title,
        "spotify_artists": artists,
        "spotify_added_at": song.get("added_at"),
        "candidate_key": candidate_key,
        "queries": build_youtube_queries(title, artists),
    }


def build_youtube_queries(title, artists):
    primary_artist = artists[0] if artists else ""
    artists_str = " ".join(artists)
    queries = []
    if title and primary_artist:
        queries.append(f'{title} {primary_artist} official audio')
        queries.append(f'{title} {primary_artist} official video')
        queries.append(f'"{title}" "{primary_artist}"')
    if title and artists_str:
        queries.append(f"{title} {artists_str}")
    if title:
        queries.append(title)
    return dedupe_preserve_order(queries)


def score_youtube_match(candidate, video):
    snippet = video.get("snippet", {})
    video_title = snippet.get("title", "")
    channel_title = snippet.get("channelTitle", "")
    edit_similarity = 1 - levenshtein_distance(
        candidate["spotify_name"].lower(), video_title.lower()
    ) / max(len(candidate["spotify_name"]), len(video_title), 1)
    title_score = max(
        edit_similarity,
        token_containment_score(candidate["spotify_name"], video_title),
    )

    artist_score = 0
    haystack = f"{video_title} {channel_title}".lower()
    for artist in candidate["spotify_artists"]:
        if artist.lower() in haystack:
            artist_score = 1
            break

    official_score = 0
    official_words = ("official", "audio", "video", "topic")
    if any(word in haystack for word in official_words):
        official_score = 1

    return title_score * 0.55 + artist_score * 0.35 + official_score * 0.10


def token_containment_score(expected_title, candidate_title):
    expected_tokens = significant_tokens(expected_title)
    if not expected_tokens:
        return 0
    candidate_tokens = set(significant_tokens(candidate_title))
    overlap = sum(1 for token in expected_tokens if token in candidate_tokens)
    return overlap / len(expected_tokens)


def significant_tokens(value):
    stopwords = {
        "a",
        "an",
        "and",
        "by",
        "feat",
        "featuring",
        "from",
        "in",
        "of",
        "the",
        "to",
        "with",
    }
    return [
        token
        for token in normalize_key(value).split()
        if token not in stopwords and len(token) > 1
    ]


def dedupe_pending_youtube_video_ids(entries, stats):
    seen_video_ids = set()
    for entry in entries:
        if entry["status"] != "pending":
            continue
        video_id = entry["youtube_video"]["id"]
        if video_id in seen_video_ids:
            entry["status"] = "skipped"
            entry["reason"] = "duplicate_youtube_video"
            stats["youtube_video_duplicates"] += 1
            continue
        seen_video_ids.add(video_id)


def dedupe_plan_pending_youtube_videos(plan):
    stats = plan.setdefault("summary", {})
    stats.setdefault("youtube_video_duplicates", 0)
    dedupe_pending_youtube_video_ids(plan["entries"], stats)

    refresh_youtube_plan_pending_summary(plan)


def refresh_youtube_plan_pending_summary(plan):
    stats = plan.setdefault("summary", {})
    entries_by_id = {entry["id"]: entry for entry in plan["entries"]}
    plan["apply_queue"] = [
        entry_id
        for entry_id in plan.get("apply_queue", [])
        if entries_by_id.get(entry_id, {}).get("status") == "pending"
    ]
    stats["pending"] = len(plan["apply_queue"])
    stats["pending_youtube_ids"] = [
        entries_by_id[entry_id]["youtube_video"]["id"]
        for entry_id in plan["apply_queue"]
    ]


def skipped_plan_entry(candidate, reason):
    return {**base_plan_entry(candidate), "status": "skipped", "reason": reason}


def base_plan_entry(candidate):
    return {
        "id": candidate["id"],
        "source_index": candidate["source_index"],
        "spotify_id": candidate["spotify_id"],
        "spotify_name": candidate["spotify_name"],
        "spotify_artists": candidate["spotify_artists"],
        "spotify_added_at": candidate["spotify_added_at"],
        "candidate_key": candidate["candidate_key"],
    }


def build_candidate_youtube_entry(
    candidate,
    youtube_video,
    synced_youtube_ids,
    target_liked_youtube_ids,
    blocked_youtube_ids,
    stats,
    score,
    queries,
    reason_prefix=None,
):
    if youtube_video["id"] in synced_youtube_ids:
        stats["already_synced_youtube"] += 1
        return {
            **base_plan_entry(candidate),
            "status": "skipped",
            "reason": "already_synced_youtube",
            "youtube_video": youtube_video,
            "score": score,
            "queries": queries,
        }
    if youtube_video["id"] in target_liked_youtube_ids:
        stats["already_liked_on_target"] += 1
        return {
            **base_plan_entry(candidate),
            "status": "skipped",
            "reason": "already_liked_on_target",
            "youtube_video": youtube_video,
            "score": score,
            "queries": queries,
        }
    if youtube_video["id"] in blocked_youtube_ids:
        stats["blocked_youtube_rating"] += 1
        return {
            **base_plan_entry(candidate),
            "status": "skipped",
            "reason": "previous_youtube_rate_failure",
            "youtube_video": youtube_video,
            "score": score,
            "queries": queries,
        }

    entry = {
        **base_plan_entry(candidate),
        "status": "pending",
        "youtube_video": youtube_video,
        "score": score,
        "queries": queries,
    }
    if reason_prefix:
        entry["match_source"] = reason_prefix
    return entry


def serialize_youtube_video(video):
    snippet = video.get("snippet", {})
    return {
        "id": video["id"]["videoId"],
        "title": snippet.get("title", ""),
        "channel_title": snippet.get("channelTitle", ""),
        "published_at": snippet.get("publishedAt"),
    }


def youtube_video_from_reverse_match(item):
    return {
        "id": item["youtube_id"],
        "title": item.get("youtube_title") or "",
        "channel_title": item.get("youtube_channel_title") or "",
        "published_at": item.get("youtube_published_at"),
    }


def load_reverse_youtube_matches(sync_cache):
    if not sync_cache:
        return {}

    matches = {}
    for item in sync_cache.get("synced_items", []):
        youtube_id = item.get("youtube_id")
        if not youtube_id:
            continue
        if item.get("spotify_id"):
            matches[item["spotify_id"]] = item
        if item.get("candidate_key"):
            matches[item["candidate_key"]] = item
    return matches


def load_synced_spotify_ids(sync_cache):
    if not sync_cache:
        return set()
    return {
        item.get("spotify_id")
        for item in sync_cache.get("synced_items", [])
        if item.get("spotify_id")
    }


def load_synced_youtube_ids(sync_cache):
    if not sync_cache:
        return set()
    return {
        item.get("youtube_id")
        for item in sync_cache.get("synced_items", [])
        if item.get("youtube_id")
    }


def load_blocked_youtube_ids(sync_cache):
    if not sync_cache:
        return set()
    return {
        item.get("youtube_id")
        for item in sync_cache.get("blocked_items", [])
        if item.get("youtube_id")
    }


def mark_spotify_to_youtube_synced(sync_cache, entry):
    sync_cache.setdefault("synced_items", []).append(
        {
            "spotify_id": entry["spotify_id"],
            "spotify_name": entry["spotify_name"],
            "spotify_artists": entry["spotify_artists"],
            "candidate_key": entry["candidate_key"],
            "youtube_id": entry["youtube_video"]["id"],
            "youtube_title": entry["youtube_video"].get("title"),
            "sync_date": utc_now_iso(),
        }
    )
    sync_cache["last_sync"] = utc_now_iso()


def mark_spotify_to_youtube_blocked(sync_cache, entry, rate_result):
    blocked_items = sync_cache.setdefault("blocked_items", [])
    youtube_id = entry["youtube_video"]["id"]
    if any(item.get("youtube_id") == youtube_id for item in blocked_items):
        return
    blocked_items.append(
        {
            "spotify_id": entry["spotify_id"],
            "spotify_name": entry["spotify_name"],
            "spotify_artists": entry["spotify_artists"],
            "candidate_key": entry["candidate_key"],
            "youtube_id": youtube_id,
            "youtube_title": entry["youtube_video"].get("title"),
            "reason": rate_result["reason"],
            "blocked_at": utc_now_iso(),
        }
    )


def save_sync_cache(sync_cache):
    cache_file = sync_cache["cache_file"]
    data_to_save = {
        key: value for key, value in sync_cache.items() if key != "cache_file"
    }
    save_json_atomic(data_to_save, cache_file)
