import concurrent.futures
import logging
import re
import time
from pathlib import Path
from typing import List
from google import genai
from pydantic import BaseModel, Field

from src.config import BRAND_SYSTEM_INSTRUCTION, Config

logger = logging.getLogger(__name__)


def enforce_max_hashtags(caption: str, max_hashtags: int = 5) -> str:
    """Ensures caption contains at most max_hashtags hashtags, trimming excess from the end."""
    all_tags = re.findall(r"#\w+", caption)
    if len(all_tags) <= max_hashtags:
        return caption

    remove_tags = set(all_tags[max_hashtags:])
    for tag in remove_tags:
        caption = re.sub(rf"{re.escape(tag)}(?=\s|$)", "", caption)

    lines = [re.sub(r"\s+", " ", line).strip() for line in caption.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines).strip()


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
        description="Full viral Instagram Reel caption for @psychologist.uday including 2-sentence hook, mechanism breakdown, actionable shift, Save/Share CTA, and strictly 3 to 5 hashtags (never exceed 5 hashtags)."
    )


def generate_viral_metadata(video_path: Path, original_filename: str, config: Config) -> ViralMetadata:
    """
    Uploads the video to the Gemini Files API, analyzes both audio and visual content
    with gemini-3.8-flash, and returns structured YouTube + Instagram + LinkedIn metadata.
    """
    client = genai.Client(api_key=config.gemini_api_key)
    if hasattr(client, "interactions") and hasattr(client.interactions, "sdk_configuration"):
        client.interactions.sdk_configuration.retry_config = None
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
                    "gemini-3.8-flash",
                    config.gemini_model,
                    "gemini-3.5-flash",
                    "gemini-3.1-flash-lite",
                ]
            )
        )

        def _call_gemini_model(m_name: str):
            return client.interactions.create(
                model=m_name,
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
                timeout=90.0,
            )

        interaction = None
        last_err = None
        for model_name in candidate_models:
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            try:
                logger.info("Generating viral caption & YouTube/Instagram metadata with %s (timeout=90s)...", model_name)
                future = executor.submit(_call_gemini_model, model_name)
                interaction = future.result(timeout=100.0)
                if interaction and getattr(interaction, "output_text", None):
                    break
            except concurrent.futures.TimeoutError:
                last_err = TimeoutError(f"Model {model_name} did not respond within 100 seconds.")
                logger.warning("Model %s timed out after 100s; falling back to next candidate model...", model_name)
            except Exception as exc:
                last_err = exc
                logger.warning("Model %s unavailable (%s); falling back to next candidate model...", model_name, exc)
            finally:
                executor.shutdown(wait=False)

        if interaction is None:
            raise RuntimeError(f"All Gemini models failed. Last error: {last_err}") from last_err

        metadata = ViralMetadata.model_validate_json(interaction.output_text)

        # Enforce YouTube 100-char title limit safety
        if len(metadata.youtube_title) > 100:
            metadata.youtube_title = metadata.youtube_title[:90].rstrip() + " #Shorts"
        elif "#shorts" not in metadata.youtube_title.lower():
            if len(metadata.youtube_title) <= 91:
                metadata.youtube_title = f"{metadata.youtube_title.rstrip()} #Shorts"

        # Enforce strict 5 hashtags maximum on Instagram Reel caption
        metadata.instagram_caption = enforce_max_hashtags(metadata.instagram_caption, max_hashtags=5)

        logger.info("Generated YouTube Title: %s", metadata.youtube_title)
        return metadata

    finally:
        if uploaded_file and getattr(uploaded_file, "name", None):
            try:
                client.files.delete(name=uploaded_file.name)
                logger.debug("Cleaned up temporary file %s from Gemini Files API.", uploaded_file.name)
            except Exception as exc:
                logger.warning("Could not delete temporary Gemini file %s: %s", uploaded_file.name, exc)
