"""
ENGONOW AI Provider Package
============================
Pluggable strategy pattern for IELTS Speaking evaluation providers.

Usage:
    from providers.factory import get_speaking_provider
    provider = get_speaking_provider()
    result = await provider.evaluate(session_id, audio_url, gemini_api_key)
"""

from providers.base import AbstractSpeakingProvider, UnifiedSpeakingResult, EvaluationStatus
from providers.factory import get_speaking_provider

__all__ = [
    "AbstractSpeakingProvider",
    "UnifiedSpeakingResult",
    "EvaluationStatus",
    "get_speaking_provider",
]
