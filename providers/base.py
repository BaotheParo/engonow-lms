"""
providers/base.py
==================
Abstract interface and shared data contracts for all speaking evaluation providers.
Both GroqLocalProvider and AzureProvider MUST implement AbstractSpeakingProvider
and MUST return UnifiedSpeakingResult from their evaluate() method.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional


class EvaluationStatus(str, Enum):
    SUCCESS = "SUCCESS"   # All 4 criteria scored from their intended source
    PARTIAL = "PARTIAL"   # 1+ criteria used fallback score due to sub-pipeline failure
    FAILED  = "FAILED"    # Complete pipeline failure  no reliable scores produced


@dataclass
class UnifiedSpeakingResult:
    """
    The single output contract for all speaking evaluation providers.
    Maps 1:1 to the Java SpeakingWebhookPayload in the Spring Boot backend.

    Both GroqLocalProvider and AzureProvider must return this dataclass.
    The FastAPI endpoint serializes it directly to JSON for the Java webhook receiver.

    SCORE CONTRACT: pronunciation_score, fluency_score, grammar_score, lexical_score
    MUST all be integers in the range [1, 9] inclusive. Any other value is invalid.
    """

    #  Core Identity 
    session_id:    str
    provider_used: str   # "GROQ_LOCAL" or "AZURE"

    #  The 4 IELTS Criterion Scores 
    # All MUST be integers. All MUST be in range [1, 9]. No floats. No zeros.
    pronunciation_score: int
    fluency_score:       int
    grammar_score:       int
    lexical_score:       int

    #  Pipeline Status 
    status: str   # Use EvaluationStatus enum values as strings

    #  Data Quality Signal 
    # Proportion of words recognized with high ASR/phoneme confidence.
    # GROQ_LOCAL: proportion of words where Whisper probability >= threshold
    # AZURE:      proportion of words where Azure accuracy_score >= 70
    # Java backend uses this to flag potentially unreliable evaluations.
    genuine_word_coverage: float   # [0.0, 1.0]

    #  Feedback 
    feedback_text: str   # LLM-generated feedback summary for student portal

    #  Operational Metadata 
    processing_time_ms: float = 0.0
    provider_metadata: Dict   = field(default_factory=dict)
    # provider_metadata contains provider-specific sub-scores and warnings.
    # It is visible in the admin panel but NOT forwarded to the student.

    def to_dict(self) -> dict:
        """Serializes to the JSON payload format expected by Java Spring Boot."""
        return {
            "session_id":            self.session_id,
            "provider_used":         self.provider_used,
            "pronunciation_score":   self.pronunciation_score,
            "fluency_score":         self.fluency_score,
            "grammar_score":         self.grammar_score,
            "lexical_score":         self.lexical_score,
            "status":                self.status,
            "genuine_word_coverage": round(self.genuine_word_coverage, 4),
            "feedback_text":         self.feedback_text,
            "processing_time_ms":    round(self.processing_time_ms, 1),
            "provider_metadata":     self.provider_metadata,
        }

    def validate_scores(self) -> None:
        """
        Raises ValueError if any criterion score is not an integer in [1, 9].
        Call this before returning from provider.evaluate().
        """
        for name, value in [
            ("pronunciation_score", self.pronunciation_score),
            ("fluency_score",       self.fluency_score),
            ("grammar_score",       self.grammar_score),
            ("lexical_score",       self.lexical_score),
        ]:
            if not isinstance(value, int):
                raise ValueError(
                    f"Score contract violation: {name}={value!r} must be an int, "
                    f"got {type(value).__name__}."
                )
            if not (1 <= value <= 9):
                raise ValueError(
                    f"Score contract violation: {name}={value} is outside [1, 9]."
                )


class AbstractSpeakingProvider(ABC):
    """
    Strategy interface for IELTS Speaking evaluation providers.

    Concrete implementations:
      - GroqLocalProvider (providers/groq_local_provider.py): Free track
      - AzureProvider     (providers/azure_provider.py):      Paid track

    The FastAPI endpoint in mock_ai_services.py only interacts with this
    interface and never depends on concrete provider implementations.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns the provider identifier string: 'GROQ_LOCAL' or 'AZURE'."""

    @abstractmethod
    async def evaluate(
        self,
        session_id:         str,
        audio_url:          Optional[str],
        gemini_api_key:     str,
        questions_metadata: str = "",
        audio_bytes:        Optional[bytes] = None,
        audio_filename:     str = "audio.mp3",
    ) -> UnifiedSpeakingResult:
        """
        Full end-to-end evaluation pipeline from audio URL to scored result.

        Args:
            session_id:         Unique identifier for this speaking session.
            audio_url:          URL/local path, or None when audio_bytes is supplied.
            gemini_api_key:     API key for Gemini GRA/LR evaluation.
            questions_metadata: Examiner questions as formatted string for Gemini context.
            audio_bytes:        Raw uploaded audio for local/benchmark operation.
            audio_filename:     Original filename used to infer the audio format.

        Returns:
            UnifiedSpeakingResult with all 4 criterion scores as integers 1-9.
            MUST NOT raise exceptions  all errors must be caught internally and
            reflected as PARTIAL or FAILED status in the returned result.
        """

    def _clamp_band(self, value: float) -> int:
        """Shared utility: clamps a float to nearest integer in [1, 9]."""
        return max(1, min(9, round(value)))

    def _build_failed_result(
        self,
        session_id: str,
        error: str,
        fallback_pr: int = 4,
        fallback_fc: int = 4,
        fallback_gra: int = 4,
        fallback_lr: int = 4,
    ) -> UnifiedSpeakingResult:
        """
        Builds a FAILED UnifiedSpeakingResult for complete pipeline failures.
        Providers call this as the last-resort catch in evaluate().
        """
        return UnifiedSpeakingResult(
            session_id            = session_id,
            provider_used         = self.provider_name,
            pronunciation_score   = fallback_pr,
            fluency_score         = fallback_fc,
            grammar_score         = fallback_gra,
            lexical_score         = fallback_lr,
            status                = EvaluationStatus.FAILED,
            genuine_word_coverage = 0.0,
            feedback_text         = f"Evaluation failed due to a technical error: {error}",
            processing_time_ms    = 0.0,
            provider_metadata     = {"error": error, "warnings": ["PIPELINE_FAILED"]},
        )
