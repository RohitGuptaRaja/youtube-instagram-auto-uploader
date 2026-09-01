# YouTube to Instagram Auto-Uploader

![License](https://img.shields.io/github/license/RohitGuptaRaja/youtube-instagram-auto-uploader)
![Last Commit](https://img.shields.io/github/last-commit/RohitGuptaRaja/youtube-instagram-auto-uploader)
![Stars](https://img.shields.io/github/stars/RohitGuptaRaja/youtube-instagram-auto-uploader?style=social)

Automatically publishes your latest YouTube Shorts to Instagram Reels on a schedule, twice a day, **completely free** — using Groq for AI-generated captions and GitHub Actions for cloud automation. No paid tools, no server to maintain, no laptop that needs to stay on.

---

Upload Shorts to YouTube, and this pipeline automatically detects them, downloads the video, generates an Instagram-friendly caption with Groq, and publishes to **Instagram Reels** at scheduled times, twice a day. **No Drive folder needed!** Works seamlessly whether you upload daily or on your own schedule.

## Quick start

1. **Fork this repo**
2. Get free API access: [Groq](https://console.groq.com/keys) (captions) + [Google Cloud](https://console.cloud.google.com/) (YouTube API) + [Meta Developers](https://developers.facebook.com/) (Instagram)
3. Add your credentials as **GitHub Secrets** (Settings → Secrets and variables → Actions) — see [Configure](#configure) below for the full list
4. Enable GitHub Actions on your fork (Actions tab → "I understand, enable")
5. Upload Shorts to YouTube — the pipeline picks them up automatically

Full setup walkthrough below if you want the details on each step.

## How it works

The pipeline is split into two scripts:

| Script | Runs | Does |
|---|---|---|
| `youtube_to_instagram.py` | 8 hours before a slot | Fetches latest Shorts from your channel, downloads video, generates caption with Groq |
| `publish_scheduled.py` | Every 10-15 min (checks the clock) | At the exact slot time: uploads video to **Instagram Reels** |

**Flow:** YouTube Upload → Auto-Detect Shorts → Download → Caption Generation → Queue → Instagram Post

## Default daily slots (edit in `.env`)

- **Slot A: 5:30 PM IST** = 8:00 AM ET = 1:00 PM UK — US morning commute, UK lunch
- **Slot B: 9:30 PM IST** = 12:00 PM ET = 5:00 PM UK — US lunch, UK evening commute

That's 2 videos/day, automatically cross-posted from YouTube to Instagram.

## One-time setup

### 1. Google Cloud project (YouTube API)

1. https://console.cloud.google.com/ → new project.
2. Enable **YouTube Data API v3**.
3. OAuth consent screen: External, add yourself as a test user.
4. Create OAuth Client ID (Desktop app), download JSON as `client_secret.json` in this folder.

### 2. Get your YouTube Channel ID

1. Go to YouTube Studio: https://studio.youtube.com/
2. Click your profile icon (top right) → Settings → Basic Info
3. Copy your **Channel ID**
4. Put it in `.env` as `YOUTUBE_CHANNEL_ID`

### 3. Meta / Instagram setup

Instagram's API requires a Business or Creator account linked to a Facebook Page.

1. Create a Facebook account if you don't have one: https://www.facebook.com/
2. Create a Facebook Page (any name/category is fine — it just needs to exist): https://www.facebook.com/pages/create
3. On Instagram: Settings → Account type → switch to **Professional account** → choose **Creator** or **Business** → link it to the Page you just made.
4. Go to https://developers.facebook.com/ → create an app (type: **Business**).
5. In the app, add the **Instagram Graph API** product.
6. Use the **Graph API Explorer** (developers.facebook.com/tools/explorer) to:
   - Select your app, generate a **User Access Token** with `instagram_basic`, `instagram_content_publish`, and `pages_show_list` permissions.
   - Exchange it for a **long-lived token** (60 days) — the Explorer has a button for this, or use the `/oauth/access_token` endpoint with `grant_type=fb_exchange_token`.
   - Find your **Instagram Business Account ID**: call `GET /me/accounts` to get your Page ID, then `GET /{page-id}?fields=instagram_business_account`.
7. Put both values in `.env` as `META_ACCESS_TOKEN` and `IG_BUSINESS_ACCOUNT_ID`.

Note: long-lived tokens expire after 60 days — you'll need to refresh it periodically (a reminder on your calendar is easiest).

### 4. Python environment

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Authenticate Google (one-time, opens a browser)

```bash
python oauth_setup.py
```

### 6. Configure

Copy `.env.example` to `.env` and fill in:
- `YOUTUBE_CHANNEL_ID` (from YouTube Studio)
- `GROQ_API_KEY` (from Groq console)
- `SLOT_A_TIME` / `SLOT_B_TIME` (defaults already set)
- `META_ACCESS_TOKEN` / `IG_BUSINESS_ACCOUNT_ID` (from Meta setup above)

### 7. Run

Queue your latest YouTube Shorts for slot A (run this ~8 hours before 5:30 PM IST, e.g. 9:30 AM):
```bash
python youtube_to_instagram.py --slot A
```

Queue for slot B (run ~8 hours before 9:30 PM IST, e.g. 1:30 PM):
```bash
python youtube_to_instagram.py --slot B
```

Then keep this running on a schedule so queued videos actually go live:
```bash
python publish_scheduled.py
```

## Automating: runs in the cloud via GitHub Actions (no laptop needed)

This pipeline runs on GitHub's servers on a schedule — your computer can be off.
Here's what's set up and why:

**1. Code lives in a private GitHub repo**, pushed with `git push`. `.gitignore`
keeps `.env`, `client_secret.json`, and `token.json` out of the repo — those are
secrets and should never be committed.

**2. Secrets are stored in GitHub → Settings → Secrets and variables → Actions**,
encrypted, one per value:
- `YOUTUBE_CHANNEL_ID`
- `GROQ_API_KEY`
- `META_ACCESS_TOKEN`
- `IG_BUSINESS_ACCOUNT_ID`
- `GOOGLE_CLIENT_SECRET_JSON` — the full contents of your local `client_secret.json`
- `GOOGLE_TOKEN_JSON` — the full contents of your local `token.json`

**3. `.github/workflows/pipeline.yml`** is the automation itself. On each scheduled
run, it: checks out the repo → installs dependencies → rebuilds `client_secret.json`
and `token.json` from the two secrets above → runs the right script for that time
slot → commits the updated `processed_log.json`/`publish_queue.json` back to the
repo so the next run remembers what's already been done.

**4. Three schedules** (cron times are UTC, converted from IST):
- Slot A fetch: `0 4 * * *` (9:30 AM IST)
- Slot B fetch: `0 8 * * *` (1:30 PM IST)
- Publish check: `*/15 * * * *` (every 15 min, all day)

**5. Manual testing**: GitHub repo → Actions tab → "PoddyGo Pipeline" → "Run workflow"
button — triggers an on-demand run without waiting for the schedule.

### Token expiry dates to track

- **Google refresh token expires in 7 days** unless the OAuth app is moved out of
  "Testing" mode. Fix: Google Cloud Console → your project → **Google Auth Platform → Audience** → **Publish app**. Do this once, early — it removes the 7-day limit.
- **Meta access token expires in ~60 days**. When it expires, Instagram posting silently fails. Fix: redo the `fb_exchange_token` exchange (see Meta setup section above) and update the `META_ACCESS_TOKEN` secret on GitHub with the new token.

## Notes

- Video is downloaded from YouTube using `yt-dlp` and temporarily hosted via `file.io` before Instagram processes it.
- `publish_queue.json` tracks what's waiting to go live; `processed_log.json` tracks what's already been picked from YouTube so nothing gets posted twice.
- If Instagram publish fails, the script logs it and continues — check the console output and retry manually if needed.
- Only Shorts (videos <90 seconds or with `#shorts` in the title) are picked up automatically.
- Works whether you upload daily or sporadically — the script fetches your latest Shorts at scheduled times.

## Why YouTube-to-Instagram?

- ✅ **No manual step** — upload once to YouTube, automatically on Instagram
- ✅ **No Drive folder** — simplifies your workflow
- ✅ **Instant availability** — YouTube Shorts go live immediately, system picks them up at scheduled times
- ✅ **Organic growth** — both platforms benefit from your content
- ✅ **Free** — no YouTube Premium, Meta verified status, or paid tools needed
