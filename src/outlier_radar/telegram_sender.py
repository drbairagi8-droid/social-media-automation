import logging
import os
from typing import List
import requests

from src.outlier_radar.config import OutlierVideo

logger = logging.getLogger(__name__)


def send_telegram_radar_report(videos: List[OutlierVideo], drive_doc_url: str = "") -> bool:
    """
    Sends the formatted Daily Outlier Radar report directly to the creator's Telegram chat.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "6866435263").strip()

    if not token or not chat_id:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set; skipping Telegram dispatch.")
        return False

    if not videos:
        msg = "🧠 *Daily Psychology Outlier Radar*\n\nNo significant outliers (>3x) detected in the last 72 hours. Everything within normal baselines."
        _send_raw(token, chat_id, msg)
        return True

    header = (
        "🧠 *DAILY PSYCHOLOGY OUTLIER RADAR*\n"
        f"📅 *Breakout Videos Detected:* {len(videos)}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    items_text = []
    for idx, v in enumerate(videos, 1):
        block = (
            f"🔥 *#{idx}: {v.title}*\n"
            f"👤 *Creator:* {v.channel_title} | 🚀 *{v.outlier_multiplier}x Outlier*\n"
            f"👁 *Views:* {v.view_count:,} (Channel avg: {v.channel_median_views:,})\n"
            f"🔗 [Watch Video]({v.url})\n\n"
            f"🎯 *The 3s Hook:* {v.hook_deconstruction}\n"
            f"🧬 *Mechanism:* {v.psychological_mechanism}\n"
            f"💡 *Why It Outperformed:* {v.why_it_worked}\n"
            f"🎨 *Uday Adaptation Idea:* {v.adaptation_angle}\n"
            "──────────────────────\n\n"
        )
        items_text.append(block)

    footer = ""
    if drive_doc_url:
        footer = f"\n📄 *Full Detailed Doc Saved in Drive:*\n{drive_doc_url}"

    # Telegram has a 4096 character limit per message; send in structured chunks
    chunks = []
    current_chunk = header
    for block in items_text:
        if len(current_chunk) + len(block) > 3800:
            chunks.append(current_chunk)
            current_chunk = block
        else:
            current_chunk += block

    if footer:
        if len(current_chunk) + len(footer) > 3800:
            chunks.append(current_chunk)
            chunks.append(footer)
        else:
            current_chunk += footer

    if current_chunk:
        chunks.append(current_chunk)

    success = True
    for chunk in chunks:
        ok = _send_raw(token, chat_id, chunk)
        if not ok:
            success = False

    return success


def _send_raw(token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=20)
        if not resp.ok:
            # Fallback to plain text if Markdown fails due to special characters
            payload.pop("parse_mode", None)
            resp = requests.post(url, json=payload, timeout=20)
        return resp.ok
    except Exception as exc:
        logger.error("Failed to send Telegram message: %s", exc)
        return False
