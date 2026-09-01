"""
STEP 2 of the pipeline (YouTube-to-Instagram version). Run this on a frequent schedule 
(e.g. every 10-15 min via Task Scheduler or GitHub Actions). It checks 
publish_queue.json for anything whose go_live_at time has arrived, then:

   1. Uploads the local video file to Instagram as a Reel
   2. Prunes old published entries from the queue (keeps file size bounded)

    python publish_scheduled.py
"""

import logging
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

from instagram_uploader import publish_reel_from_file
from utils import load_json, save_json

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

TIMEZONE_STR = os.environ.get("TIMEZONE", "Asia/Kolkata")
QUEUE_FILE = "publish_queue.json"

# Prune published entries older than this many days to keep the queue file small
QUEUE_PRUNE_DAYS = int(os.environ.get("QUEUE_PRUNE_DAYS", "30"))


# ---------------------------------------------------------------------------
# Queue helpers
# ---------------------------------------------------------------------------

def prune_queue(queue: list[dict]) -> list[dict]:
    """Remove published entries older than QUEUE_PRUNE_DAYS to keep file bounded."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=QUEUE_PRUNE_DAYS)
    before = len(queue)
    queue = [
        item for item in queue
        if not item.get("published")
        or datetime.fromisoformat(item["go_live_at"]) >= cutoff
    ]
    pruned = before - len(queue)
    if pruned:
        logger.info("Pruned %d old published entries from queue.", pruned)
    return queue


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(TIMEZONE_STR)
    now = datetime.now(tz)

    queue = load_json(QUEUE_FILE, [])
    due = [
        item for item in queue
        if not item.get("published")
        and datetime.fromisoformat(item["go_live_at"]) <= now
    ]

    if not due:
        logger.info("Nothing due yet.")
        return

    for item in due:
        local_video_path = item.get("local_video_path")
        logger.info("Publishing slot %s video to Instagram", item["slot"])

        # Check if video file exists
        if not local_video_path or not os.path.exists(local_video_path):
            logger.error("  Video file not found at %s", local_video_path)
            # Mark as published anyway so we don't retry indefinitely
            item["published"] = True
            continue

        logger.info("  Posting to Instagram as Reel...")
        try:
            ig_media_id = publish_reel_from_file(local_video_path, item["ig_caption"])
            logger.info("  Instagram media ID: %s", ig_media_id)
        except Exception as exc:
            logger.error(
                "  Instagram publish FAILED: %s", exc
            )
            # Continue processing other items; don't mark as published so it
            # can be retried manually.
            continue

        # Clean up the local video file after successful upload
        try:
            if os.path.exists(local_video_path):
                os.remove(local_video_path)
                logger.info("  Cleaned up local video file")
        except Exception as exc:
            logger.warning("  Could not delete local video file: %s", exc)

        item["published"] = True

    # Prune old entries and persist
    queue = prune_queue(queue)
    save_json(QUEUE_FILE, queue)
    logger.info("Done.")


if __name__ == "__main__":
    main()
