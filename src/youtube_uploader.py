import logging
import time
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from src.ai_metadata import ViralMetadata
from src.config import Config

logger = logging.getLogger(__name__)

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]
MAX_RETRIES = 5


def get_youtube_credentials(config: Config) -> Credentials:
    """Builds and refreshes YouTube OAuth2 credentials (supports separate YOUTUBE_REFRESH_TOKEN)."""
    creds = Credentials(
        token=None,
        refresh_token=config.youtube_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.google_client_id,
        client_secret=config.google_client_secret,
        scopes=YOUTUBE_SCOPES,
    )
    creds.refresh(Request())
    return creds


def upload_to_youtube(video_path: Path, metadata: ViralMetadata, config: Config) -> str:
    """
    Uploads a vertical video (YouTube Short) to TheKyunProject via YouTube Data API v3.
    Returns the published YouTube video ID.
    """
    creds = get_youtube_credentials(config)
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": metadata.youtube_title[:100],
            "description": metadata.youtube_description[:4900],
            "tags": metadata.youtube_tags[:20],
            "categoryId": config.youtube_category_id,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": config.youtube_privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        chunksize=8 * 1024 * 1024,
        resumable=True,
    )

    insert_request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    logger.info("Starting YouTube upload to TheKyunProject: '%s'", metadata.youtube_title)
    response = None
    retry = 0

    while response is None:
        try:
            status, response = insert_request.next_chunk()
            if status:
                logger.info("YouTube upload progress: %d%%", int(status.progress() * 100))
        except HttpError as exc:
            if exc.resp.status in RETRIABLE_STATUS_CODES and retry < MAX_RETRIES:
                retry += 1
                sleep_seconds = 2**retry
                logger.warning(
                    "Retriable YouTube HTTP error %d; retrying in %ds (%d/%d)...",
                    exc.resp.status,
                    sleep_seconds,
                    retry,
                    MAX_RETRIES,
                )
                time.sleep(sleep_seconds)
            else:
                raise

    video_id = response["id"]
    logger.info("Successfully published to YouTube Shorts! URL: https://youtube.com/shorts/%s", video_id)
    return video_id
