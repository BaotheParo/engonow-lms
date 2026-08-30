"""
acoustic package
================
Acoustic feature extraction, speech fluency analysis, pause classification,
audio continuity gating, phonetic diagnostics (GOP), word stress accuracy,
and pitch contour intonation analysis for IELTS Speaking assessment.
"""

from acoustic.models import WordTimestamp, PauseAnalysis, FluencyResult
from acoustic.continuity_gate import AudioContinuityGate
from acoustic.fluency_engine import FluencyEngine
from acoustic.phonetic_models import (
    PhonemeErrorType,
    PhonemeError,
    WordStressAnalysis,
    IntonationAnalysis,
    FullAcousticAnalysisResult,
)
from acoustic.g2p_engine import G2PEngine
from acoustic.pronunciation_engine import PronunciationEngine
from acoustic.acoustic_orchestrator import AcousticOrchestrator

__all__ = [
    "WordTimestamp",
    "PauseAnalysis",
    "FluencyResult",
    "AudioContinuityGate",
    "FluencyEngine",
    "PhonemeErrorType",
    "PhonemeError",
    "WordStressAnalysis",
    "IntonationAnalysis",
    "FullAcousticAnalysisResult",
    "G2PEngine",
    "PronunciationEngine",
    "AcousticOrchestrator",
]
