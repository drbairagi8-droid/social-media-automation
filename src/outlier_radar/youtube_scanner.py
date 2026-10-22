import datetime
import logging
import statistics
from typing import Dict, List
import yt_dlp

from src.config import Config
from src.outlier_radar.config import OutlierVideo

logger = logging.getLogger(__name__)

# Curated benchmark creators in clinical psychology, behavioral science, and neuroscience
CREATOR_SHORTS_URLS = [
    {"name": "Dr. Julie Smith", "url": "https://www.youtube.com/@DrJulie/shorts"},
    {"name": "Psych2Go", "url": "https://www.youtube.com/@Psych2go/shorts"},
    {"name": "HealthyGamerGG", "url": "https://www.youtube.com/@HealthyGamerGG/shorts"},
    {"name": "Therapy in a Nutshell", "url": "https://www.youtube.com/@TherapyinaNutshell/shorts"},
    {"name": "Sprouts Behavioral Science", "url": "https://www.youtube.com/@SproutsVideos/shorts"},
    {"name": "The School of Life", "url": "https://www.youtube.com/@TheSchoolofLife/shorts"},
    {"name": "Huberman Lab Clips", "url": "https://www.youtube.com/@HubermanLabClips/shorts"},
    {"name": "Practical Psychology", "url": "https://www.youtube.com/@practical_psychology/shorts"},
]


class YouTubeOutlierScanner:
    def __init__(self, config: Config):
        self.config = config
        self.ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "playlistend": 6,
            "skip_download": True,
        }

    def scan_recent_outliers(self, days_back: int = 3, max_candidates: int = 10) -> List[OutlierVideo]:
        """
        Scans top benchmark psychology channels' /shorts tabs, calculates
        each channel's baseline, and detects videos with a breakout outlier score.
        """
        logger.info("Scanning benchmark psychology channels for breakout outlier Shorts...")
        all_videos: List[OutlierVideo] = []

        with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
            for creator in CREATOR_SHORTS_URLS:
                creator_name = creator["name"]
                channel_url = creator["url"]
                try:
                    res = ydl.extract_info(channel_url, download=False)
                    entries = [e for e in res.get("entries", []) if e and e.get("view_count")]
                    if not entries:
                        continue

                    views_list = [e.get("view_count", 0) for e in entries if e.get("view_count")]
                    if not views_list:
                        continue

                    median_views = int(statistics.median(views_list)) or 25000

                    for e in entries:
                        view_count = e.get("view_count", 0)
                        multiplier = round(view_count / max(1000, median_views), 1)

                        v_id = e.get("id")
                        v_url = e.get("url") or f"https://youtube.com/shorts/{v_id}"
                        title = e.get("title", "Psychology Short")

                        all_videos.append(
                            OutlierVideo(
                                platform="YouTube Shorts",
                                video_id=v_id,
                                title=title,
                                url=v_url,
                                channel_title=creator_name,
                                channel_id=creator_name,
                                published_at=datetime.date.today().strftime("%Y-%m-%d"),
                                view_count=view_count,
                                channel_median_views=median_views,
                                outlier_multiplier=multiplier,
                                description=f"Breakout Short by {creator_name} ({multiplier}x channel median views).",
                            )
                        )
                except Exception as exc:
                    logger.warning("Could not scan %s: %s", creator_name, exc)

        # Sort all videos across all channels by outlier multiplier descending
        all_videos.sort(key=lambda x: (x.outlier_multiplier, x.view_count), reverse=True)

        # Select the top breakout outliers
        top_outliers = all_videos[:max_candidates]
        logger.info("Successfully detected %d top breakout psychology outliers across creators.", len(top_outliers))
        return top_outliers
