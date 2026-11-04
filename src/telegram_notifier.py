import logging
from typing import List, Optional
import requests

from src.config import Config

logger = logging.getLogger(__name__)


def _escape_md(text: str) -> str:
    """Escapes characters that could break legacy Telegram Markdown parsing."""
    return (
        str(text)
        .replace("_", "\\_")
        .replace("*", "\\*")
        .replace("`", "'")
        .replace("[", "(")
        .replace("]", ")")
    )


def _send_telegram(config: Config, text: str, include_buttons: bool = True) -> None:
    if not config.telegram_bot_token or not config.telegram_chat_id:
        logger.info("Telegram credentials not configured; skipping Telegram alert.")
        return

    url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
    payload: dict = {
        "chat_id": config.telegram_chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    if include_buttons and config.profile == "uday":
        payload["reply_markup"] = {
            "inline_keyboard": [
                [
                    {"text": "🎛️ Control Center", "callback_data": "refresh"},
                    {"text": "🎯 Video Slots", "callback_data": "menu_slots"},
                ]
            ]
        }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        if not resp.ok:
            logger.warning("Telegram notification returned %d: %s", resp.status_code, resp.text[:200])
        else:
            logger.info("Sent live status alert to Telegram (@UdayPsychRadarBot).")
    except Exception as exc:
        logger.warning("Failed to send Telegram alert (%s).", exc)


def _format_profile_label(config: Config) -> str:
    if config.profile == "psyketch":
        return "@psyketch.studio (US)"
    return "@psychologist.uday & TheKyunProject"


def _format_slot_label(slot_key: Optional[str]) -> str:
    mapping = {
        "morning": "🌅 Morning (06:00 AM IST)",
        "afternoon": "☀️ Afternoon (12:00 PM IST)",
        "evening": "🌙 Evening (05:30 PM IST)",
        "morning_us": "🌅 Morning US (09:00 AM EST)",
        "evening_us": "🌙 Evening US (08:00 PM EST)",
    }
    return mapping.get(slot_key or "", "⚡ Manual / Instant Run")


def notify_post_result(
    config: Config,
    file_name: str,
    youtube_title: str,
    slot_key: Optional[str],
    yt_video_id: Optional[str],
    ig_done: bool,
    remaining_count: int,
    errors: List[str],
) -> None:
    """Sends a Telegram notification after a publishing run completes."""
    header = "⚠️ *POST COMPLETED WITH ERRORS*" if errors else "✅ *NEW POST PUBLISHED*"
    yt_line = (
        f"[Watch Short](https://youtube.com/shorts/{yt_video_id})"
        if yt_video_id
        else ("❌ Failed" if any(e.startswith("YouTube:") for e in errors) else "⏭️ Skipped")
    )
    ig_line = (
        "✅ Dispatched to Instagram"
        if ig_done
        else ("❌ Failed" if any(e.startswith("Instagram:") for e in errors) else "⏭️ Skipped")
    )

    lines = [
        header,
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"👤 *Channel:* {_escape_md(_format_profile_label(config))}",
        f"⏰ *Slot:* {_escape_md(_format_slot_label(slot_key))}",
        f"🎬 *File:* `{file_name}`",
        f"📝 *Title:* {_escape_md(youtube_title)}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"▶️ *YouTube:* {yt_line}",
        f"📸 *Instagram:* {ig_line}",
    ]

    if remaining_count >= 0:
        lines.append(f"📁 *Queue Remaining:* {remaining_count} video(s)")
        if remaining_count == 0:
            lines.append("\n🚨 *QUEUE IS NOW EMPTY!* Upload new `.mp4` videos to Google Drive before the next slot.")

    if errors:
        lines.append("\n❌ *Errors:*")
        for err in errors:
            lines.append(f"• {_escape_md(err[:250])}")

    _send_telegram(config, "\n".join(lines))


def notify_empty_queue(config: Config, slot_key: Optional[str]) -> None:
    """Sends a Telegram alert when a scheduled slot finds 0 eligible videos in the Queue."""
    lines = [
        "📭 *QUEUE EMPTY — Nothing Posted*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"👤 *Channel:* {_escape_md(_format_profile_label(config))}",
        f"⏰ *Slot:* {_escape_md(_format_slot_label(slot_key))}",
        "⚠️ No eligible `.mp4` video was found in your Google Drive Queue for this slot. Upload videos to `Social Queue` for the next slot!",
    ]
    _send_telegram(config, "\n".join(lines))


def notify_fatal_error(config: Config, file_name: str, slot_key: Optional[str], error_msg: str) -> None:
    """Sends a Telegram alert if an unhandled exception occurs during AI analysis or download."""
    lines = [
        "❌ *AUTOMATION ERROR ALERT*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"👤 *Channel:* {_escape_md(_format_profile_label(config))}",
        f"⏰ *Slot:* {_escape_md(_format_slot_label(slot_key))}",
        f"🎬 *File:* `{file_name}`",
        f"⚠️ *Error:* {_escape_md(error_msg[:300])}",
    ]
    _send_telegram(config, "\n".join(lines))
