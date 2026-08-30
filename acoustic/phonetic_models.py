"""
acoustic/phonetic_models.py
===========================
Data contracts and model structures for phonetic error diagnostics,
Goodness-of-Pronunciation (GOP), word stress accuracy, and pitch intonation analysis.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


class PhonemeErrorType(str, Enum):
    SUBSTITUTION = "SUBSTITUTION"
    DELETION = "DELETION"
    INSERTION = "INSERTION"


@dataclass
class PhonemeError:
    """
    Diagnostic record for an individual IPA phoneme mispronunciation.
    """
    expected_phoneme_ipa: str
    produced_phoneme_ipa: Optional[str]      # None if DELETION
    error_type: PhonemeErrorType
    word_context: str
    start_time_seconds: float
    goodness_of_pronunciation_score: float   # Bounded [0.0, 1.0], < 0.65 indicates mispronunciation


@dataclass
class WordStressAnalysis:
    """
    Syllable-level primary lexical stress evaluation across polysyllabic words.
    """
    total_polysyllabic_words: int
    correctly_stressed_words: int
    stress_accuracy_ratio: float
    common_misstressed_words: List[str] = field(default_factory=list)


@dataclass
class IntonationAnalysis:
    """
    Speaker-relative fundamental frequency (F0) contour and expressiveness metrics.
    """
    pitch_range_hz: float
    pitch_standard_deviation_hz: float
    pitch_coefficient_of_variation: float   # std(F0) / median(F0)
    monotone_flag: bool                     # True if pitch CV < 0.12
    dominant_contour_pattern: str           # "FALLING", "RISING", "MIXED", "FLAT"


@dataclass
class FullAcousticAnalysisResult:
    """
    Unified end-to-end IELTS Speaking acoustic report combining Phase 4.2 Fluency
    with Phase 4.3 Phonetics, Stress, and Intonation diagnostics.
    """
    speaking_rate_wpm: float
    articulation_rate_wpm: float
    phonation_ratio: float
    total_duration_seconds: float
    phonation_time_seconds: float
    word_count: int
    pause_analysis: Dict[str, Any]
    phoneme_errors: List[PhonemeError]
    word_stress_analysis: WordStressAnalysis
    intonation_analysis: IntonationAnalysis
    excluded_from_automated_scoring: bool = False
    exclusion_reason: Optional[str] = None
