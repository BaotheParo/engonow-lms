"""
ENGONOW AI Provider Package
============================
Pluggable strategy pattern for IELTS Speaking evaluation providers.

Usage:
    from providers.factory import get_speaking_provider
    provider = get_speaking_provider()
    result = await provider.evaluate(session_id, audio_url, gemini_api_key)
"""

from providers.base import (
    AbstractEvaluationProvider,  # Alias if desired
    AbstractSpeakingProvider,
    AbstractWritingProvider,
    EvaluationStatus,
    MalformedAIResponseError,
    UnifiedSpeakingResult,
    WritingEvaluationError,
)
from providers.factory import get_speaking_provider, get_writing_provider
from providers.gemini_writing_provider import GeminiWritingProvider

__all__ = [
    "AbstractSpeakingProvider",
    "AbstractWritingProvider",
    "UnifiedSpeakingResult",
    "EvaluationStatus",
    "GeminiWritingProvider",
    "WritingEvaluationError",
    "MalformedAIResponseError",
    "get_speaking_provider",
    "get_writing_provider",
]

