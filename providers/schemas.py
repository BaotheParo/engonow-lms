"""
providers/schemas.py
====================
Pydantic v2 domain schemas for IELTS Writing evaluation and feedback details.
Maps 1:1 with Java backend DTOs and enterprise LMS database contracts with
strict schema enforcement, Str-Enums, and IELTS band validation.
"""

from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaskType(str, Enum):
    """Supported IELTS Writing task categories."""
    ACADEMIC_TASK1 = "ACADEMIC_TASK1"
    GENERAL_TASK1 = "GENERAL_TASK1"
    TASK2 = "TASK2"
    FULL_TEST = "FULL_TEST"


class CorrectionErrorType(str, Enum):
    """Taxonomy used to classify sentence-level corrections."""
    GRAMMAR = "GRAMMAR"
    VOCABULARY = "VOCABULARY"
    SPELLING = "SPELLING"
    PUNCTUATION = "PUNCTUATION"
    COHESION = "COHESION"
    TASK_RELEVANCE = "TASK_RELEVANCE"


class ErrorSeverity(str, Enum):
    """Pedagogical impact of a detected writing error."""
    MINOR = "MINOR"
    MAJOR = "MAJOR"
    CRITICAL = "CRITICAL"


class WritingCriterion(str, Enum):
    """Official IELTS assessment criteria."""
    TASK_ACHIEVEMENT = "TASK_ACHIEVEMENT"
    TASK_RESPONSE = "TASK_RESPONSE"
    COHERENCE_COHESION = "COHERENCE_COHESION"
    LEXICAL_RESOURCE = "LEXICAL_RESOURCE"
    GRAMMATICAL_RANGE_ACCURACY = "GRAMMATICAL_RANGE_ACCURACY"


def _validate_ielts_band_increment(v: float, field_name: str) -> float:
    """Validates that an IELTS band score is within [0.0, 9.0] and uses 0.5 increments."""
    if not (0.0 <= v <= 9.0):
        raise ValueError(f"{field_name} {v} must be within official IELTS range [0.0, 9.0]")
    if round(v * 2, 4) % 1.0 != 0.0:
        raise ValueError(
            f"{field_name} {v} must be in 0.5 step increments (e.g. 6.0, 6.5, 7.0)"
        )
    return v


class EssayMetrics(BaseModel):
    """Statistical and linguistic metrics of the submitted essay."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    totalWords: int = Field(..., description="Total word count in the essay")
    uniqueWords: int = Field(..., description="Number of unique words used")
    lexicalDiversityRatio: float = Field(
        ..., description="Ratio of unique words to total words (TTR)"
    )
    averageSentenceLength: float = Field(
        ..., description="Average number of words per sentence"
    )
    complexSentencesRatio: float = Field(
        ..., description="Proportion of sentences containing subordinate/relative clauses"
    )


class EnhancedOptions(BaseModel):
    """Band-targeted sentence rewrite alternatives."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    band7Option: str = Field(..., description="Sentence rewritten to target Band 7.0")
    band8Option: str = Field(..., description="Sentence rewritten to target Band 8.0+")


class SentenceCorrection(BaseModel):
    """Granular character-offset sentence error diagnostic and correction."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    startIndex: int = Field(..., description="0-indexed start character offset in original essay")
    endIndex: int = Field(..., description="0-indexed end character offset in original essay")
    originalSentence: str = Field(..., description="Verbatim original text span containing the issue")
    correctedSentence: str = Field(..., description="Minimum-reconstruction corrected sentence")
    errorType: CorrectionErrorType = Field(..., description="Category of error")
    severity: ErrorSeverity = Field(..., description="Severity level: MINOR, MAJOR, CRITICAL")
    explanation: str = Field(..., description="Pedagogical explanation in Vietnamese")
    enhancedOptions: Optional[EnhancedOptions] = Field(
        default=None, description="Optional Band 7/8 upgrade suggestions"
    )

    @field_validator("errorType", mode="before")
    @classmethod
    def normalize_error_type(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip().upper()
            mapping = {
                "SVA": CorrectionErrorType.GRAMMAR,
                "SUBJECT_VERB_AGREEMENT": CorrectionErrorType.GRAMMAR,
                "TENSE": CorrectionErrorType.GRAMMAR,
                "VERB_TENSE": CorrectionErrorType.GRAMMAR,
                "PREPOSITION": CorrectionErrorType.GRAMMAR,
                "ARTICLE": CorrectionErrorType.GRAMMAR,
                "SYNTAX": CorrectionErrorType.GRAMMAR,
                "WORD_CHOICE": CorrectionErrorType.VOCABULARY,
                "COLLOCATION": CorrectionErrorType.VOCABULARY,
                "LEXICAL": CorrectionErrorType.VOCABULARY,
                "LEXICAL_PRECISION": CorrectionErrorType.VOCABULARY,
                "SPELLING": CorrectionErrorType.SPELLING,
                "PUNCTUATION": CorrectionErrorType.PUNCTUATION,
                "COHESION": CorrectionErrorType.COHESION,
                "TASK_RESPONSE": CorrectionErrorType.TASK_RELEVANCE,
                "TASK_RELEVANCE": CorrectionErrorType.TASK_RELEVANCE,
                "OFF_TOPIC": CorrectionErrorType.TASK_RELEVANCE,
            }
            if v_clean in mapping:
                return mapping[v_clean]
        return v

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip().upper()
            mapping = {
                "LOW": ErrorSeverity.MINOR,
                "MEDIUM": ErrorSeverity.MAJOR,
                "HIGH": ErrorSeverity.MAJOR,
                "MINOR": ErrorSeverity.MINOR,
                "MAJOR": ErrorSeverity.MAJOR,
                "CRITICAL": ErrorSeverity.CRITICAL,
            }
            if v_clean in mapping:
                return mapping[v_clean]
        return v


class CohesiveDeviceAnalysis(BaseModel):
    """Discourse and coherence markers evaluation."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    usedDevices: List[str] = Field(
        default_factory=list, description="List of cohesive devices identified in the essay"
    )
    overusedOrRepetitive: List[str] = Field(
        default_factory=list, description="Connectors repeated excessively (ceiling indicator)"
    )
    suggestedTransitions: List[str] = Field(
        default_factory=list, description="Recommended alternative transition markers"
    )


class VocabularyUpgrade(BaseModel):
    """Contextual academic lexical enhancement suggestions."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    originalWord: str = Field(..., description="Original vocabulary term used by student")
    contextInEssay: str = Field(..., description="Sentence context where the word appeared")
    academicAlternatives: List[str] = Field(
        default_factory=list, description="More precise, natural academic alternatives"
    )
    recommendedCollocations: List[str] = Field(
        default_factory=list, description="High-frequency native collocations for the concept"
    )


class CriterionFeedback(BaseModel):
    """Individual IELTS criterion assessment."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    criterion: WritingCriterion = Field(..., description="Criterion identifier")
    score: float = Field(..., description="Criterion band score in 0.5 step increments")
    summary: str = Field(..., description="Detailed justification based on Cambridge descriptors")
    strengths: List[str] = Field(
        default_factory=list, description="Key strong points demonstrated in this criterion"
    )
    weaknesses: List[str] = Field(
        default_factory=list, description="Key limiting factors capping the score"
    )
    bandGapAnalysis: Optional[str] = Field(
        default=None, description="Actionable gap analysis to reach the next band level"
    )

    @field_validator("criterion", mode="before")
    @classmethod
    def normalize_criterion(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip().upper()
            mapping = {
                "TR": WritingCriterion.TASK_RESPONSE,
                "TA": WritingCriterion.TASK_ACHIEVEMENT,
                "CC": WritingCriterion.COHERENCE_COHESION,
                "LR": WritingCriterion.LEXICAL_RESOURCE,
                "GRA": WritingCriterion.GRAMMATICAL_RANGE_ACCURACY,
                "TASK_RESPONSE": WritingCriterion.TASK_RESPONSE,
                "TASK_ACHIEVEMENT": WritingCriterion.TASK_ACHIEVEMENT,
                "COHERENCE_COHESION": WritingCriterion.COHERENCE_COHESION,
                "LEXICAL_RESOURCE": WritingCriterion.LEXICAL_RESOURCE,
                "GRAMMATICAL_RANGE_ACCURACY": WritingCriterion.GRAMMATICAL_RANGE_ACCURACY,
            }
            if v_clean in mapping:
                return mapping[v_clean]
        return v

    @field_validator("score")
    @classmethod
    def validate_score(cls, v: float) -> float:
        return _validate_ielts_band_increment(v, "Criterion score")


class ImprovementTip(BaseModel):
    """High-priority targeted advice for student progression."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    category: str = Field(..., description="Target category or criterion")
    tipText: str = Field(..., description="Actionable advice in Vietnamese")
    targetBand: float = Field(..., description="Target IELTS band level for this tip")

    @field_validator("targetBand")
    @classmethod
    def validate_target_band(cls, v: float) -> float:
        return _validate_ielts_band_increment(v, "Target band")


class WritingFeedbackDetail(BaseModel):
    """Root structured feedback object for IELTS Writing submissions."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    examinerSummary: str = Field(
        ..., description="Overall assessment summary and high-level examiner commentary"
    )
    essayMetrics: EssayMetrics = Field(
        ..., description="Computed lexical and syntactic metrics"
    )
    criteria: List[CriterionFeedback] = Field(
        ..., description="Detailed breakdown for all 4 IELTS criteria"
    )
    corrections: List[SentenceCorrection] = Field(
        default_factory=list, description="Sequential list of sentence-level corrections"
    )
    cohesiveDeviceAnalysis: CohesiveDeviceAnalysis = Field(
        ..., description="Analysis of discourse markers and paragraph transitions"
    )
    vocabularyUpgrades: List[VocabularyUpgrade] = Field(
        default_factory=list, description="Lexical upgrades and collocation enhancements"
    )
    improvementTips: List[ImprovementTip] = Field(
        default_factory=list, description="Prioritized tips for student development"
    )
