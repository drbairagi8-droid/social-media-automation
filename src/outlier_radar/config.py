"""
Configuration and target tracking parameters for the Psychology Outlier Radar.
"""
from dataclasses import dataclass, field
from typing import List

# High-intent psychology search queries for recent breakout shorts
TARGET_QUERIES = [
    "psychology facts shorts",
    "human behavior shorts",
    "psychological trick shorts",
    "attachment styles shorts",
    "overthinking psychology shorts",
    "fawn response boundaries shorts",
    "cognitive biases psychology shorts",
    "emotional regulation nervous system shorts",
    "relationship psychology quirks shorts",
    "subconscious mind human behavior shorts",
]

# Benchmark YouTube Channels in behavioral science, neuroscience & clinical psychology
BENCHMARK_CHANNELS = [
    {"name": "Psych2Go", "id": "UCkJEpR7J44S06pxEySC45dg"},
    {"name": "HealthyGamerGG", "id": "UClHVl2N3jPEbkNJVx-ItQIQ"},
    {"name": "Dr. Julie", "id": "UC9_O6d-3X_bJtZc4y8zU26g"},
    {"name": "Therapy in a Nutshell", "id": "UCpuqYFKLkcEryEieomiAv3Q"},
    {"name": "Sprouts", "id": "UCkjJ2d04J7fXy1sJ2j8U8eg"},
]


@dataclass
class OutlierVideo:
    platform: str
    video_id: str
    title: str
    url: str
    channel_title: str
    channel_id: str
    published_at: str
    view_count: int
    channel_median_views: int
    outlier_multiplier: float
    description: str = ""
    # Analysis fields populated by Gemini
    hook_deconstruction: str = ""
    psychological_mechanism: str = ""
    why_it_worked: str = ""
    adaptation_angle: str = ""
