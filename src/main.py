import argparse
import datetime
import json
import logging
import os
import sys

from src.ai_metadata import generate_viral_metadata
from src.config import Config
from src.gdrive_manager import GDriveManager
from src.instagram_uploader import upload_to_instagram
from src.telegram_notifier import notify_empty_queue, notify_fatal_error, notify_post_result
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
    parser.add_argument(
        "--slot",
        choices=["morning", "afternoon", "evening", "morning_us", "evening_us"],
        default="",
        help="Explicitly target a specific posting slot (overrides clock/cron inference).",
    )
    return parser.parse_args()


def run() -> int:
    args = parse_args()
    config = Config.from_profile(profile=args.profile)
    config.validate(platform=args.platform, dry_run=args.dry_run)

    gdrive = GDriveManager(config)
    schedule = gdrive.get_schedule_config()
    active_slot_key = None

    utc_now = datetime.datetime.now(datetime.timezone.utc)
    ist_now = utc_now + datetime.timedelta(hours=5, minutes=30)
    hour = ist_now.hour
    today_ist = ist_now.strftime("%Y-%m-%d")

    posted_by_date = schedule.get("posted_slots_by_date") or {}
    posted_today = posted_by_date.get(today_ist) if isinstance(posted_by_date, dict) else []
    if not isinstance(posted_today, list):
        posted_today = []

    cron_expr = os.getenv("GITHUB_EVENT_SCHEDULE", "").strip()
    CRON_TO_SLOT = {
        "30 0 * * *": "morning",
        "25 0 * * *": "morning",
        "45 0 * * *": "morning",
        "30 1 * * *": "morning",
        "0 3 * * *": "morning",
        "30 6 * * *": "afternoon",
        "25 6 * * *": "afternoon",
        "50 6 * * *": "afternoon",
        "0 8 * * *": "afternoon",
        "0 12 * * *": "evening",
        "55 11 * * *": "evening",
        "20 12 * * *": "evening",
        "0 13 * * *": "evening",
        "30 14 * * *": "evening",
    }

    PSYKETCH_CRON_TO_SLOT = {
        "0 13 * * *": "morning_us",
        "30 14 * * *": "morning_us",
        "0 0 * * *": "evening_us",
        "30 1 * * *": "evening_us",
    }

    if args.profile == "psyketch":
        # 2x Daily US Audience slots (US Eastern Time):
        # Slot 1: Morning US (08:00 - 11:00 AM EST) = 17:30 - 21:30 IST (5:30 PM - 9:30 PM IST)
        # Slot 2: Evening US (07:00 - 10:00 PM EST) = 04:30 - 08:30 IST (4:30 AM - 8:30 AM IST)
        if args.slot:
            active_slot_key = args.slot
        elif cron_expr in PSYKETCH_CRON_TO_SLOT:
            active_slot_key = PSYKETCH_CRON_TO_SLOT[cron_expr]
        elif 17 <= hour <= 22:
            active_slot_key = "morning_us"
        else:
            active_slot_key = "evening_us"
    else:
        # Uday profile (slots: 6:00 AM, 12:00 PM, 5:30 PM IST)
        if args.slot:
            active_slot_key = args.slot
        elif cron_expr in CRON_TO_SLOT:
            active_slot_key = CRON_TO_SLOT[cron_expr]
            logger.info("[SLOT DETECTOR] Matched GitHub cron '%s' -> '%s' slot.", cron_expr, active_slot_key)
        elif 5 <= hour <= 10:
            active_slot_key = "morning"
        elif 11 <= hour <= 15:
            active_slot_key = "afternoon"
        elif 16 <= hour <= 21:
            active_slot_key = "evening"
        else:
            # Late night (10:00 PM - 04:59 AM IST): only map to evening for manual --force/--dry-run
            active_slot_key = "evening"

    # Schedule Gatekeeper (obey schedule config, catch-up logic, and late-night blackout if not --force)
    if not args.dry_run and not args.force:
        if not schedule.get("all_posting_enabled", True):
            logger.info("[GATEKEEPER] All postings paused by configuration — exiting cleanly.")
            return 0

        if args.profile == "uday":
            # 1. Hard Late-Night Blackout Guard (10:00 PM - 04:59 AM IST)
            if hour >= 22 or hour < 5:
                logger.info(
                    "[GATEKEEPER] Late-night blackout window (%02d:%02d IST, 22:00-04:59 IST) — blocking delayed night post.",
                    ist_now.hour,
                    ist_now.minute,
                )
                return 0

            slots = schedule.get("slots", {})
            slot_enabled = lambda k: slots.get(k, {}).get("enabled", True)

            # 2. Smart Catch-Up Logic: if Afternoon cron wakes up (or Morning cron was delayed into 11:00-15:59 IST)
            # and Afternoon is OFF (or already posted), check if Morning was enabled and missed today!
            if active_slot_key == "afternoon" and (not slot_enabled("afternoon") or "afternoon" in posted_today):
                if slot_enabled("morning") and "morning" not in posted_today and 11 <= hour <= 15:
                    logger.info(
                        "[SMART CATCH-UP] Morning (06:00 AM IST) was missed earlier today and Afternoon is OFF — "
                        "auto-promoting this run to fulfill the missed 'morning' slot!"
                    )
                    active_slot_key = "morning"

            # 3. Stale Cron Window Guard: never let a Morning/Afternoon cron delayed past its window post out-of-window
            if active_slot_key == "morning" and hour >= 16:
                logger.info(
                    "[GATEKEEPER] Morning cron was delayed until %02d:%02d IST (>=16:00 IST) — skipping stale run so it doesn't collide with Evening.",
                    ist_now.hour,
                    ist_now.minute,
                )
                return 0
            if active_slot_key == "afternoon" and hour >= 16:
                if slot_enabled("afternoon") and "afternoon" not in posted_today:
                    logger.info(
                        "[GATEKEEPER] Afternoon cron was delayed until %02d:%02d IST (>=16:00 IST) — skipping stale run so it doesn't collide with Evening.",
                        ist_now.hour,
                        ist_now.minute,
                    )
                    return 0
            if active_slot_key == "evening" and hour < 16:
                logger.info(
                    "[GATEKEEPER] Evening cron was delayed into next day (%02d:%02d IST < 16:00 IST) — skipping stale run.",
                    ist_now.hour,
                    ist_now.minute,
                )
                return 0

            # 4. Check if target slot is enabled
            if active_slot_key and active_slot_key in slots:
                slot_info = slots[active_slot_key]
                if not slot_info.get("enabled", True):
                    logger.info(
                        "[GATEKEEPER] %s slot (%s) is toggled OFF — skipping upload.",
                        active_slot_key.capitalize(),
                        slot_info.get("name", active_slot_key),
                    )
                    return 0

            # 5. Anti-Double-Post Guard: never publish twice for the same slot on the same IST day
            if active_slot_key and active_slot_key in posted_today:
                logger.info(
                    "[SAFEGUARD] Slot '%s' has already published a video today (%s) — skipping duplicate run.",
                    active_slot_key,
                    today_ist,
                )
                return 0
        else:
            slots = schedule.get("slots", {})
            if active_slot_key and active_slot_key in slots:
                slot_info = slots[active_slot_key]
                if not slot_info.get("enabled", True):
                    logger.info(
                        "[GATEKEEPER] %s slot (%s) is toggled OFF — skipping upload.",
                        active_slot_key.capitalize(),
                        slot_info.get("name", active_slot_key),
                    )
                    return 0
            if active_slot_key and active_slot_key in posted_today:
                logger.info(
                    "[SAFEGUARD] Slot '%s' has already published a video today (%s) — skipping duplicate run.",
                    active_slot_key,
                    today_ist,
                )
                return 0

    video_item = gdrive.get_next_queued_video(
        platform=args.platform,
        active_slot=active_slot_key,
        video_slots=schedule.get("video_slots", {}),
        force_file_id=schedule.get("force_file_id"),
    )

    if not video_item:
        logger.info("Queue is empty — nothing to post right now. Exiting cleanly.")
        if not args.dry_run:
            notify_empty_queue(config=config, slot_key=active_slot_key)
        return 0

    file_id = video_item["id"]
    file_name = video_item["name"]
    props = video_item.get("appProperties") or {}

    logger.info("Selected queued video: '%s' (Drive ID: %s)", file_name, file_id)
    local_video_path = gdrive.download_video(file_id=file_id, file_name=file_name)

    try:
        # 1. Generate viral metadata by letting Gemini watch the video
        try:
            metadata = generate_viral_metadata(
                video_path=local_video_path,
                original_filename=file_name,
                config=config,
            )
        except Exception as exc:
            if not args.dry_run:
                notify_fatal_error(config=config, file_name=file_name, slot_key=active_slot_key, error_msg=str(exc))
            raise

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
        yt_video_id = props.get("youtube_video_id")

        # 2. Post to YouTube Shorts (TheKyunProject) with anti-duplicate guard
        if args.platform in ("all", "youtube"):
            if yt_done:
                logger.info("[SAFEGUARD] Video '%s' already posted to YouTube (ID: %s) — skipping.", file_name, yt_video_id)
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
            gdrive.record_slot_posted(date_str=today_ist, slot_key=active_slot_key, file_id=file_id)
        elif yt_done or ig_done:
            gdrive.record_slot_posted(date_str=today_ist, slot_key=active_slot_key)

        remaining_count = gdrive.count_remaining_videos()
        notify_post_result(
            config=config,
            file_name=file_name,
            youtube_title=metadata.youtube_title,
            slot_key=active_slot_key,
            yt_video_id=yt_video_id,
            ig_done=ig_done,
            remaining_count=remaining_count,
            errors=errors,
        )

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
