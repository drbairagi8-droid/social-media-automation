import json
import logging
from typing import List
from google import genai
from pydantic import BaseModel, Field

from src.config import Config
from src.outlier_radar.config import OutlierVideo

logger = logging.getLogger(__name__)


class DeconstructionItem(BaseModel):
    video_id: str
    hook_deconstruction: str = Field(
        description="Analysis of the first 3-second hook: the exact pattern interrupt, visual trigger, and opening words."
    )
    psychological_mechanism: str = Field(
        description="The scientific/behavioral principle being highlighted (e.g. Fawn response, Cognitive Dissonance, Safe Emotional Sandbox)."
    )
    why_it_worked: str = Field(
        description="The core viral reason this video outperformed the channel average (e.g. hyper-specific relatability, controversy, emotional validation)."
    )
    adaptation_angle: str = Field(
        description="A concrete, original concept adaptation for Psychologist Uday (@psychologist.uday / TheKyunProject 2D character rig) without copying."
    )


class BatchDeconstruction(BaseModel):
    items: List[DeconstructionItem]


DECONSTRUCTOR_SYSTEM_PROMPT = """You are the Senior Viral Retention Analyst and Behavioral Psychology Strategist for **Psychologist Uday** (@psychologist.uday) and **TheKyunProject** ("The Why Project").

Your goal is to reverse-engineer high-performing "outlier" psychology videos (videos that got significantly more views than the creator's channel average in the last 72 hours).

For each video, analyze:
1. **The 3-Second Hook**: What exact curiosity gap, pattern interrupt, or relatable dilemma stopped the viewer's thumb?
2. **The Psychological Mechanism**: What exact behavioral science, cognitive bias, neuroscience, or attachment theory concept does this tap into?
3. **Why It Outperformed**: What psychological trigger drove high retention, shares, or saves?
4. **Adaptation for Psychologist Uday**: How can Psychologist Uday take this validated concept and create an original, authentic breakdown starring his 2D animated character rig (wavy quiff, beard, sage rolled-sleeve shirt) with zero copying?
"""


def deconstruct_outliers(videos: List[OutlierVideo], config: Config) -> List[OutlierVideo]:
    """
    Uses Gemini to perform deep viral reverse-engineering on a batch of outlier videos.
    """
    if not videos:
        return []

    client = genai.Client(api_key=config.gemini_api_key)
    if hasattr(client, "interactions") and hasattr(client.interactions, "sdk_configuration"):
        client.interactions.sdk_configuration.retry_config = None
    logger.info("Running Gemini deep viral deconstruction on %d outlier videos...", len(videos))

    summaries = []
    for idx, v in enumerate(videos, 1):
        summaries.append(
            f"[{idx}] ID: {v.video_id}\n"
            f"Platform: {v.platform}\n"
            f"Title: {v.title}\n"
            f"Channel: {v.channel_title}\n"
            f"Views: {v.view_count:,} (Channel Baseline: {v.channel_median_views:,} -> Multiplier: {v.outlier_multiplier}x)\n"
            f"Description/Context: {v.description}\n"
            f"URL: {v.url}\n"
        )

    user_prompt = (
        "Here are the recent breakout psychology outlier videos from the last 72 hours:\n\n"
        + "\n---\n".join(summaries)
        + "\n\nProvide the structured deep reverse-engineering for each video."
    )

    candidate_models = list(
        dict.fromkeys(
            [
                config.gemini_model,
                "gemini-3.8-flash",
                "gemini-3.7-flash",
                "gemini-3.5-flash",
                "gemini-3.1-flash-lite",
            ]
        )
    )

    batch_result = None
    last_err = None
    for model_name in candidate_models:
        try:
            interaction = client.interactions.create(
                model=model_name,
                system_instruction=DECONSTRUCTOR_SYSTEM_PROMPT,
                input=[{"type": "text", "text": user_prompt}],
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": BatchDeconstruction.model_json_schema(),
                },
            )
            batch_result = BatchDeconstruction.model_validate_json(interaction.output_text)
            break
        except Exception as exc:
            last_err = exc
            logger.warning("Gemini deconstruction with %s failed (%s); trying fallback...", model_name, exc)

    if not batch_result:
        logger.error("Could not deconstruct outliers with Gemini: %s", last_err)
        return videos

    analysis_map = {item.video_id: item for item in batch_result.items}

    for v in videos:
        if v.video_id in analysis_map:
            analysis = analysis_map[v.video_id]
            v.hook_deconstruction = analysis.hook_deconstruction
            v.psychological_mechanism = analysis.psychological_mechanism
            v.why_it_worked = analysis.why_it_worked
            v.adaptation_angle = analysis.adaptation_angle

    return videos
