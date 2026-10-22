import datetime
import io
import logging
from typing import List, Optional
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from src.config import Config
from src.gdrive_manager import get_google_credentials
from src.outlier_radar.config import OutlierVideo
from src.outlier_radar.script_writer import RefinedScript

logger = logging.getLogger(__name__)


class DriveReportPublisher:
    def __init__(self, config: Config):
        self.config = config
        self.creds = get_google_credentials(config)
        self.drive = build("drive", "v3", credentials=self.creds)

    def publish_report(self, videos: List[OutlierVideo], scripts: Optional[List[RefinedScript]] = None) -> str:
        """
        Creates a formatted report file inside an 'Outlier Reports' folder in Google Drive.
        Contains both the 5 Production Scripts and the 10 Researched Outliers.
        Returns the webViewLink of the created document.
        """
        folder_id = self._get_or_create_reports_folder()
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        title = f"Daily Psychology Outlier Scripts & Intelligence — {today_str}"

        md_content = self._generate_markdown_content(videos, scripts or [], today_str)

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
            logger.info("Successfully published Google Doc report with scripts to Drive: %s", web_link)
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

    def _generate_markdown_content(
        self, videos: List[OutlierVideo], scripts: List[RefinedScript], today_str: str
    ) -> str:
        lines = [
            f"# Daily Psychology Outlier Scripts & Intelligence Briefing",
            f"**Date:** {today_str} | **Curated for:** Psychologist Uday (@psychologist.uday & TheKyunProject)",
            f"**Production Ready Scripts:** {len(scripts)} | **Researched Outliers:** {len(videos)}",
            "",
            "==================================================================",
            "## SECTION 1: TODAY'S 5 PRODUCTION-READY HINDI SCRIPTS",
            "*(Filtered for Mass Indian Relatability + Viral Share Triggers)*",
            "==================================================================",
            "",
        ]

        if scripts:
            for idx, s in enumerate(scripts, 1):
                lines.extend(
                    [
                        f"### 🎬 SCRIPT #{idx}: {s.topic_name.upper()}",
                        f"- **Format:** {s.format_type}",
                        f"- **Source Outlier:** {s.source_outlier_title}",
                        f"- **🇮🇳 Indian Relatability:** {s.indian_relatability_angle}",
                        f"- **🚀 Why Someone Will Share This:** {s.share_catalyst}",
                        "",
                        f"#### 1. Topic Summary & Psychological Mechanism ('Kyun?')",
                        f"{s.summary_and_mechanism}",
                        "",
                        f"#### 2. Animation & Storyboard Vision (Remotion Rig)",
                        f"{s.animation_vision}",
                        "",
                        f"#### 3. Senior Director Review & Polish Note",
                        f"_{s.editorial_critique}_",
                        "",
                        f"#### 4. Final Production Dialogue Script (Hindi/Hinglish)",
                        f"{s.final_refined_script}",
                        "",
                        "------------------------------------------------------------------",
                        "",
                    ]
                )
        else:
            lines.append("*(No scripts generated in this run)*\n")

        lines.extend(
            [
                "",
                "==================================================================",
                "## SECTION 2: RAW RESEACHED BREAKOUT OUTLIERS (LAST 72H)",
                "==================================================================",
                "",
            ]
        )

        for idx, v in enumerate(videos, 1):
            lines.extend(
                [
                    f"### #{idx}: {v.title}",
                    f"- **Platform:** {v.platform} | **Creator:** {v.channel_title}",
                    f"- **Views:** {v.view_count:,} (Channel Baseline: {v.channel_median_views:,} -> **{v.outlier_multiplier}x Outlier**)",
                    f"- **Link:** {v.url}",
                    f"- **The 3s Hook:** {v.hook_deconstruction}",
                    f"- **Mechanism:** {v.psychological_mechanism}",
                    f"- **Virality Factor:** {v.why_it_worked}",
                    "",
                ]
            )

        return "\n".join(lines)
