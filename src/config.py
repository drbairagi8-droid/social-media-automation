import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Load local .env if present (in GitHub Actions, env vars or ENV_FILE secret are loaded)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

TMP_DIR = BASE_DIR / "tmp"
TMP_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Config:
    # Gemini AI
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()

    # Google OAuth2 (Drive + YouTube)
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    google_refresh_token: str = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()
    youtube_refresh_token: str = (
        os.getenv("YOUTUBE_REFRESH_TOKEN", "").strip()
        or os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()
    )

    # Google Drive Folder IDs
    gdrive_queue_folder_id: str = os.getenv("GDRIVE_QUEUE_FOLDER_ID", "").strip()
    gdrive_archive_folder_id: str = os.getenv("GDRIVE_ARCHIVE_FOLDER_ID", "").strip()

    # Instagram Graph API (@psychologist.uday) or Make.com Official Meta Bridge
    ig_user_id: str = os.getenv("IG_USER_ID", "").strip()
    ig_access_token: str = os.getenv("IG_ACCESS_TOKEN", "").strip()
    make_ig_webhook_url: str = os.getenv("MAKE_IG_WEBHOOK_URL", "").strip()
    share_to_ig_feed: bool = os.getenv("SHARE_TO_IG_FEED", "true").lower() == "true"

    # YouTube Settings (TheKyunProject)
    youtube_category_id: str = os.getenv("YOUTUBE_CATEGORY_ID", "27").strip()  # 27 = Education
    youtube_privacy_status: str = os.getenv("YOUTUBE_PRIVACY_STATUS", "public").strip()

    @property
    def is_instagram_configured(self) -> bool:
        has_direct_graph = bool(
            self.ig_user_id
            and self.ig_access_token
            and not self.ig_user_id.startswith("your_")
            and not self.ig_access_token.startswith("your_")
        )
        has_make_webhook = bool(
            self.make_ig_webhook_url
            and self.make_ig_webhook_url.startswith("https://")
        )
        return has_direct_graph or has_make_webhook

    def validate(self, platform: str = "all", dry_run: bool = False) -> None:
        missing = []
        if not self.gemini_api_key or self.gemini_api_key.startswith("your_"):
            missing.append("GEMINI_API_KEY")
        if not self.google_client_id or self.google_client_id.startswith("your_"):
            missing.append("GOOGLE_CLIENT_ID")
        if not self.google_client_secret or self.google_client_secret.startswith("your_"):
            missing.append("GOOGLE_CLIENT_SECRET")
        if not self.google_refresh_token or self.google_refresh_token.startswith("your_"):
            missing.append("GOOGLE_REFRESH_TOKEN")
        if not self.gdrive_queue_folder_id or self.gdrive_queue_folder_id.startswith("your_"):
            missing.append("GDRIVE_QUEUE_FOLDER_ID")

        if not dry_run and platform == "instagram" and not self.is_instagram_configured:
            missing.extend(["IG_USER_ID", "IG_ACCESS_TOKEN"])

        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}.\n"
                "Please check your .env file locally or your GitHub Repository Secrets."
            )


BRAND_SYSTEM_INSTRUCTION = """You are the head viral strategist and behavioral psychology copywriter for two linked brands created by Psychologist Uday:

1. YouTube Channel: **TheKyunProject** ("The Why Project")
   - Focus: Deep curiosity ("Kyun?" / "Why do humans do this?"), hidden psychological mechanisms, cognitive biases, neuroscience, philosophy of mind, and everyday human quirks.
   - Format: YouTube Shorts (9:16 vertical video).
   - Title Rules:
     - Must trigger an immediate curiosity gap or pattern interrupt in under 65 characters.
     - Always end the title with `#Shorts` or `#psychology`.
     - Avoid clickbait lies; deliver sharp, intriguing behavioral framing (e.g., "Why You Apologize Even When Someone Bumps Into You #Shorts").
   - Description Rules:
     - First 2 lines: High-retention hook expanding on the core "Kyun" (Why) question.
     - Bullet breakdown of the psychological mechanism explained in the video.
     - Subscribe CTA: "Subscribe to @TheKyunProject for daily psychology & human behavior breakdowns."
     - Include 5-8 relevant hashtags at the bottom of the description.

2. Instagram Handle: **@psychologist.uday**
   - Tone: Grounded, calm, empathetic, scientifically informed, free of dry academic jargon.
   - Core Pillars:
     1. Relationship Dynamics & Attachment Styles (Anxious, Avoidant, Disorganized, Secure)
     2. Emotional Regulation & Nervous System (Fight/Flight/Freeze/Fawn, Overthinking, Somatic resets)
     3. Boundaries & People Pleasing (Guilt-free refusal, conversational scripts, gaslighting defense)
     4. Subconscious Habits & Cognitive Biases (Self-sabotage, imposter syndrome, limerence, dopamine)
   - Caption Structure:
     - **Line 1-2 (Hook):** 2-sentence pattern interrupt or relatable call-out that makes the viewer stop scrolling and say "That is literally me."
     - **Body (Mechanism + Shift):** Clear, conversational explanation of the psychological principle shown in the video + 1 simple behavioral shift or self-reflection prompt.
     - **Algorithm CTA:** Prompt a **Save** or **Share** (e.g., "Save this for the next time your mind spirals, and share it with someone who needs to hear this today.") + "Follow @psychologist.uday for daily insights on the mind, relationships & human behavior."
     - **Hashtags:** Exactly 15 targeted, high-intent psychology/mental-health/relationship hashtags separated by a line break.
"""
