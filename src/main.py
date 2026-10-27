import argparse
import datetime
import json
import logging
import sys

from src.ai_metadata import generate_viral_metadata
from src.config import Config
from src.gdrive_manager import GDriveManager
from src.instagram_uploader import upload_to_instagram
from src.youtube_uploader import upload_to_youtube

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automated Daily Social Media Poster for TheKyunProject & @psyketch.studio"
    )
    parser.add_argument(
        "--profile",
        choices=["uday", "psyketch"],
        default="uday",
        help="Target channel profile to execute (default: uday).",
    )
    parser.add_argument(
        "--platform",
        choices=["all", "youtube", "instagram"],
        default="all",
        help="Target platform(s) to publish to (default: all).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Download video from Drive and generate AI captions/metadata without publishing.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass schedule gatekeeper and post immediately.",
    )
    return parser.parse_args()


def run() -> int:
    args = parse_args()
    config = Config.from_profile(profile=args.profile)
    config.validate(platform=args.platform, dry_run=args.dry_run)

    gdrive = GDriveManager(config)

    # Schedule Gatekeeper (obey schedule config if present)
    if not args.dry_run and not args.force:
        schedule = gdrive.get_schedule_config()
        if not schedule.get("all_posting_enabled", True):
            logger.info("[GATEKEEPER] All postings paused by configuration — exiting cleanly.")
            return 0

        utc_now = datetime.datetime.now(datetime.timezone.utc)
        ist_now = utc_now + datetime.timedelta(hours=5, minutes=30)
        hour = ist_now.hour

        slots = schedule.get("slots", {})
        active_slot_key = None
        if args.profile == "psyketch":
            # 2x Daily US Audience slots (US Eastern Time):
            # Slot 1: Morning US (08:00 - 11:00 AM EST) = 17:30 - 21:30 IST (5:30 PM - 9:30 PM IST)
            # Slot 2: Evening US (07:00 - 10:00 PM EST) = 04:30 - 08:30 IST (4:30 AM - 8:30 AM IST)
            if 17 <= hour <= 21:
                active_slot_key = "morning_us"
            elif 4 <= hour <= 8:
                active_slot_key = "evening_us"
        else:
            # Uday profile (exact existing slots: 7 AM, 1 PM, 7 PM IST)
            if 5 <= hour <= 10:
                active_slot_key = "morning"
            elif 11 <= hour <= 15:
                active_slot_key = "afternoon"
            elif 17 <= hour <= 22:
                active_slot_key = "evening"

        if active_slot_key and active_slot_key in slots:
            slot_info = slots[active_slot_key]
            if not slot_info.get("enabled", True):
                logger.info(
                    "[GATEKEEPER] %s slot (%s) is toggled OFF — skipping upload.",
                    active_slot_key.capitalize(),
                    slot_info.get("name", active_slot_key),
                )
                return 0

    video_item = gdrive.get_next_queued_video(platform=args.platform)

    if not video_item:
        logger.info("Queue is empty — nothing to post right now. Exiting cleanly.")
        return 0

    file_id = video_item["id"]
    file_name = video_item["name"]
    props = video_item.get("appProperties") or {}

    logger.info("Selected queued video: '%s' (Drive ID: %s)", file_name, file_id)
    local_video_path = gdrive.download_video(file_id=file_id, file_name=file_name)

    try:
        # 1. Generate viral metadata by letting Gemini watch the video
        metadata = generate_viral_metadata(
            video_path=local_video_path,
            original_filename=file_name,
            config=config,
        )

        print("\n" + "=" * 72)
        print("GENERATED VIRAL METADATA PREVIEW")
        print("=" * 72)
        print(json.dumps(metadata.model_dump(), indent=2, ensure_ascii=False))
        print("=" * 72 + "\n")

        if args.dry_run:
            logger.info("Dry-run complete! No posts were published and Drive queue was not modified.")
            return 0

        errors = []
        yt_done = props.get("youtube_posted") == "true"
        ig_done = props.get("instagram_posted") == "true"

        # 2. Post to YouTube Shorts (TheKyunProject) with anti-duplicate guard
        if args.platform in ("all", "youtube"):
            if yt_done:
                logger.info("[SAFEGUARD] Video '%s' already posted to YouTube (ID: %s) — skipping.", file_name, props.get("youtube_video_id"))
            else:
                try:
                    yt_video_id = upload_to_youtube(local_video_path, metadata, config)
                    props = gdrive.update_post_status(
                        file_id=file_id,
                        existing_props=props,
                        youtube_video_id=yt_video_id,
                    )
                    yt_done = True
                except Exception as exc:
                    logger.exception("YouTube upload failed: %s", exc)
                    errors.append(f"YouTube: {exc}")

        # 3. Post to Instagram Reels (@psychologist.uday) with anti-duplicate guard
        if args.platform in ("all", "instagram"):
            if ig_done:
                logger.info("[SAFEGUARD] Video '%s' already dispatched to Instagram — skipping.", file_name)
            elif not config.is_instagram_configured:
                logger.info(
                    "Instagram credentials not configured yet — skipping Instagram upload for now."
                )
            else:
                try:
                    ig_media_id = upload_to_instagram(
                        local_video_path, metadata, config, gdrive_file_id=file_id
                    )
                    props = gdrive.update_post_status(
                        file_id=file_id,
                        existing_props=props,
                        instagram_media_id=ig_media_id,
                    )
                    ig_done = True
                except Exception as exc:
                    logger.exception("Instagram upload failed: %s", exc)
                    errors.append(f"Instagram: {exc}")

        # 4. Immediately Archive the video once target platform(s) succeed (evict from Queue)
        should_archive = (
            (args.platform == "all"
             and yt_done
             and (ig_done or not config.is_instagram_configured))
            or (args.platform == "youtube" and yt_done)
            or (args.platform == "instagram" and ig_done)
        )
        if should_archive:
            logger.info("[SAFEGUARD] Both targets satisfied! Moving '%s' from Queue to Archive folder...", file_name)
            gdrive.archive_completed_video(file_id=file_id, file_name=file_name)

        if errors:
            logger.error("Completed with errors: %s", "; ".join(errors))
            return 1

        logger.info("All scheduled posts completed successfully!")
        return 0

    finally:
        if local_video_path.exists():
            try:
                local_video_path.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(run())
