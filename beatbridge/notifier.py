import json
import logging
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from beatbridge.config import DISCORD_WEBHOOK_URL, NOTIFY_ON_PLAN_ONLY


logger = logging.getLogger(__name__)


def notify_sync_summary(summary):
    if not DISCORD_WEBHOOK_URL:
        logger.debug("Discord webhook is not configured; skipping notification.")
        return False
    if summary.get("plan_only") and not NOTIFY_ON_PLAN_ONLY:
        logger.debug("Plan-only notification disabled; skipping notification.")
        return False

    payload = {"content": format_sync_summary(summary)}
    request = Request(
        DISCORD_WEBHOOK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "BeatBridge/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            if response.status >= 300:
                logger.warning("Discord notification returned HTTP %s", response.status)
                return False
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.warning(
            "Discord notification failed with HTTP %s: %s",
            exc.code,
            body,
        )
        return False
    except URLError as exc:
        logger.warning("Discord notification failed: %s", exc.reason)
        return False

    logger.info("Discord notification sent.")
    return True


def format_sync_summary(summary):
    if summary.get("failed"):
        status = "failed"
    elif summary.get("dry_run"):
        status = "dry run"
    else:
        status = "completed"
    mode = "plan" if summary.get("plan_only") else summary.get("mode", "sync")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"BeatBridge sync {status}",
        f"Time: {timestamp}",
        f"Direction: {summary.get('direction')}",
        f"Mode: {mode}",
    ]

    workflows = summary.get("workflows") or []
    for workflow in workflows:
        label = workflow.get("label", workflow.get("direction", "workflow"))
        if summary.get("failed"):
            lines.append(f"- {label}: failed before completing")
        elif workflow.get("plan_only"):
            lines.append(
                f"- {label}: built plan with {workflow.get('planned', 0)} pending item(s)"
            )
        elif workflow.get("dry_run"):
            lines.append(
                f"- {label}: would sync {workflow.get('processed', 0)} item(s)"
            )
        else:
            lines.append(f"- {label}: synced {workflow.get('processed', 0)} item(s)")

        skipped = workflow.get("skipped")
        not_found = workflow.get("not_found")
        if skipped is not None or not_found is not None:
            detail = []
            if skipped is not None:
                detail.append(f"skipped {skipped}")
            if not_found is not None:
                detail.append(f"not found {not_found}")
            lines[-1] += f" ({', '.join(detail)})"

    if not workflows:
        lines.append("- No workflow summary was produced.")

    return "\n".join(lines)
