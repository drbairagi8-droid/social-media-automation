import logging
import time
from pathlib import Path
import requests
import urllib.parse

from src.ai_metadata import ViralMetadata
from src.config import Config

logger = logging.getLogger(__name__)

LINKEDIN_REST_BASE = "https://api.linkedin.com/rest"
LINKEDIN_API_VERSION = "202401"


def upload_to_linkedin(video_path: Path, metadata: ViralMetadata, config: Config) -> str:
    """
    Uploads a vertical video to LinkedIn via the official Versioned REST API
    and publishes a high-engagement psychology post on Psychologist Uday's profile.
    Returns the published LinkedIn Post URN.
    """
    file_size = video_path.stat().st_size
    headers_base = {
        "Authorization": f"Bearer {config.linkedin_access_token}",
        "LinkedIn-Version": LINKEDIN_API_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
    }

    # Step 1: Initialize Video Upload
    logger.info("Initializing LinkedIn video upload for %s (%.2f MB)...", config.linkedin_person_urn, file_size / (1024 * 1024))
    init_url = f"{LINKEDIN_REST_BASE}/videos?action=initializeUpload"
    init_payload = {
        "initializeUploadRequest": {
            "owner": config.linkedin_person_urn,
            "fileSizeBytes": file_size,
            "uploadCaptions": False,
            "uploadThumbnail": False,
        }
    }

    resp = requests.post(init_url, json=init_payload, headers=headers_base, timeout=60)
    if not resp.ok:
        raise RuntimeError(f"LinkedIn initializeUpload failed ({resp.status_code}): {resp.text}")

    init_data = resp.json().get("value", {})
    upload_instructions = init_data.get("uploadInstructions", [])
    if not upload_instructions:
        raise RuntimeError(f"No uploadInstructions received from LinkedIn: {resp.text}")

    upload_url = upload_instructions[0]["uploadUrl"]
    video_urn = init_data["video"]
    logger.info("LinkedIn upload URL created. Video URN: %s", video_urn)

    # Step 2: Upload raw video bytes to uploadUrl
    logger.info("Uploading video bytes to LinkedIn CDN...")
    with open(video_path, "rb") as fh:
        put_resp = requests.put(
            upload_url,
            headers={"Content-Type": "application/octet-stream"},
            data=fh,
            timeout=300,
        )

    if not put_resp.ok:
        raise RuntimeError(f"LinkedIn binary upload failed ({put_resp.status_code}): {put_resp.text}")

    logger.info("Binary video upload to LinkedIn completed successfully. Waiting for video ingestion...")

    # Step 3: Poll video status until AVAILABLE
    encoded_video_urn = urllib.parse.quote(video_urn, safe="")
    poll_url = f"{LINKEDIN_REST_BASE}/videos/{encoded_video_urn}"
    max_polls = 30  # Up to 5 minutes (30 * 10s)
    for attempt in range(1, max_polls + 1):
        time.sleep(10)
        status_resp = requests.get(poll_url, headers=headers_base, timeout=30)
        if not status_resp.ok:
            logger.warning("LinkedIn video check status warning (%d): %s", status_resp.status_code, status_resp.text)
            continue

        status_data = status_resp.json()
        video_status = status_data.get("status", "PROCESSING")
        logger.info("LinkedIn video processing status (%d/%d): %s", attempt, max_polls, video_status)

        if video_status == "AVAILABLE":
            break
        if video_status in ("FAILED", "EXPIRED"):
            raise RuntimeError(f"LinkedIn video processing failed: {status_data}")
    else:
        logger.warning("LinkedIn video status check timed out, proceeding to publish post attempt...")

    # Step 4: Publish the Post
    logger.info("Publishing post with attached video to LinkedIn...")
    posts_url = f"{LINKEDIN_REST_BASE}/posts"
    post_payload = {
        "author": config.linkedin_person_urn,
        "commentary": metadata.linkedin_post,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "content": {
            "media": {
                "title": metadata.youtube_title,
                "id": video_urn,
            }
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }

    create_resp = requests.post(posts_url, json=post_payload, headers=headers_base, timeout=60)
    if create_resp.status_code not in (201, 200):
        raise RuntimeError(f"LinkedIn post creation failed ({create_resp.status_code}): {create_resp.text}")

    post_urn = create_resp.headers.get("x-restli-id") or create_resp.json().get("id", "linkedin_post_published")
    logger.info("Successfully published video post to LinkedIn! Post URN: %s", post_urn)
    return post_urn
