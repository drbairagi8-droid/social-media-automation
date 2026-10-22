import argparse
import logging
import sys

from src.config import Config
from src.outlier_radar.drive_publisher import DriveReportPublisher
from src.outlier_radar.gemini_deconstructor import deconstruct_outliers
from src.outlier_radar.telegram_sender import send_telegram_radar_report
from src.outlier_radar.youtube_scanner import YouTubeOutlierScanner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_outlier_radar(days_back: int = 3, max_videos: int = 10, skip_telegram: bool = False) -> int:
    config = Config()
    logger.info("Initializing Daily Psychology Outlier Radar...")

    # Step 1: Scan for recent outliers
    scanner = YouTubeOutlierScanner(config)
    outliers = scanner.scan_recent_outliers(days_back=days_back, max_candidates=max_videos)

    if not outliers:
        logger.info("No breakout outliers (>15k views, recent 72h) found in this run.")
        if not skip_telegram:
            send_telegram_radar_report([])
        return 0

    logger.info("Deconstructing %d breakout outlier videos with Gemini 3.8 Flash...", len(outliers))

    # Step 2: Gemini deep deconstruction
    analyzed_outliers = deconstruct_outliers(outliers, config)

    # Step 3: Publish full report to Google Drive
    doc_url = ""
    try:
        publisher = DriveReportPublisher(config)
        doc_url = publisher.publish_report(analyzed_outliers)
    except Exception as exc:
        logger.error("Could not upload report to Google Drive: %s", exc)

    # Step 4: Dispatch executive briefing to Telegram
    if not skip_telegram:
        logger.info("Sending executive briefing to Telegram...")
        send_telegram_radar_report(analyzed_outliers, drive_doc_url=doc_url)

    logger.info("Daily Outlier Radar execution completed successfully!")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Daily Psychology Outlier Radar for @psychologist.uday")
    parser.add_argument("--days", type=int, default=3, help="Lookback window in days (default: 3)")
    parser.add_argument("--limit", type=int, default=10, help="Maximum outliers to analyze (default: 10)")
    parser.add_argument("--skip-telegram", action="store_true", help="Do not send Telegram alert")
    args = parser.parse_args()

    sys.exit(run_outlier_radar(days_back=args.days, max_videos=args.limit, skip_telegram=args.skip_telegram))


if __name__ == "__main__":
    main()
