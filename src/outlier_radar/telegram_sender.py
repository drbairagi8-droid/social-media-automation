import logging
import os
from typing import List, Optional
import requests

from src.outlier_radar.config import OutlierVideo
from src.outlier_radar.script_writer import RefinedScript

logger = logging.getLogger(__name__)


def send_telegram_radar_report(
    videos: List[OutlierVideo],
    scripts: Optional[List[RefinedScript]] = None,
    drive_doc_url: str = "",
) -> bool:
    """
    Sends the formatted Daily Outlier Radar and 5 Script previews directly to Telegram.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "6866435263").strip()

    if not token or not chat_id:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set; skipping Telegram dispatch.")
        return False

    scripts = scripts or []
    header = (
        "🧠 *DAILY PSYCHOLOGY SCRIPT BRIEFING*\n"
        f"📅 *5 Production-Ready Hindi Scripts Generated*\n"
        f"🔍 *Outlier Topics Analyzed:* {len(videos)}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    scripts_blocks = []
    if scripts:
        scripts_blocks.append("🎬 *TODAY'S 5 PRODUCTION SCRIPTS:*\n\n")
        for idx, s in enumerate(scripts, 1):
            block = (
                f"✨ *Script #{idx}: {s.topic_name}*\n"
                f"🎭 *Format:* {s.format_type}\n"
                f"🇮🇳 *Indian Relatability:* {s.indian_relatability_angle}\n"
                f"🚀 *Share Catalyst:* {s.share_catalyst}\n"
                f"💡 *Mechanism:* {s.summary_and_mechanism[:160]}...\n"
                "──────────────────────\n"
            )
            scripts_blocks.append(block)

    outliers_summary = "\n🔥 *TOP OUTLIER BREAKOUTS STUDIED:*\n"
    for idx, v in enumerate(videos[:3], 1):
        outliers_summary += f"• *{v.channel_title}*: {v.title[:45]}... (*{v.outlier_multiplier}x*)\n"

    footer = ""
    if drive_doc_url:
        footer = (
            f"\n📄 *FULL SCRIPTS & STORYBOARD CUES IN DRIVE:*\n"
            f"[👉 Open Today's Google Doc]({drive_doc_url})"
        )

    # Format chunks for Telegram 4096 char limit
    full_text = header + "".join(scripts_blocks) + outliers_summary + footer
    chunks = []
    if len(full_text) > 3800:
        # Split into Script Part and Outlier Part
        chunk1 = header + "".join(scripts_blocks[:3])
        chunk2 = "".join(scripts_blocks[3:]) + outliers_summary + footer
        chunks = [chunk1, chunk2]
    else:
        chunks = [full_text]

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
            payload.pop("parse_mode", None)
            resp = requests.post(url, json=payload, timeout=20)
        return resp.ok
    except Exception as exc:
        logger.error("Failed to send Telegram message: %s", exc)
        return False
