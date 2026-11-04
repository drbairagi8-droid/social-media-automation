import io
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
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

    def get_next_queued_video(
        self,
        platform: str = "all",
        active_slot: Optional[str] = None,
        video_slots: Optional[Dict[str, str]] = None,
        force_file_id: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Fetches the next unposted video from the Google Drive Queue folder.
        If `force_file_id` is set, selects that exact video immediately.
        If `active_slot` ('morning', 'afternoon', 'evening') is provided:
          1. Prioritizes a video explicitly assigned to `active_slot` in `video_slots` (or `appProperties.target_slot`).
          2. Falls back to the oldest unassigned ('auto') video in the queue.
          3. Never pulls a video that is locked to a different time slot.
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

        eligible_files = []
        for file_item in files:
            props = file_item.get("appProperties") or {}
            yt_done = props.get("youtube_posted") == "true"
            ig_done = props.get("instagram_posted") == "true"

            if platform == "all":
                need_yt = not yt_done
                need_ig = self.config.is_instagram_configured and not ig_done
                if need_yt or need_ig:
                    eligible_files.append(file_item)
            elif platform == "youtube" and not yt_done:
                eligible_files.append(file_item)
            elif platform == "instagram" and not ig_done:
                eligible_files.append(file_item)

        if not eligible_files:
            logger.info("All videos in the Queue folder have already been posted for platform=%s.", platform)
            return None

        if force_file_id:
            for item in eligible_files:
                if item["id"] == force_file_id:
                    logger.info("[SLOT PICKER] Selected explicitly requested video (force_file_id): '%s'", item["name"])
                    return item

        if not active_slot or active_slot not in ("morning", "afternoon", "evening"):
            return eligible_files[0]

        slot_map = video_slots or {}

        def _get_assigned_slot(item: Dict) -> Optional[str]:
            f_id = item["id"]
            props = item.get("appProperties") or {}
            raw_slot = (slot_map.get(f_id) or props.get("target_slot") or "").strip().lower()
            if raw_slot == "night":
                raw_slot = "evening"
            if raw_slot in ("morning", "afternoon", "evening"):
                return raw_slot
            return None

        # Priority 1: Video explicitly locked to the current active_slot
        for item in eligible_files:
            if _get_assigned_slot(item) == active_slot:
                logger.info(
                    "[SLOT PICKER] Selected video explicitly assigned to '%s' slot: '%s'",
                    active_slot,
                    item["name"],
                )
                return item

        # Priority 2: Unassigned ('auto') video (never steal a video locked to another slot)
        for item in eligible_files:
            if _get_assigned_slot(item) is None:
                logger.info(
                    "[SLOT PICKER] No video locked to '%s'; selected unassigned auto video: '%s'",
                    active_slot,
                    item["name"],
                )
                return item

        logger.info(
            "[SLOT PICKER] All %d queued video(s) are locked to other time slots — skipping '%s' run.",
            len(eligible_files),
            active_slot,
        )
        return None

    def count_remaining_videos(self) -> int:
        """Returns the number of video files remaining in the Google Drive Queue folder."""
        query = (
            f"'{self.config.gdrive_queue_folder_id}' in parents "
            "and mimeType contains 'video/' "
            "and trashed = false"
        )
        try:
            res = self.service.files().list(q=query, pageSize=50, fields="files(id)").execute()
            return len(res.get("files", []))
        except Exception as exc:
            logger.warning("Could not count remaining videos in Queue (%s).", exc)
            return -1

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
    ) -> Dict[str, str]:
        """Records platform publish state inside the Drive file's `appProperties`."""
        props = dict(existing_props or {})
        if youtube_video_id:
            props["youtube_posted"] = "true"
            props["youtube_video_id"] = str(youtube_video_id)
        if instagram_media_id:
            props["instagram_posted"] = "true"
            props["instagram_media_id"] = str(instagram_media_id)

        self.service.files().update(
            fileId=file_id,
            body={"appProperties": props},
            fields="id, appProperties",
        ).execute()
        return props

    def get_schedule_config(self) -> Dict[str, Any]:
        """Fetches and parses schedule_config.json from Google Drive."""
        query = (
            f"name = 'schedule_config.json' "
            f"and '{self.config.gdrive_queue_folder_id}' in parents "
            "and trashed = false"
        )
        try:
            res = self.service.files().list(q=query, fields="files(id, name)").execute()
            files = res.get("files", [])
            if not files:
                return {"all_posting_enabled": True, "slots": {}}
            f_id = files[0]["id"]
            content = self.service.files().get_media(fileId=f_id).execute().decode("utf-8")
            return json.loads(content)
        except Exception as exc:
            logger.warning("Could not read schedule_config.json from Drive (%s); defaulting to enabled.", exc)
            return {"all_posting_enabled": True, "slots": {}}

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
