"""
STEP 1 of the new pipeline: YouTube to Instagram Auto-Uploader

This script:
1. Connects to your YouTube channel
2. Finds your latest uploaded Shorts
3. Downloads the video
4. Generates Instagram caption with Groq
5. Queues it for Instagram posting

No Drive folder needed anymore - directly from YouTube to Instagram!

    python youtube_to_instagram.py --slot A
    python youtube_to_instagram.py --slot B

Slot times are read from .env (SLOT_A_TIME, SLOT_B_TIME, daily, in TIMEZONE).
"""

import argparse
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import yt_dlp

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

TIMEZONE = os.environ.get("TIMEZONE", "Asia/Kolkata")
YOUTUBE_CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID")  # Your channel ID

SLOT_TIMES = {
    "A": os.environ.get("SLOT_A_TIME", "17:30"),  # 5:30 PM IST default
    "B": os.environ.get("SLOT_B_TIME", "21:30"),  # 9:30 PM IST default
}

LOG_FILE = "processed_log.json"
QUEUE_FILE = "publish_queue.json"
TEMP_DIR = "temp_downloads"


# ---------------------------------------------------------------------------
# YouTube helpers
# ---------------------------------------------------------------------------

def get_latest_shorts(youtube, channel_id: str) -> dict | None:
    """Get the latest Shorts video from your channel."""
    try:
        # Search for latest uploads from your channel
        search_response = youtube.search().list(
            channelId=channel_id,
            part="snippet",
            order="date",
            type="video",
            maxResults=50,  # Check last 50 videos
            fields="items(id(videoId),snippet(title,publishedAt))"
        ).execute()

        if not search_response.get("items"):
            logger.info("No videos found on your channel.")
            return None

        # Filter for Shorts (usually <90 seconds, or check if #shorts in title)
        for item in search_response["items"]:
            video_id = item["id"]["videoId"]
            title = item["snippet"]["title"]
            
            # Get video details to check duration
            video_response = youtube.videos().list(
                id=video_id,
                part="contentDetails,snippet",
                fields="items(id,contentDetails(duration),snippet(title,description))"
            ).execute()

            if video_response["items"]:
                video = video_response["items"][0]
                duration_str = video["contentDetails"]["duration"]
                
                # Parse duration (format: PT1M30S)
                import re
                match = re.match(r'PT(?:(\d+)M)?(?:(\d+)S)?', duration_str)
                if match:
                    minutes = int(match.group(1) or 0)
                    seconds = int(match.group(2) or 0)
                    total_seconds = minutes * 60 + seconds
                    
                    # Shorts are typically < 90 seconds
                    if total_seconds <= 90 or "#shorts" in title.lower():
                        logger.info("Found Shorts video: %s (Duration: %s)", title, duration_str)
                        return {
                            "video_id": video_id,
                            "title": title,
                            "description": video["snippet"]["description"],
                            "url": f"https://www.youtube.com/watch?v={video_id}"
                        }

        logger.info("No Shorts found in recent uploads.")
        return None

    except Exception as exc:
        logger.error("Error fetching YouTube Shorts: %s", exc)
        return None


def download_youtube_video(video_url: str, filename: str) -> str:
    """Download YouTube video using yt-dlp and return local path."""
    os.makedirs(TEMP_DIR, exist_ok=True)
    local_path = os.path.join(TEMP_DIR, filename)
    
    try:
        ydl_opts = {
            'format': 'best[ext=mp4]',
            'outtmpl': local_path.replace('.mp4', ''),
            'quiet': False,
            'no_warnings': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info("Downloading video from YouTube...")
            info = ydl.extract_info(video_url, download=True)
            downloaded_path = ydl.prepare_filename(info)
            logger.info("Downloaded to: %s", downloaded_path)
            return downloaded_path
            
    except Exception as exc:
        logger.error("Failed to download YouTube video: %s", exc)
        raise


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
    parser = argparse.ArgumentParser(description="Queue latest YouTube Shorts to Instagram.")
    parser.add_argument("--slot", choices=["A", "B"], required=True, help="Publishing slot (A or B)")
    args = parser.parse_args()

    if not YOUTUBE_CHANNEL_ID:
        logger.error("YOUTUBE_CHANNEL_ID not set in .env")
        return

    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    log = load_json(LOG_FILE, {"processed_video_ids": []})
    queue = load_json(QUEUE_FILE, [])

    # Get latest Shorts
    logger.info("Fetching latest Shorts from your YouTube channel...")
    shorts_video = get_latest_shorts(youtube, YOUTUBE_CHANNEL_ID)

    if not shorts_video:
        logger.info("No new Shorts to process.")
        return

    video_id = shorts_video["video_id"]

    # Check if already processed
    if video_id in log["processed_video_ids"]:
        logger.info("This video has already been processed.")
        return

    logger.info("Processing: %s", shorts_video["title"])

    try:
        # Download the video
        logger.info("Downloading video...")
        local_path = download_youtube_video(shorts_video["url"], f"{video_id}.mp4")

        # Generate Instagram caption using Groq
        logger.info("Generating Instagram caption with Groq...")
        # Use YouTube title/description for metadata generation
        metadata = generate_metadata(shorts_video["title"])

        go_live_at = next_slot_datetime(args.slot)
        logger.info("Queued to post to Instagram at: %s", go_live_at.isoformat())

        # Queue for Instagram posting
        queue.append({
            "youtube_video_id": video_id,
            "youtube_url": shorts_video["url"],
            "local_video_path": local_path,
            "ig_caption": metadata["ig_caption"],
            "go_live_at": go_live_at.isoformat(),
            "slot": args.slot,
            "published": False,
        })
        save_json(QUEUE_FILE, queue)

        log["processed_video_ids"].append(video_id)
        save_json(LOG_FILE, log)

        logger.info("Done. Video will post to Instagram at the scheduled time.")

    except Exception as exc:
        logger.error("Error processing video: %s", exc)
        # Clean up downloaded file if it exists
        if 'local_path' in locals() and os.path.exists(local_path):
            os.remove(local_path)


if __name__ == "__main__":
    main()
