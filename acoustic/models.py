"""
acoustic/models.py
==================
Data contracts and acoustic model structures for IELTS Speaking fluency evaluation,
pause dynamics, and audio continuity analysis.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class WordTimestamp:
    """
    Word-level alignment timestamp produced by Faster-Whisper or forced aligner.
    """
    word: str
    start: float
    end: float
    probability: float = 1.0

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class PauseAnalysis:
    """
    Detailed breakdown of pause categories and disfluencies detected in the audio.
    """
    filled_pause_count: int = 0
    filled_pause_counts_by_type: Dict[str, int] = field(default_factory=dict)
    silent_cognitive_pause_count: int = 0         # Natural silent pauses > 0.75s
    silent_micro_pause_count: int = 0             # Natural micro-pauses 0.25s - 0.75s
    average_cognitive_pause_duration_seconds: float = 0.0
    total_pause_duration_seconds: float = 0.0
    possible_technical_artifact_count: int = 0    # Excluded from cognitive pause penalty


@dataclass
class FluencyResult:
    """
    Comprehensive IELTS Speaking acoustic fluency metrics and continuity status.
    """
    speaking_rate_wpm: float
    articulation_rate_wpm: float
    phonation_ratio: float
    total_duration_seconds: float
    phonation_time_seconds: float
    word_count: int
    pause_analysis: PauseAnalysis
    excluded_from_automated_scoring: bool = False
    exclusion_reason: Optional[str] = None
