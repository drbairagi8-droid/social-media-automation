import argparse
import logging
import sys

from src.config import Config
from src.outlier_radar.drive_publisher import DriveReportPublisher
from src.outlier_radar.gemini_deconstructor import deconstruct_outliers
from src.outlier_radar.script_writer import generate_and_refine_scripts
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
    logger.info("Initializing Daily Psychology Outlier Radar & Script Engine...")

    # Step 1: Scan for recent breakout outliers
    scanner = YouTubeOutlierScanner(config)
    outliers = scanner.scan_recent_outliers(days_back=days_back, max_candidates=max_videos)

    if not outliers:
        logger.info("No breakout outliers found in this run.")
        if not skip_telegram:
            send_telegram_radar_report([], scripts=[])
        return 0

    # Step 2: Gemini deconstructs the raw 10 outliers
    logger.info("Deconstructing %d breakout outlier videos with Gemini...", len(outliers))
    analyzed_outliers = deconstruct_outliers(outliers, config)

    # Step 3: Two-Pass Script Engine (Select top 5 -> Draft -> Senior Editor Review & Refine)
    logger.info("Starting Two-Pass Hindi Scriptwriting Engine (Indian Relatability + Share Trigger Filters)...")
    refined_scripts = []
    try:
        refined_scripts = generate_and_refine_scripts(analyzed_outliers, config)
        logger.info("Successfully generated and refined %d daily Hindi production scripts!", len(refined_scripts))
    except Exception as exc:
        logger.error("Error generating refined scripts: %s", exc)

    # Step 4: Publish full report & scripts to Google Drive
    doc_url = ""
    try:
        publisher = DriveReportPublisher(config)
        doc_url = publisher.publish_report(analyzed_outliers, scripts=refined_scripts)
    except Exception as exc:
        logger.error("Could not upload report to Google Drive: %s", exc)

    # Step 5: Dispatch executive briefing & script links to Telegram
    if not skip_telegram:
        logger.info("Sending executive briefing & script previews to Telegram...")
        send_telegram_radar_report(analyzed_outliers, scripts=refined_scripts, drive_doc_url=doc_url)

    logger.info("Daily Outlier Radar & Script Generation completed successfully!")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Daily Psychology Outlier Radar & Script Engine for @psychologist.uday")
    parser.add_argument("--days", type=int, default=3, help="Lookback window in days (default: 3)")
    parser.add_argument("--limit", type=int, default=10, help="Maximum outliers to analyze (default: 10)")
    parser.add_argument("--skip-telegram", action="store_true", help="Do not send Telegram alert")
    args = parser.parse_args()

    sys.exit(run_outlier_radar(days_back=args.days, max_videos=args.limit, skip_telegram=args.skip_telegram))


if __name__ == "__main__":
    main()
