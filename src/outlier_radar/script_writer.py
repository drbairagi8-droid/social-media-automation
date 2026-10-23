import logging
from typing import List, Literal
from google import genai
from pydantic import BaseModel, Field

from src.config import Config
from src.outlier_radar.config import OutlierVideo

logger = logging.getLogger(__name__)


class ScriptDraft(BaseModel):
    topic_name: str = Field(description="Name of the psychological phenomenon/topic.")
    source_outlier_title: str = Field(description="Title of the real outlier video this was inspired by.")
    format_type: Literal[
        "2-Character Dialogue Skit (Priya & Uday)", "Solo Voiceover + 2D Animated B-Rolls"
    ] = Field(description="Video format choice.")
    indian_relatability_angle: str = Field(
        description="Why this is intensely relatable to everyday Indian households, college, corporate or friend dynamics."
    )
    share_catalyst: str = Field(
        description="The exact reason someone will DM this to a specific person (Call-out, Vindication, or Caring check-in)."
    )
    summary_and_mechanism: str = Field(
        description="2-3 sentence scientific/psychological explanation of the 'Kyun?' (Why)."
    )
    animation_vision: str = Field(
        description="Detailed Remotion storyboard directions: character poses, props, facial expressions, visual metaphors, on-screen text."
    )
    hindi_dialogue_script: str = Field(
        description="Full spoken Hindi/Hinglish script with timestamps/cues. Fast-paced, witty, colloquial, natural conversational rhythm."
    )


class ScriptDraftBatch(BaseModel):
    scripts: List[ScriptDraft]


class RefinedScript(BaseModel):
    topic_name: str
    source_outlier_title: str
    format_type: str
    indian_relatability_angle: str
    share_catalyst: str
    summary_and_mechanism: str
    animation_vision: str
    editorial_critique: str = Field(
        description="Director's critique: identifies any stiff/unnatural lines, slow hooks, or weak punchlines."
    )
    final_refined_script: str = Field(
        description="Polished, production-ready spoken Hindi/Hinglish script with sharp comedic timing and emotional payoff."
    )


class FinalScriptBatch(BaseModel):
    scripts: List[RefinedScript]


PASS1_SYSTEM_PROMPT = """You are the Lead Creative Director & Behavioral Psychology Scriptwriter for **Psychologist Uday** (@psychologist.uday) and **TheKyunProject** ("The Why Project").

Your mission is to take 10 real-world outlier psychology videos discovered in today's research, select the **TOP 5 BEST TOPICS**, and draft full production-ready Hindi/Hinglish scripts for them.

CRITICAL SCREENING FILTERS:
1. **Mass Indian Relatability**: The topic MUST relate to real-life Indian social dynamics: family pressure, rishtedaar dilemmas, log kya kahenge, sibling fights over chargers/Maggi, hesitation to say 'No', over-apologizing to elders/colleagues, exam guilt, corporate people-pleasing. Discard abstract Western therapy tropes.
2. **The "Why Share This?" Acid Test**: Every script must have a direct, obvious reason for someone to DM it to a friend, sibling, or partner:
   - Call-Out ("Bhai yeh tu hai!")
   - Vindication ("Dekh, main pagal nahi hoon, science kehti hai!")
   - Caring Check-in ("Thought of you, take it easy today.")

FORMAT SPECIFICATIONS:
- **Format A (Default ~3-4 scripts): 2-Character Dialogue Skit (Priya & Uday)**
  - Characters: Uday (relatable subconscious of the viewer, slightly lazy, witty, defends weird habits) vs Priya (sharp, observant psychologist friend, calls Uday out, drops the science).
  - Pacing: Starts with a funny/weird taunt or micro-action, rapid banter, drops the psychological concept with a funny/cute analogy, ends with a punchline that doubles as an organic share prompt.
  - GOLD STANDARD BENCHMARK TO EMULATE:
    Priya: "Uday, kal raat maine tujhe message kiya tha ki kaisa hai, uska reply toh aaya nahi, par subah se teri aath reels aa chuki hain!"
    Uday: "Haan toh woh aath reels hi mera reply tha! Zinda hoon, tujhe bhoola nahi hoon, bas abhi lambi baat karne ki himmat nahi hai."
    Priya: "Matlab ab humari dosti mein haal-chaal poochne ki jagah sirf reels chalengi?"
    Uday: "Yaar kaisa hai ka jawab dene ke liye poori zindagi ka dukh-dard type karna padta hai, reel bhejna kitna aasan hai!"
    Priya: "Waise mazaak se hatke, psychology mein isse Social Pebbling kehte hain. Jaise penguins apne pasandida sathi ko chhote-chhote patthar laake dete hain, waise hi hum apne kareebi logon ko memes aur reels bhejte hain..."
- **Format B (~1-2 scripts): Solo Voiceover + 2D Animated B-Rolls**
  - Uday speaking directly to viewer with rich Remotion visual metaphors, kinetic text, and introspective depth.

Tone: 100% natural conversational Indian Hindi/Hinglish. NO textbook translated Hindi (never write 'मनोवैज्ञानिक दृष्टिकोण' or 'सामाजिक पेबलिंग का सिद्धांत'). Use natural spoken phrasing: 'Bhai sun', 'dimaag ka fuse udna', 'kabhi notice kiya hai', 'guilt trip'.
"""

PASS2_SYSTEM_PROMPT = """You are the Senior Executive Script Editor & Showrunner for Psychologist Uday.
Your job is to review the 5 drafted Hindi scripts, ruthlessly eliminate any weakness, and polish them to perfection.

REVIEW & REFINE CHECKLIST:
1. **Natural Dialogue Polish**: Check every line of Hindi. If a line sounds even slightly translated, stiff, or bookish, rewrite it into real colloquial Hindi that young Indians actually speak.
2. **Hook Speed (2.5 Seconds)**: Ensure the opening line hits a conflict, accusation, or absurd visual immediately. Cut any slow greetings or setup.
3. **Comedic Timing & Punchiness**: Punch up Uday's funny defenses and Priya's witty comebacks. Ensure the dialogue bounces back and forth fast.
4. **Remotion Animation Vision**: Make sure the visual directions specify clear character rig poses (Uday quiff/beard/sage shirt, Priya), facial expressions, and visual metaphors.
5. **Organic Share CTA**: The ending must make sharing the video part of the joke.

Provide your brief editorial critique and the finalized, polished production script.
"""


def generate_and_refine_scripts(outliers: List[OutlierVideo], config: Config) -> List[RefinedScript]:
    """
    Two-Pass Script Generator:
    - Pass 1: Selects 5 best researched outlier topics and drafts production scripts.
    - Pass 2: Senior Editor reviews, critiques, and refines dialogue and comedic timing.
    """
    if not outliers:
        logger.warning("No outlier videos provided for scriptwriting.")
        return []

    client = genai.Client(api_key=config.gemini_api_key)
    if hasattr(client, "interactions") and hasattr(client.interactions, "sdk_configuration"):
        client.interactions.sdk_configuration.retry_config = None

    # 1. Format researched outliers as context
    research_summary = []
    for idx, v in enumerate(outliers, 1):
        research_summary.append(
            f"Topic #{idx}: {v.title}\n"
            f"- Creator: {v.channel_title} | Views: {v.view_count:,} ({v.outlier_multiplier}x Outlier)\n"
            f"- Hook: {v.hook_deconstruction}\n"
            f"- Mechanism: {v.psychological_mechanism}\n"
            f"- Why it blew up: {v.why_it_worked}\n"
            f"- Adaptation Spark: {v.adaptation_angle}\n"
        )
    outliers_text = "\n---\n".join(research_summary)

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

    # ==========================================
    # PASS 1: The Writer Drafts 5 Scripts
    # ==========================================
    logger.info("Pass 1: Screening topics for Indian relatability and drafting 5 scripts...")
    pass1_prompt = (
        "Here are the 10 breakout psychology outlier topics discovered in today's research:\n\n"
        f"{outliers_text}\n\n"
        "Select the TOP 5 BEST TOPICS based on Indian mass relatability and shareability, "
        "and draft the 5 complete production scripts."
    )

    draft_batch = None
    last_err = None
    for model_name in candidate_models:
        try:
            interaction = client.interactions.create(
                model=model_name,
                system_instruction=PASS1_SYSTEM_PROMPT,
                input=[{"type": "text", "text": pass1_prompt}],
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": ScriptDraftBatch.model_json_schema(),
                },
            )
            draft_batch = ScriptDraftBatch.model_validate_json(interaction.output_text)
            break
        except Exception as exc:
            last_err = exc
            logger.warning("Pass 1 failed on model %s (%s); trying next model...", model_name, exc)

    if not draft_batch or not draft_batch.scripts:
        raise RuntimeError(f"Pass 1 script drafting failed: {last_err}")

    logger.info("Pass 1 complete! Drafted %d scripts. Starting Pass 2 Editorial Review...", len(draft_batch.scripts))

    # ==========================================
    # PASS 2: The Senior Editor Reviews & Refines
    # ==========================================
    drafts_json = draft_batch.model_dump_json(indent=2)
    pass2_prompt = (
        "Review each of the following 5 drafted Hindi psychology scripts.\n"
        "Critique them for spoken dialogue naturalness, 2.5-second hook speed, comedic punchlines, "
        "and Remotion visual directions. Then provide the final polished, refined production scripts:\n\n"
        f"{drafts_json}"
    )

    final_batch = None
    for model_name in candidate_models:
        try:
            interaction = client.interactions.create(
                model=model_name,
                system_instruction=PASS2_SYSTEM_PROMPT,
                input=[{"type": "text", "text": pass2_prompt}],
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": FinalScriptBatch.model_json_schema(),
                },
            )
            final_batch = FinalScriptBatch.model_validate_json(interaction.output_text)
            break
        except Exception as exc:
            last_err = exc
            logger.warning("Pass 2 review failed on model %s (%s); trying next model...", model_name, exc)

    if not final_batch or not final_batch.scripts:
        logger.warning("Pass 2 review failed (%s); falling back to Pass 1 drafts.", last_err)
        # Fallback cleanly to Pass 1 drafts converted to RefinedScript format
        fallback_scripts = []
        for d in draft_batch.scripts:
            fallback_scripts.append(
                RefinedScript(
                    topic_name=d.topic_name,
                    source_outlier_title=d.source_outlier_title,
                    format_type=d.format_type,
                    indian_relatability_angle=d.indian_relatability_angle,
                    share_catalyst=d.share_catalyst,
                    summary_and_mechanism=d.summary_and_mechanism,
                    animation_vision=d.animation_vision,
                    editorial_critique="Pass 1 direct draft (auto-approved).",
                    final_refined_script=d.hindi_dialogue_script,
                )
            )
        return fallback_scripts

    logger.info("Pass 2 Editorial Review successfully polished all %d scripts!", len(final_batch.scripts))
    return final_batch.scripts
