"""
ENGONOW AI Provider Package
============================
Pluggable strategy pattern for IELTS Speaking & Writing evaluation providers.
"""

from providers.base import (
    AbstractEvaluationProvider,
    AbstractSpeakingProvider,
    AbstractWritingProvider,
    BaseLLMProvider,
    EvaluationStatus,
    MalformedAIResponseError,
    ProviderCallError,
    UnifiedSpeakingResult,
    WritingEvaluationError,
)
from providers.factory import ProviderFactory, get_speaking_provider, get_writing_provider
from providers.gemini_speaking_provider import GeminiSpeakingProvider
from providers.gemini_writing_provider import GeminiWritingProvider
from providers.rounding import (
    calculate_overall_band,
    is_legal_band_value,
    round_to_nearest_half_band,
)
from providers.schemas_speaking_additions import (
    ContourPattern,
    ErrorSeverity,
    ExamPart,
    PhonemeDiagnostic,
    PhonemeErrorType,
    SpeakingCriterion,
    SpeakingCriterionFeedback,
    SpeakingEvaluationResult,
    SpeakingFeedbackDetail,
    SpeakingGrammarCorrection,
    SpeakingGrammarErrorType,
    SpeakingImprovementTip,
    SpeakingMetrics,
    SpeakingVocabularyUpgrade,
    cambridge_round,
)

__all__ = [
    "AbstractSpeakingProvider",
    "AbstractWritingProvider",
    "BaseLLMProvider",
    "UnifiedSpeakingResult",
    "EvaluationStatus",
    "ProviderFactory",
    "GeminiSpeakingProvider",
    "GeminiWritingProvider",
    "WritingEvaluationError",
    "MalformedAIResponseError",
    "ProviderCallError",
    "get_speaking_provider",
    "get_writing_provider",
    "round_to_nearest_half_band",
    "calculate_overall_band",
    "is_legal_band_value",
    "ExamPart",
    "SpeakingCriterion",
    "SpeakingGrammarErrorType",
    "ErrorSeverity",
    "PhonemeErrorType",
    "ContourPattern",
    "SpeakingMetrics",
    "SpeakingGrammarCorrection",
    "PhonemeDiagnostic",
    "SpeakingVocabularyUpgrade",
    "SpeakingImprovementTip",
    "SpeakingCriterionFeedback",
    "SpeakingFeedbackDetail",
    "SpeakingEvaluationResult",
    "cambridge_round",
]
