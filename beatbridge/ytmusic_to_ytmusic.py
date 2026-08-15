import logging
from datetime import datetime, timezone

from ytmusicapi.models.content.enums import LikeStatus

from beatbridge.config import (
    ytmusic_to_ytmusic_plan_file,
    ytmusic_to_ytmusic_sync_file,
)
from beatbridge.storage import load_json_file, save_json_atomic


logger = logging.getLogger(__name__)


def build_ytmusic_to_ytmusic_plan(
    source_ytmusic,
    target_ytmusic,
    source_profile,
    target_profile,
    source_kind,
    sync_cache,
    limit=None,
    plan_file=None,
):
    plan_file = plan_file or ytmusic_to_ytmusic_plan_file(
        source_profile,
        target_profile,
        source_kind,
    )
    source_items = fetch_ytmusic_items(source_ytmusic, source_kind, limit=limit)
    target_liked_ids = fetch_ytmusic_liked_ids(target_ytmusic, limit=limit)
    synced_ids = load_synced_video_ids(sync_cache)
    blocked_ids = load_blocked_video_ids(sync_cache)

    entries = []
    seen_ids = set()
    stats = {
        "items": len(source_items),
        "duplicates_in_run": 0,
        "missing_video_id": 0,
        "already_synced": 0,
        "already_liked_on_target": 0,
        "blocked": 0,
        "pending": 0,
    }

    for source_index, item in enumerate(source_items):
        entry = base_plan_entry(item, source_index)
        video_id = entry["ytmusic_item"]["video_id"]
        if not video_id:
            stats["missing_video_id"] += 1
            entries.append({**entry, "status": "skipped", "reason": "missing_video_id"})
            continue
        if video_id in seen_ids:
            stats["duplicates_in_run"] += 1
            entries.append({**entry, "status": "skipped", "reason": "duplicate_in_run"})
            continue
        seen_ids.add(video_id)
        if video_id in synced_ids:
            stats["already_synced"] += 1
            entries.append({**entry, "status": "skipped", "reason": "already_synced"})
            continue
        if video_id in target_liked_ids:
            stats["already_liked_on_target"] += 1
            entries.append(
                {**entry, "status": "skipped", "reason": "already_liked_on_target"}
            )
            continue
        if video_id in blocked_ids:
            stats["blocked"] += 1
            entries.append({**entry, "status": "skipped", "reason": "previous_failure"})
            continue
        entries.append({**entry, "status": "pending"})

    pending_entries = [entry for entry in entries if entry["status"] == "pending"]
    stats["pending"] = len(pending_entries)
    plan = {
        "created_at": utc_now_iso(),
        "source_profile": source_profile,
        "target_profile": target_profile,
        "source_kind": source_kind,
        "entries": entries,
        "apply_queue": [entry["id"] for entry in reversed(pending_entries)],
        "summary": {
            **stats,
            "pending_video_ids": [
                entry["ytmusic_item"]["video_id"] for entry in pending_entries
            ],
        },
    }
    save_json_atomic(plan, plan_file)
    logger.info("Wrote YouTube Music plan: %s", plan_file)
    logger.info("Plan summary: %s", without_long_ids(plan["summary"]))
    return plan


def apply_ytmusic_to_ytmusic_plan(
    target_ytmusic,
    source_profile,
    target_profile,
    source_kind,
    sync_cache,
    dry_run=False,
    plan_file=None,
):
    plan_file = plan_file or ytmusic_to_ytmusic_plan_file(
        source_profile,
        target_profile,
        source_kind,
    )
    plan = load_json_file(plan_file, default=None)
    if not plan:
        logger.info("No YouTube Music plan found at %s", plan_file)
        return []

    refresh_pending_summary(plan)
    save_json_atomic(plan, plan_file)
    entries_by_id = {entry["id"]: entry for entry in plan["entries"]}
    pending_entries = [
        entries_by_id[entry_id]
        for entry_id in plan.get("apply_queue", [])
        if entries_by_id.get(entry_id, {}).get("status") == "pending"
    ]
    if not pending_entries:
        logger.info("No pending YouTube Music items in %s", plan_file)
        return []

    liked_ids = []
    for index, entry in enumerate(pending_entries, start=1):
        video_id = entry["ytmusic_item"]["video_id"]
        if dry_run:
            logger.info(
                "Dry run: would like YouTube Music item %s on %s",
                video_id,
                target_profile,
            )
            liked_ids.append(video_id)
            continue
        try:
            target_ytmusic.rate_song(video_id, LikeStatus.LIKE)
        except Exception as exc:
            entry["last_error"] = str(exc)
            plan.setdefault("summary", {})["stopped_reason"] = type(exc).__name__
            plan["summary"]["stopped_at"] = utc_now_iso()
            refresh_pending_summary(plan)
            save_json_atomic(plan, plan_file)
            save_sync_cache(sync_cache)
            logger.warning(
                "Stopping YouTube Music apply after failure on %s: %s",
                video_id,
                exc,
            )
            break

        entry["status"] = "liked"
        entry["liked_at"] = utc_now_iso()
        mark_synced(sync_cache, entry)
        liked_ids.append(video_id)
        refresh_pending_summary(plan)
        save_json_atomic(plan, plan_file)
        save_sync_cache(sync_cache)
        logger.info(
            "Liked YouTube Music item %s of %s on %s: %s",
            index,
            len(pending_entries),
            target_profile,
            video_id,
        )

    return liked_ids


def fetch_ytmusic_items(ytmusic, source_kind, limit=None):
    effective_limit = limit or 10000
    if source_kind == "liked":
        liked = ytmusic.get_liked_songs(limit=effective_limit)
        return normalize_items(liked.get("tracks", []), source_kind)
    if source_kind == "library":
        return normalize_items(
            ytmusic.get_library_songs(
                limit=effective_limit,
                order="recently_added",
                validate_responses=True,
            ),
            source_kind,
        )
    if source_kind == "both":
        liked = ytmusic.get_liked_songs(limit=effective_limit).get("tracks", [])
        library = ytmusic.get_library_songs(
            limit=effective_limit,
            order="recently_added",
            validate_responses=True,
        )
        return dedupe_items(
            normalize_items(liked, "liked") + normalize_items(library, "library")
        )
    raise ValueError("--ytmusic-source must be liked, library, or both")


def fetch_ytmusic_liked_ids(ytmusic, limit=None):
    liked = ytmusic.get_liked_songs(limit=limit or 10000)
    return {
        item["video_id"]
        for item in normalize_items(liked.get("tracks", []), "liked")
        if item.get("video_id")
    }


def normalize_items(items, source_kind):
    normalized = []
    for item in items:
        artists = item.get("artists") or []
        normalized.append(
            {
                "video_id": item.get("videoId"),
                "title": item.get("title") or "",
                "artists": [
                    artist.get("name", "")
                    for artist in artists
                    if isinstance(artist, dict) and artist.get("name")
                ],
                "album": (item.get("album") or {}).get("name"),
                "duration": item.get("duration"),
                "source_kind": source_kind,
            }
        )
    return normalized


def dedupe_items(items):
    seen = set()
    deduped = []
    for item in items:
        key = item.get("video_id") or (
            item.get("title"),
            tuple(item.get("artists", [])),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def base_plan_entry(item, source_index):
    return {
        "id": f"ytmusic-{source_index}",
        "source_index": source_index,
        "ytmusic_item": item,
    }


def load_synced_video_ids(sync_cache):
    return {
        item.get("video_id")
        for item in sync_cache.get("synced_items", [])
        if item.get("video_id")
    }


def load_blocked_video_ids(sync_cache):
    return {
        item.get("video_id")
        for item in sync_cache.get("blocked_items", [])
        if item.get("video_id")
    }


def refresh_pending_summary(plan):
    entries_by_id = {entry["id"]: entry for entry in plan.get("entries", [])}
    plan["apply_queue"] = [
        entry_id
        for entry_id in plan.get("apply_queue", [])
        if entries_by_id.get(entry_id, {}).get("status") == "pending"
    ]
    plan.setdefault("summary", {})["pending"] = len(plan["apply_queue"])
    plan["summary"]["pending_video_ids"] = [
        entries_by_id[entry_id]["ytmusic_item"]["video_id"]
        for entry_id in plan["apply_queue"]
    ]


def mark_synced(sync_cache, entry):
    item = entry["ytmusic_item"]
    sync_cache.setdefault("synced_items", []).append(
        {
            "video_id": item["video_id"],
            "title": item.get("title"),
            "artists": item.get("artists", []),
            "source_kind": item.get("source_kind"),
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


def without_long_ids(summary):
    return {
        key: value
        for key, value in summary.items()
        if key not in ("pending_video_ids",)
    }


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()
