# Zero-Cost Daily 3x Social Media Automation
**Channels:** YouTube Shorts (`TheKyunProject`) + Instagram Reels (`@psychologist.uday`)  
**Schedule:** Daily at **7:00 AM**, **1:00 PM**, and **7:00 PM IST** (3 posts/day)  
**Cost:** **₹0 / $0 Forever** (GitHub Actions Free Tier + Google Drive API + YouTube Data API v3 + Meta Graph API + Gemini 3.8 Flash Free Tier)

---

## How It Works

1. **Drop Videos in Google Drive:** Save your 9:16 vertical `.mp4` videos into your Google Drive `Queue` folder.
2. **GitHub Actions Wakes Up 3x/Day:** At **7:00 AM**, **1:00 PM**, and **7:00 PM IST**, the workflow in [`.github/workflows/daily_poster.yml`](./.github/workflows/daily_poster.yml) runs automatically in the cloud.
3. **Gemini Multimodal Video Analysis:** [`src/ai_metadata.py`](./src/ai_metadata.py) uploads the video to the Gemini Files API, watches & listens to it with `gemini-3.8-flash`, and generates:
   - **YouTube Title, SEO Description & 15 Search Tags** tailored to **TheKyunProject** ("The Why Project" curiosity-gap framing + `#Shorts`).
   - **Instagram Reel Viral Caption & 15 Hashtags** tailored to **@psychologist.uday** (2-sentence hook, psychological mechanism, actionable shift, and Save/Share CTA).
4. **Simultaneous Publishing:**
   - [`src/youtube_uploader.py`](./src/youtube_uploader.py) uploads the Short to **TheKyunProject**.
   - [`src/instagram_uploader.py`](./src/instagram_uploader.py) uploads the Reel to **@psychologist.uday** using Meta's Resumable Upload API (no external S3 bucket needed).
5. **Auto-Archive:** [`src/gdrive_manager.py`](./src/gdrive_manager.py) moves the posted video from your `Queue` folder into your `Posted` archive folder so it never double-posts.

---

## Quick Setup Commands

```powershell
# 1. Install dependencies locally for one-time token setup
pip install -r requirements.txt

# 2. Generate GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET & GOOGLE_REFRESH_TOKEN
python scripts/setup_oauth.py

# 3. Exchange short-lived Meta token for 60-day IG_ACCESS_TOKEN & discover IG_USER_ID
python scripts/setup_instagram_token.py --app-id YOUR_APP_ID --app-secret YOUR_APP_SECRET --token SHORT_TOKEN

# 4. Test locally with a dry-run (watches oldest video in Drive & prints AI metadata without posting)
python -m src.main --dry-run
```
