import logging
import time
from pathlib import Path
from typing import List
from google import genai
from pydantic import BaseModel, Field

from src.config import BRAND_SYSTEM_INSTRUCTION, Config

logger = logging.getLogger(__name__)


class ViralMetadata(BaseModel):
    video_summary: str = Field(
        description="1-2 sentence summary of the core psychological topic and spoken message in the video."
    )
    youtube_title: str = Field(
        description="Viral curiosity-gap YouTube Shorts title for TheKyunProject (max 95 characters, must include #Shorts)."
    )
    youtube_description: str = Field(
        description="Full SEO-optimized YouTube description for TheKyunProject including hook, key takeaways, CTA, and hashtags."
    )
    youtube_tags: List[str] = Field(
        description="List of 12-15 high-volume YouTube search tags (without '#' symbol) related to the video's psychology topic."
    )
    instagram_caption: str = Field(
        description="Full viral Instagram Reel caption for @psychologist.uday including 2-sentence hook, mechanism breakdown, actionable shift, Save/Share CTA, and 15 hashtags."
    )


def generate_viral_metadata(video_path: Path, original_filename: str, config: Config) -> ViralMetadata:
    """
    Uploads the video to the Gemini Files API, analyzes both audio and visual content
    with gemini-3.8-flash, and returns structured YouTube + Instagram metadata.
    """
    client = genai.Client(api_key=config.gemini_api_key)
    uploaded_file = None

    try:
        logger.info("Uploading '%s' to Gemini Files API for multimodal analysis...", original_filename)
        uploaded_file = client.files.upload(file=str(video_path))

        # Wait until the video file reaches ACTIVE state
        max_wait_seconds = 180
        elapsed = 0
        while not uploaded_file.state or uploaded_file.state.name != "ACTIVE":
            if uploaded_file.state and uploaded_file.state.name == "FAILED":
                raise RuntimeError(f"Gemini video processing failed for file: {original_filename}")
            if elapsed >= max_wait_seconds:
                raise TimeoutError(f"Timed out waiting for Gemini to process video: {original_filename}")
            logger.info("Waiting for Gemini video processing (state=%s)...", getattr(uploaded_file.state, "name", "PROCESSING"))
            time.sleep(5)
            elapsed += 5
            uploaded_file = client.files.get(name=uploaded_file.name)

        prompt = (
            f"Watch and listen to this vertical video carefully (original file name: '{original_filename}').\n"
            "Analyze the exact spoken hook, visual text/animations, psychological concept, and emotional payoff.\n"
            "Generate the structured viral metadata for:\n"
            "1. YouTube Shorts channel: TheKyunProject\n"
            "2. Instagram Reels account: @psychologist.uday\n"
            "Ensure the YouTube title is under 95 characters and ends with #Shorts."
        )

        candidate_models = list(
            dict.fromkeys(
                [
                    config.gemini_model,
                    "gemini-3.8-flash",
                    "gemini-3.7-flash",
                    "gemini-3.6-flash",
                    "gemini-3.5-flash",
                    "gemini-3.1-flash-lite",
                ]
            )
        )

        interaction = None
        last_err = None
        for model_name in candidate_models:
            try:
                logger.info("Generating viral caption & YouTube metadata with %s...", model_name)
                interaction = client.interactions.create(
                    model=model_name,
                    system_instruction=BRAND_SYSTEM_INSTRUCTION,
                    input=[
                        {"type": "video", "uri": uploaded_file.uri, "mime_type": uploaded_file.mime_type or "video/mp4"},
                        {"type": "text", "text": prompt},
                    ],
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": ViralMetadata.model_json_schema(),
                    },
                )
                break
            except Exception as exc:
                last_err = exc
                logger.warning("Model %s unavailable (%s); trying next fallback model...", model_name, exc)

        if interaction is None:
            raise RuntimeError(f"All Gemini models failed. Last error: {last_err}") from last_err

        metadata = ViralMetadata.model_validate_json(interaction.output_text)

        # Enforce YouTube 100-char title limit safety
        if len(metadata.youtube_title) > 100:
            metadata.youtube_title = metadata.youtube_title[:90].rstrip() + " #Shorts"
        elif "#shorts" not in metadata.youtube_title.lower():
            if len(metadata.youtube_title) <= 91:
                metadata.youtube_title = f"{metadata.youtube_title.rstrip()} #Shorts"

        logger.info("Generated YouTube Title: %s", metadata.youtube_title)
        return metadata

    finally:
        if uploaded_file and getattr(uploaded_file, "name", None):
            try:
                client.files.delete(name=uploaded_file.name)
                logger.debug("Cleaned up temporary file %s from Gemini Files API.", uploaded_file.name)
            except Exception as exc:
                logger.warning("Could not delete temporary Gemini file %s: %s", uploaded_file.name, exc)
