import argparse
import json
import logging
import sys

from src.ai_metadata import generate_viral_metadata
from src.config import Config
from src.gdrive_manager import GDriveManager
from src.instagram_uploader import upload_to_instagram
from src.linkedin_uploader import upload_to_linkedin
from src.youtube_uploader import upload_to_youtube

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automated Daily Social Media Poster for TheKyunProject (YT), @psychologist.uday (IG) & Psychologist Uday (LI)"
    )
    parser.add_argument(
        "--platform",
        choices=["all", "youtube", "instagram", "linkedin"],
        default="all",
        help="Target platform(s) to publish to (default: all).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Download video from Drive and generate AI captions/metadata without publishing.",
    )
    return parser.parse_args()


def run() -> int:
    args = parse_args()
    config = Config()
    config.validate(platform=args.platform, dry_run=args.dry_run)

    gdrive = GDriveManager(config)
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
        li_done = props.get("linkedin_posted") == "true"

        # 2. Post to YouTube Shorts (TheKyunProject)
        if args.platform in ("all", "youtube") and not yt_done:
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

        # 3. Post to Instagram Reels (@psychologist.uday)
        if args.platform in ("all", "instagram") and not ig_done:
            if not config.is_instagram_configured:
                logger.info(
                    "Instagram credentials not configured yet — skipping Instagram upload for now."
                )
            else:
                try:
                    ig_media_id = upload_to_instagram(local_video_path, metadata, config)
                    props = gdrive.update_post_status(
                        file_id=file_id,
                        existing_props=props,
                        instagram_media_id=ig_media_id,
                    )
                    ig_done = True
                except Exception as exc:
                    logger.exception("Instagram upload failed: %s", exc)
                    errors.append(f"Instagram: {exc}")

        # 4. Post to LinkedIn Personal Profile (Psychologist Uday)
        if args.platform in ("all", "linkedin") and not li_done:
            if not config.is_linkedin_configured:
                logger.info(
                    "LinkedIn credentials not configured yet — skipping LinkedIn upload for now."
                )
            else:
                try:
                    li_post_urn = upload_to_linkedin(local_video_path, metadata, config)
                    props = gdrive.update_post_status(
                        file_id=file_id,
                        existing_props=props,
                        linkedin_post_urn=li_post_urn,
                    )
                    li_done = True
                except Exception as exc:
                    logger.exception("LinkedIn upload failed: %s", exc)
                    errors.append(f"LinkedIn: {exc}")

        # 5. Archive the video in Google Drive once all target platform(s) succeed
        should_archive = (
            (args.platform == "all"
             and yt_done
             and (ig_done or not config.is_instagram_configured)
             and (li_done or not config.is_linkedin_configured))
            or (args.platform == "youtube" and yt_done)
            or (args.platform == "instagram" and ig_done)
            or (args.platform == "linkedin" and li_done)
        )
        if should_archive:
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
