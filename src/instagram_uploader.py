import logging
import time
from pathlib import Path
from typing import Optional
import requests
from googleapiclient.discovery import build

from src.ai_metadata import ViralMetadata
from src.config import Config
from src.gdrive_manager import get_google_credentials

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"
GRAPH_BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
RUPLOAD_BASE_URL = f"https://rupload.facebook.com/ig-api-upload/{GRAPH_API_VERSION}"


def _upload_temp_public_video(video_path: Path) -> str:
    """
    Uploads the video file to a direct-download HTTPS host (catbox.moe)
    so Make.com's official Meta Instagram module can fetch the raw .mp4 stream.
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    with open(video_path, "rb") as fh:
        resp = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": (video_path.name, fh, "video/mp4")},
            headers=headers,
            timeout=180,
        )
    if resp.ok and resp.text.strip().startswith("https://"):
        return resp.text.strip()

    raise RuntimeError(f"Temporary video hosting on catbox failed ({resp.status_code}): {resp.text}")


def upload_to_instagram_via_make(
    video_path: Path,
    metadata: ViralMetadata,
    config: Config,
    gdrive_file_id: Optional[str] = None,
) -> str:
    """
    Publishes the Reel to @psychologist.uday via Make.com's official Meta-verified
    Instagram for Business integration (bypasses developers.facebook.com registration).
    Uses direct Google Drive CDN stream if gdrive_file_id is available, or catbox direct link.
    """
    public_video_url = None

    if gdrive_file_id:
        try:
            creds = get_google_credentials(config)
            drive = build("drive", "v3", credentials=creds)
            # Ensure anyone with link can read so Meta can download the mp4
            drive.permissions().create(
                fileId=gdrive_file_id,
                body={"role": "reader", "type": "anyone"},
            ).execute()
            candidate_url = f"https://drive.usercontent.google.com/download?id={gdrive_file_id}&export=download&confirm=t"
            with requests.get(
                candidate_url,
                headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-1023"},
                stream=True,
                timeout=30,
            ) as check_resp:
                content_type = check_resp.headers.get("Content-Type", "").lower()
                if check_resp.ok and ("video/" in content_type or "application/octet-stream" in content_type):
                    public_video_url = candidate_url
                    logger.info(
                        "Using verified direct Google Drive CDN stream URL (%s) for Make.com: %s",
                        content_type,
                        public_video_url,
                    )
                else:
                    logger.warning(
                        "Drive URL returned non-video Content-Type '%s'; falling back to direct host upload...",
                        content_type,
                    )
        except Exception as exc:
            logger.warning("Could not set Drive public stream link (%s); falling back to direct host upload...", exc)

    if not public_video_url:
        logger.info("Generating temporary direct HTTPS video stream for Make.com -> Instagram...")
        public_video_url = _upload_temp_public_video(video_path)

    logger.info("Direct video URL ready for Instagram: %s", public_video_url)

    payload = {
        "dedup_id": gdrive_file_id or video_path.stem,
        "video_url": public_video_url,
        "caption": metadata.instagram_caption[:2200],
        "share_to_feed": config.share_to_ig_feed,
        "youtube_title": metadata.youtube_title,
    }
    logger.info("Triggering Make.com Official Instagram Reel webhook...")
    resp = requests.post(config.make_ig_webhook_url, json=payload, timeout=120)
    if not resp.ok:
        raise RuntimeError(f"Make.com Instagram webhook failed ({resp.status_code}): {resp.text}")

    logger.info("Successfully triggered Instagram Reel publish via Make.com! Response: %s", resp.text[:200])
    return resp.text.strip() or "make_webhook_dispatched"


def upload_to_instagram(
    video_path: Path,
    metadata: ViralMetadata,
    config: Config,
    gdrive_file_id: Optional[str] = None,
) -> str:
    """
    Uploads a vertical video as an Instagram Reel to @psychologist.uday using either:
    1. Make.com Official Meta Partner Webhook (if MAKE_IG_WEBHOOK_URL is set), or
    2. Direct Meta Graph API Resumable Upload protocol (if IG_USER_ID + IG_ACCESS_TOKEN are set).
    Returns the published Instagram Media ID.
    """
    if config.make_ig_webhook_url and config.make_ig_webhook_url.startswith("https://"):
        return upload_to_instagram_via_make(video_path, metadata, config, gdrive_file_id=gdrive_file_id)

    file_size = video_path.stat().st_size

    # Step 1: Initialize Resumable Reel Container
    logger.info("Initializing Instagram Reels container for @psychologist.uday...")
    init_url = f"{GRAPH_BASE_URL}/{config.ig_user_id}/media"
    init_payload = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": metadata.instagram_caption[:2200],
        "share_to_feed": "true" if config.share_to_ig_feed else "false",
        "access_token": config.ig_access_token,
    }
    init_resp = requests.post(init_url, data=init_payload, timeout=60)
    if not init_resp.ok:
        raise RuntimeError(f"Instagram container initialization failed ({init_resp.status_code}): {init_resp.text}")

    init_data = init_resp.json()
    container_id = init_data["id"]
    upload_uri = init_data.get("uri") or f"{RUPLOAD_BASE_URL}/{container_id}"
    logger.info("Created Instagram container ID: %s", container_id)

    # Step 2: Upload raw video bytes to rupload.facebook.com
    logger.info("Uploading video bytes (%.2f MB) to Meta Resumable Upload endpoint...", file_size / (1024 * 1024))
    headers = {
        "Authorization": f"OAuth {config.ig_access_token}",
        "offset": "0",
        "file_size": str(file_size),
        "Content-Type": "application/octet-stream",
    }
    with open(video_path, "rb") as video_file:
        upload_resp = requests.post(upload_uri, headers=headers, data=video_file, timeout=300)

    if not upload_resp.ok:
        raise RuntimeError(f"Instagram binary upload failed ({upload_resp.status_code}): {upload_resp.text}")
    logger.info("Binary upload complete. Waiting for Instagram media processing...")

    # Step 3: Poll container status until FINISHED
    status_url = f"{GRAPH_BASE_URL}/{container_id}"
    max_polls = 36  # Up to 6 minutes (36 * 10s)
    for attempt in range(1, max_polls + 1):
        time.sleep(10)
        status_resp = requests.get(
            status_url,
            params={"fields": "status_code,status", "access_token": config.ig_access_token},
            timeout=30,
        )
        if not status_resp.ok:
            raise RuntimeError(f"Failed checking Instagram status ({status_resp.status_code}): {status_resp.text}")

        status_data = status_resp.json()
        status_code = status_data.get("status_code", "IN_PROGRESS")
        logger.info("Instagram processing status (%d/%d): %s", attempt, max_polls, status_code)

        if status_code == "FINISHED":
            break
        if status_code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram processing failed with status {status_code}: {status_data}")
    else:
        raise TimeoutError(f"Instagram container {container_id} did not finish processing within 6 minutes.")

    # Step 4: Publish the Reel
    logger.info("Publishing Reel to @psychologist.uday...")
    publish_url = f"{GRAPH_BASE_URL}/{config.ig_user_id}/media_publish"
    publish_resp = requests.post(
        publish_url,
        data={
            "creation_id": container_id,
            "access_token": config.ig_access_token,
        },
        timeout=60,
    )
    if not publish_resp.ok:
        raise RuntimeError(f"Instagram media_publish failed ({publish_resp.status_code}): {publish_resp.text}")

    media_id = publish_resp.json()["id"]
    logger.info("Successfully published to Instagram Reels (@psychologist.uday)! Media ID: %s", media_id)
    return media_id
