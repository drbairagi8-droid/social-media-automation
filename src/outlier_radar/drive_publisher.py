import datetime
import io
import logging
from typing import List
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from src.config import Config
from src.gdrive_manager import get_google_credentials
from src.outlier_radar.config import OutlierVideo

logger = logging.getLogger(__name__)


class DriveReportPublisher:
    def __init__(self, config: Config):
        self.config = config
        self.creds = get_google_credentials(config)
        self.drive = build("drive", "v3", credentials=self.creds)

    def publish_report(self, videos: List[OutlierVideo]) -> str:
        """
        Creates a formatted report file inside an 'Outlier Reports' folder in Google Drive.
        Returns the webViewLink of the created document.
        """
        folder_id = self._get_or_create_reports_folder()
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        title = f"Daily Psychology Outlier Radar — {today_str}"

        md_content = self._generate_markdown_content(videos, today_str)

        file_metadata = {
            "name": title,
            "parents": [folder_id],
            "mimeType": "application/vnd.google-apps.document",  # Creates as native Google Doc
        }
        media = MediaIoBaseUpload(
            io.BytesIO(md_content.encode("utf-8")),
            mimetype="text/plain",
            resumable=True,
        )

        try:
            created = (
                self.drive.files()
                .create(body=file_metadata, media_body=media, fields="id, webViewLink")
                .execute()
            )
            web_link = created.get("webViewLink", "")
            logger.info("Successfully published Google Doc report to Drive: %s", web_link)
            return web_link
        except Exception as exc:
            logger.error("Failed to create Google Doc in Drive: %s", exc)
            return ""

    def _get_or_create_reports_folder(self) -> str:
        """Finds or creates the 'Outlier Reports' folder in Google Drive."""
        query = "mimeType = 'application/vnd.google-apps.folder' and name = 'Outlier Reports' and trashed = false"
        try:
            res = self.drive.files().list(q=query, fields="files(id, name)").execute()
            files = res.get("files", [])
            if files:
                return files[0]["id"]

            # Create folder
            folder_meta = {
                "name": "Outlier Reports",
                "mimeType": "application/vnd.google-apps.folder",
            }
            created_folder = self.drive.files().create(body=folder_meta, fields="id").execute()
            logger.info("Created 'Outlier Reports' folder in Drive: %s", created_folder["id"])
            return created_folder["id"]
        except Exception as exc:
            logger.error("Error managing Outlier Reports folder: %s", exc)
            return self.config.gdrive_queue_folder_id

    def _generate_markdown_content(self, videos: List[OutlierVideo], today_str: str) -> str:
        lines = [
            f"# Daily Psychology Outlier Radar Briefing",
            f"**Date:** {today_str} | **Total Outliers Analyzed:** {len(videos)}",
            f"**Curated for:** Psychologist Uday (@psychologist.uday & TheKyunProject)",
            "",
            "---",
            "",
        ]

        for idx, v in enumerate(videos, 1):
            lines.extend(
                [
                    f"## #{idx}: {v.title}",
                    f"- **Platform:** {v.platform}",
                    f"- **Creator / Channel:** {v.channel_title}",
                    f"- **Published:** {v.published_at[:10]}",
                    f"- **Views:** {v.view_count:,} (Channel Baseline: {v.channel_median_views:,} -> **{v.outlier_multiplier}x Outlier**)",
                    f"- **Link:** {v.url}",
                    "",
                    f"### 1. The 3-Second Hook Deconstruction",
                    f"{v.hook_deconstruction}",
                    "",
                    f"### 2. The Core Psychological Mechanism",
                    f"{v.psychological_mechanism}",
                    "",
                    f"### 3. Why It Outperformed (Virality Trigger)",
                    f"{v.why_it_worked}",
                    "",
                    f"### 4. Adaptation Idea for Psychologist Uday",
                    f"{v.adaptation_angle}",
                    "",
                    "---",
                    "",
                ]
            )

        return "\n".join(lines)
