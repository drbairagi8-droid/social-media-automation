import io
import logging
from pathlib import Path
from typing import Dict, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from src.config import Config, TMP_DIR

logger = logging.getLogger(__name__)

DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive",
]


def get_google_credentials(config: Config) -> Credentials:
    """Builds and refreshes Google Drive OAuth2 credentials from environment variables."""
    creds = Credentials(
        token=None,
        refresh_token=config.google_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=config.google_client_id,
        client_secret=config.google_client_secret,
        scopes=DRIVE_SCOPES,
    )
    creds.refresh(Request())
    return creds


class GDriveManager:
    def __init__(self, config: Config):
        self.config = config
        self.creds = get_google_credentials(config)
        self.service = build("drive", "v3", credentials=self.creds)

    def get_next_queued_video(self, platform: str = "all") -> Optional[Dict]:
        """
        Fetches the oldest unposted video from the Google Drive Queue folder.
        Uses Drive `appProperties` to avoid double-posting if one platform already succeeded.
        """
        query = (
            f"'{self.config.gdrive_queue_folder_id}' in parents "
            "and mimeType contains 'video/' "
            "and trashed = false"
        )
        response = (
            self.service.files()
            .list(
                q=query,
                orderBy="createdTime asc, name asc",
                pageSize=20,
                fields="files(id, name, mimeType, size, createdTime, appProperties)",
            )
            .execute()
        )
        files = response.get("files", [])
        if not files:
            logger.info("No video files found in Google Drive Queue folder (%s).", self.config.gdrive_queue_folder_id)
            return None

        for file_item in files:
            props = file_item.get("appProperties") or {}
            yt_done = props.get("youtube_posted") == "true"
            ig_done = props.get("instagram_posted") == "true"
            li_done = props.get("linkedin_posted") == "true"

            if platform == "all":
                # Check if any configured platform is still pending
                need_yt = not yt_done
                need_ig = self.config.is_instagram_configured and not ig_done
                need_li = self.config.is_linkedin_configured and not li_done
                if need_yt or need_ig or need_li:
                    return file_item
            elif platform == "youtube" and not yt_done:
                return file_item
            elif platform == "instagram" and not ig_done:
                return file_item
            elif platform == "linkedin" and not li_done:
                return file_item

        logger.info("All videos in the Queue folder have already been posted for platform=%s.", platform)
        return None

    def download_video(self, file_id: str, file_name: str) -> Path:
        """Downloads a video from Google Drive to the local tmp/ directory."""
        safe_ext = Path(file_name).suffix or ".mp4"
        local_path = TMP_DIR / f"{file_id}{safe_ext}"

        logger.info("Downloading '%s' (ID: %s) from Google Drive...", file_name, file_id)
        request = self.service.files().get_media(fileId=file_id)

        with io.FileIO(local_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request, chunksize=8 * 1024 * 1024)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if status:
                    logger.info("Download progress: %d%%", int(status.progress() * 100))

        logger.info("Downloaded video to %s (%.2f MB)", local_path, local_path.stat().st_size / (1024 * 1024))
        return local_path

    def update_post_status(
        self,
        file_id: str,
        existing_props: Optional[Dict[str, str]] = None,
        youtube_video_id: Optional[str] = None,
        instagram_media_id: Optional[str] = None,
        linkedin_post_urn: Optional[str] = None,
    ) -> Dict[str, str]:
        """Records platform publish state inside the Drive file's `appProperties`."""
        props = dict(existing_props or {})
        if youtube_video_id:
            props["youtube_posted"] = "true"
            props["youtube_video_id"] = str(youtube_video_id)
        if instagram_media_id:
            props["instagram_posted"] = "true"
            props["instagram_media_id"] = str(instagram_media_id)
        if linkedin_post_urn:
            props["linkedin_posted"] = "true"
            props["linkedin_post_urn"] = str(linkedin_post_urn)

        self.service.files().update(
            fileId=file_id,
            body={"appProperties": props},
            fields="id, appProperties",
        ).execute()
        return props

    def archive_completed_video(self, file_id: str, file_name: str) -> None:
        """Moves a fully posted video from the Queue folder to the Archive ('Posted') folder."""
        if not self.config.gdrive_archive_folder_id:
            logger.info(
                "No GDRIVE_ARCHIVE_FOLDER_ID configured; keeping '%s' in Queue with posted appProperties.",
                file_name,
            )
            return

        logger.info(
            "Moving '%s' (ID: %s) from Queue to Archive folder (%s)...",
            file_name,
            file_id,
            self.config.gdrive_archive_folder_id,
        )
        file_meta = self.service.files().get(fileId=file_id, fields="parents").execute()
        previous_parents = ",".join(file_meta.get("parents", []))

        self.service.files().update(
            fileId=file_id,
            addParents=self.config.gdrive_archive_folder_id,
            removeParents=previous_parents,
            fields="id, parents",
        ).execute()
        logger.info("Successfully archived '%s'.", file_name)
