"""
STEP 1 of the pipeline (Instagram-only version). Run this 8 hours before a scheduled slot time.

Picks the next unprocessed video from Drive, generates metadata with Groq,
makes the Drive file link-shareable (needed for Instagram), and queues it 
in publish_queue.json with the target live time.

Does NOT upload to YouTube -- this is Instagram-only.

    python upload_unlisted.py --slot A
    python upload_unlisted.py --slot B

Slot times are read from .env (SLOT_A_TIME, SLOT_B_TIME, daily, in TIMEZONE).
"""

import argparse
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

from auth import get_credentials
from metadata_generator import generate_metadata
from utils import load_json, save_json

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DRIVE_FOLDER_ID = os.environ["DRIVE_FOLDER_ID"]
TIMEZONE = os.environ.get("TIMEZONE", "Asia/Kolkata")

SLOT_TIMES = {
    "A": os.environ.get("SLOT_A_TIME", "17:30"),  # 5:30 PM IST default
    "B": os.environ.get("SLOT_B_TIME", "21:30"),  # 9:30 PM IST default
}

LOG_FILE = "processed_log.json"
QUEUE_FILE = "publish_queue.json"
TEMP_DIR = "temp_downloads"


# ---------------------------------------------------------------------------
# Drive helpers
# ---------------------------------------------------------------------------

def list_drive_videos(drive, folder_id: str) -> list[dict]:
    query = f"'{folder_id}' in parents and trashed = false"
    results = (
        drive.files()
        .list(q=query, fields="files(id, name, mimeType)", orderBy="name", pageSize=1000)
        .execute()
    )
    return [f for f in results.get("files", []) if f["mimeType"].startswith("video/")]


def make_shareable(drive, file_id: str) -> str:
    """Grant anyone-with-link viewer access and return a direct-download URL."""
    drive.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()
    return f"https://drive.google.com/uc?export=download&id={file_id}"


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

def next_slot_datetime(slot: str) -> datetime:
    """Return the next occurrence of *slot*'s time in TIMEZONE (tomorrow if already past)."""
    tz = ZoneInfo(TIMEZONE)
    now = datetime.now(tz)
    hour, minute = map(int, SLOT_TIMES[slot].split(":"))
    target = datetime(now.year, now.month, now.day, hour, minute, tzinfo=tz)
    if target <= now:
        target += timedelta(days=1)
    return target


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Queue a video for Instagram publishing.")
    parser.add_argument("--slot", choices=["A", "B"], required=True, help="Publishing slot (A or B)")
    args = parser.parse_args()

    creds = get_credentials()
    drive = build("drive", "v3", credentials=creds)

    log = load_json(LOG_FILE, {"processed_file_ids": []})
    queue = load_json(QUEUE_FILE, [])

    videos = list_drive_videos(drive, DRIVE_FOLDER_ID)
    next_video = next(
        (v for v in videos if v["id"] not in log["processed_file_ids"]), None
    )

    if not next_video:
        logger.info("No new videos to process.")
        return

    logger.info("Next video: %s", next_video["name"])

    logger.info("Generating metadata with Groq...")
    metadata = generate_metadata(next_video["name"])

    logger.info("Making Drive file link-shareable for Instagram...")
    drive_public_url = make_shareable(drive, next_video["id"])

    go_live_at = next_slot_datetime(args.slot)
    logger.info("Queued to post to Instagram at: %s", go_live_at.isoformat())

    queue.append({
        "drive_file_id": next_video["id"],
        "drive_public_url": drive_public_url,
        "ig_caption": metadata["ig_caption"],
        "go_live_at": go_live_at.isoformat(),
        "slot": args.slot,
        "published": False,
    })
    save_json(QUEUE_FILE, queue)

    log["processed_file_ids"].append(next_video["id"])
    save_json(LOG_FILE, log)

    logger.info("Done. Video will post to Instagram at the scheduled time.")


if __name__ == "__main__":
    main()
