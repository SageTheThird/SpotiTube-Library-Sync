import logging

from beatbridge.config import (
    NUMBER_OF_LIKED_SONGS_TO_FETCH_FROM_YT,
    youtube_to_youtube_plan_file,
    youtube_to_youtube_sync_file,
)
from beatbridge.storage import load_json_file, save_json_atomic
from beatbridge.youtube_client import (
    get_liked_videos,
    like_youtube_video_result,
)


logger = logging.getLogger(__name__)


def build_youtube_to_youtube_plan(
    source_youtube,
    source_profile,
    target_profile,
    sync_cache,
    limit=None,
    plan_file=None,
    target_liked_youtube_ids=None,
):
    plan_file = plan_file or youtube_to_youtube_plan_file(
        source_profile,
        target_profile,
    )
    liked_videos = get_liked_videos(
        source_youtube,
        max_results=limit or NUMBER_OF_LIKED_SONGS_TO_FETCH_FROM_YT,
    )
    synced_video_ids = load_synced_youtube_ids(sync_cache)
    blocked_video_ids = load_blocked_youtube_ids(sync_cache)
    target_liked_youtube_ids = set(target_liked_youtube_ids or [])

    entries = []
    stats = {
        "items": len(liked_videos),
        "already_synced": 0,
        "already_liked_on_target": 0,
        "blocked_youtube_rating": 0,
        "pending": 0,
    }

    for source_index, video in enumerate(liked_videos):
        entry = base_plan_entry(video, source_index)
        video_id = entry["youtube_video"]["id"]
        if video_id in synced_video_ids:
            stats["already_synced"] += 1
            entries.append({**entry, "status": "skipped", "reason": "already_synced"})
            continue
        if video_id in target_liked_youtube_ids:
            stats["already_liked_on_target"] += 1
            entries.append(
                {**entry, "status": "skipped", "reason": "already_liked_on_target"}
            )
            continue
        if video_id in blocked_video_ids:
            stats["blocked_youtube_rating"] += 1
            entries.append(
                {
                    **entry,
                    "status": "skipped",
                    "reason": "previous_youtube_rate_failure",
                }
            )
            continue
        entries.append({**entry, "status": "pending"})

    pending_entries = [entry for entry in entries if entry["status"] == "pending"]
    apply_queue = [entry["id"] for entry in reversed(pending_entries)]
    stats["pending"] = len(pending_entries)

    plan = {
        "source_profile": source_profile,
        "target_profile": target_profile,
        "entries": entries,
        "apply_queue": apply_queue,
        "summary": stats,
    }
    save_json_atomic(plan, plan_file)
    logger.info("Wrote YouTube-to-YouTube plan: %s", plan_file)
    logger.info("Plan summary: %s", plan["summary"])
    return plan


def apply_youtube_to_youtube_plan(
    target_youtube,
    source_profile,
    target_profile,
    sync_cache,
    dry_run=False,
    plan_file=None,
):
    plan_file = plan_file or youtube_to_youtube_plan_file(
        source_profile,
        target_profile,
    )
    plan = load_json_file(plan_file, default=None)
    if not plan:
        logger.info("No YouTube-to-YouTube plan found at %s", plan_file)
        return []

    refresh_youtube_to_youtube_pending_summary(plan)
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
                "Dry run: would like YouTube video %s on %s",
                video_id,
                target_profile,
            )
            liked_video_ids.append(video_id)
            continue

        rate_result = like_youtube_video_result(target_youtube, video_id)
        if rate_result["ok"]:
            entry["status"] = "liked"
            entry["liked_at"] = utc_now_iso()
            mark_youtube_to_youtube_synced(sync_cache, entry)
            liked_video_ids.append(video_id)
            refresh_youtube_to_youtube_pending_summary(plan)
            save_json_atomic(plan, plan_file)
            save_sync_cache(sync_cache)
            logger.info(
                "Liked YouTube video %s of %s on %s: %s",
                index,
                len(pending_entries),
                target_profile,
                video_id,
            )
            continue

        if not rate_result["retryable"]:
            entry["status"] = "skipped"
            entry["reason"] = f"youtube_rate_{rate_result['reason']}"
            entry["error"] = rate_result["message"]
            entry["skipped_at"] = utc_now_iso()
            mark_youtube_to_youtube_blocked(sync_cache, entry, rate_result)
            refresh_youtube_to_youtube_pending_summary(plan)
            save_json_atomic(plan, plan_file)
            save_sync_cache(sync_cache)
            logger.info(
                "Skipped unrateable YouTube video %s of %s on %s: %s",
                index,
                len(pending_entries),
                target_profile,
                video_id,
            )

    return liked_video_ids


def base_plan_entry(video, source_index):
    snippet = video.get("snippet", {})
    video_id = video.get("id")
    if isinstance(video_id, dict):
        video_id = video_id.get("videoId")
    return {
        "id": f"yt-mirror-{source_index}",
        "source_index": source_index,
        "youtube_video": {
            "id": video_id,
            "title": snippet.get("title", ""),
            "channel_title": snippet.get("channelTitle", ""),
            "published_at": snippet.get("publishedAt"),
        },
    }


def load_synced_youtube_ids(sync_cache):
    return {
        item.get("youtube_id")
        for item in sync_cache.get("synced_items", [])
        if item.get("youtube_id")
    }


def load_blocked_youtube_ids(sync_cache):
    return {
        item.get("youtube_id")
        for item in sync_cache.get("blocked_items", [])
        if item.get("youtube_id")
    }


def refresh_youtube_to_youtube_pending_summary(plan):
    entries_by_id = {entry["id"]: entry for entry in plan.get("entries", [])}
    plan["apply_queue"] = [
        entry_id
        for entry_id in plan.get("apply_queue", [])
        if entries_by_id.get(entry_id, {}).get("status") == "pending"
    ]
    plan.setdefault("summary", {})["pending"] = len(plan["apply_queue"])
    plan["summary"]["pending_youtube_ids"] = [
        entries_by_id[entry_id]["youtube_video"]["id"]
        for entry_id in plan["apply_queue"]
    ]


def mark_youtube_to_youtube_synced(sync_cache, entry):
    sync_cache.setdefault("synced_items", []).append(
        {
            "youtube_id": entry["youtube_video"]["id"],
            "youtube_title": entry["youtube_video"].get("title"),
            "sync_date": utc_now_iso(),
        }
    )
    sync_cache["last_sync"] = utc_now_iso()


def mark_youtube_to_youtube_blocked(sync_cache, entry, rate_result):
    blocked_items = sync_cache.setdefault("blocked_items", [])
    youtube_id = entry["youtube_video"]["id"]
    if any(item.get("youtube_id") == youtube_id for item in blocked_items):
        return
    blocked_items.append(
        {
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


def utc_now_iso():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
