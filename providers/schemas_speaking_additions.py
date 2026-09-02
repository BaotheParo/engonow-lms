"""
providers/schemas_speaking_additions.py
=======================================
Pydantic v2 domain schemas for IELTS Speaking multi-modal AI evaluation and diagnostics.
Includes fault-tolerant null handling for acoustic exclusion, strict Cambridge Decimal band validation,
and dual camelCase / snake_case serialization aliases for seamless Java Core LMS inter-op.
"""

from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ExamPart(str, Enum):
    """IELTS Speaking test part identifier."""
    PART_1 = "PART_1"
    PART_2 = "PART_2"
    PART_3 = "PART_3"


class SpeakingCriterion(str, Enum):
    """Official IELTS Speaking assessment criteria."""
    FLUENCY_COHERENCE = "FLUENCY_COHERENCE"
    LEXICAL_RESOURCE = "LEXICAL_RESOURCE"
    GRAMMATICAL_RANGE_ACCURACY = "GRAMMATICAL_RANGE_ACCURACY"
    PRONUNCIATION = "PRONUNCIATION"


class SpeakingGrammarErrorType(str, Enum):
    """Taxonomy used to classify spoken grammatical errors."""
    TENSE = "TENSE"
    SUBJECT_VERB_AGREEMENT = "SUBJECT_VERB_AGREEMENT"
    ARTICLE = "ARTICLE"
    PREPOSITION = "PREPOSITION"
    WORD_ORDER = "WORD_ORDER"
    CLAUSE_STRUCTURE = "CLAUSE_STRUCTURE"
    PRONOUN = "PRONOUN"
    PLURALITY = "PLURALITY"
    OTHER = "OTHER"


class ErrorSeverity(str, Enum):
    """Pedagogical impact of a detected error."""
    MINOR = "MINOR"
    MAJOR = "MAJOR"
    CRITICAL = "CRITICAL"


class PhonemeErrorType(str, Enum):
    """Goodness-of-Pronunciation (GOP) phoneme error classification."""
    SUBSTITUTION = "SUBSTITUTION"
    DELETION = "DELETION"
    INSERTION = "INSERTION"


class ContourPattern(str, Enum):
    """Acoustic pitch (F0) intonation contour classification."""
    FALLING = "FALLING"
    RISING = "RISING"
    MIXED = "MIXED"
    FLAT = "FLAT"


def _validate_legal_band(v: Any, field_name: str = "Band score") -> Optional[float]:
    """
    Validates that an IELTS band score is within [0.0, 9.0] and uses 0.5 increments.
    Gracefully accepts None and returns None to support acoustic exclusions.
    """
    if v is None:
        return None

    if isinstance(v, str):
        v_clean = v.strip()
        if v_clean.lower() in ("null", "none", "", "n/a", "undefined"):
            return None
        try:
            v = float(v_clean)
        except ValueError:
            raise ValueError(f"{field_name} '{v}' could not be parsed as a float")

    if isinstance(v, (int, float, Decimal)):
        v_float = float(v)
        if math.isnan(v_float):
            return None
        if not (0.0 <= v_float <= 9.0):
            raise ValueError(f"{field_name} {v_float} must be within official IELTS range [0.0, 9.0]")
        if round(v_float * 2, 4) % 1.0 != 0.0:
            raise ValueError(
                f"{field_name} {v_float} must be in 0.5 step increments (e.g. 6.0, 6.5, 7.0)"
            )
        return v_float

    raise ValueError(f"{field_name} must be a float, integer, Decimal, or None; received {type(v)}")


def cambridge_round(mean_score: Union[float, int, Decimal, str]) -> float:
    """
    Applies official Cambridge IELTS rounding using decimal arithmetic to prevent
    floating-point precision issues at boundary points (.25, .75, .125, .625, .875).
    - Rounds to nearest quarter band (0.25).
    - Promotes .25 and .75 boundaries to next half or whole band (.50 or 1.0).
    """
    if mean_score is None:
        raise ValueError("mean_score cannot be None for Cambridge rounding")

    m = Decimal(str(mean_score))
    quarter = Decimal("0.25")
    three_quarter = Decimal("0.75")
    one = Decimal("1.0")

    # Round to nearest quarter band via ROUND_HALF_UP
    rounded_to_quarter = (m / quarter).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * quarter
    if rounded_to_quarter < Decimal("0.0"):
        return 0.0
    if rounded_to_quarter > Decimal("9.0"):
        return 9.0

    decimal_part = rounded_to_quarter % one
    if decimal_part == quarter or decimal_part == three_quarter:
        rounded_band = rounded_to_quarter + quarter
    else:
        rounded_band = rounded_to_quarter

    res = min(Decimal("9.0"), max(Decimal("0.0"), rounded_band))
    return float(res.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


class SpeakingMetrics(BaseModel):
    """Acoustic and speech fluency measurements computed from raw audio."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    totalWords: int = Field(
        ...,
        alias="total_words",
        description="Total word count in spoken transcript"
    )
    speakingRateWpm: Optional[float] = Field(
        default=None,
        alias="speaking_rate_wpm",
        description="Speaking rate in words per minute (including pauses)"
    )
    articulationRateWpm: Optional[float] = Field(
        default=None,
        alias="articulation_rate_wpm",
        description="Articulation rate in words per minute (excluding pauses)"
    )
    phonationRatio: Optional[float] = Field(
        default=None,
        alias="phonation_ratio",
        description="Ratio of phonation time to total duration [0.0, 1.0]"
    )
    pauseCount: Optional[int] = Field(
        default=None,
        alias="pause_count",
        description="Total count of cognitive and hesitation pauses"
    )
    totalPauseDurationSeconds: Optional[float] = Field(
        default=None,
        alias="total_pause_duration_seconds",
        description="Aggregate pause duration in seconds"
    )
    stressAccuracyRatio: Optional[float] = Field(
        default=None,
        alias="stress_accuracy_ratio",
        description="Ratio of correctly stressed polysyllabic words [0.0, 1.0]"
    )
    pitchVariationCv: Optional[float] = Field(
        default=None,
        alias="pitch_variation_cv",
        description="Speaker-normalized pitch coefficient of variation std(F0)/median(F0)"
    )
    monotoneFlag: Optional[bool] = Field(
        default=None,
        alias="monotone_flag",
        description="Flag indicating restricted pitch range (CV < 0.12)"
    )
    dominantContour: Optional[ContourPattern] = Field(
        default=None,
        alias="dominant_contour",
        description="Dominant intonation contour pattern"
    )

    @field_validator("dominantContour", mode="before")
    @classmethod
    def normalize_contour(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip().upper()
            if v_clean in ContourPattern.__members__:
                return ContourPattern(v_clean)
        return v


class SpeakingGrammarCorrection(BaseModel):
    """Spoken utterance grammar diagnostic and minimal correction."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    startIndex: int = Field(
        ...,
        alias="start_index",
        description="0-indexed start character offset in transcript"
    )
    endIndex: int = Field(
        ...,
        alias="end_index",
        description="0-indexed end character offset in transcript"
    )
    originalUtterance: str = Field(
        ...,
        alias="original_utterance",
        description="Verbatim spoken transcript span containing error"
    )
    correctedUtterance: str = Field(
        ...,
        alias="corrected_utterance",
        description="Minimum-reconstruction corrected utterance"
    )
    errorType: SpeakingGrammarErrorType = Field(
        ...,
        alias="error_type",
        description="Grammatical error classification"
    )
    severity: ErrorSeverity = Field(
        ...,
        description="Pedagogical error severity: MINOR, MAJOR, CRITICAL"
    )
    explanation: str = Field(
        ...,
        description="Pedagogical explanation in Vietnamese"
    )
    betterAlternative: Optional[str] = Field(
        default=None,
        alias="better_alternative",
        description="Natural native spoken English upgrade"
    )

    @property
    def original_utterance(self) -> str:
        return self.originalUtterance

    @property
    def corrected_utterance(self) -> str:
        return self.correctedUtterance

    @property
    def error_type(self) -> SpeakingGrammarErrorType:
        return self.errorType

    @property
    def better_alternative(self) -> Optional[str]:
        return self.betterAlternative

    @field_validator("errorType", mode="before")
    @classmethod
    def normalize_error_type(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip().upper()
            mapping = {
                "TENSE": SpeakingGrammarErrorType.TENSE,
                "VERB_TENSE": SpeakingGrammarErrorType.TENSE,
                "SVA": SpeakingGrammarErrorType.SUBJECT_VERB_AGREEMENT,
                "SUBJECT_VERB_AGREEMENT": SpeakingGrammarErrorType.SUBJECT_VERB_AGREEMENT,
                "ARTICLE": SpeakingGrammarErrorType.ARTICLE,
                "PREPOSITION": SpeakingGrammarErrorType.PREPOSITION,
                "WORD_ORDER": SpeakingGrammarErrorType.WORD_ORDER,
                "SYNTAX": SpeakingGrammarErrorType.CLAUSE_STRUCTURE,
                "CLAUSE_STRUCTURE": SpeakingGrammarErrorType.CLAUSE_STRUCTURE,
                "PRONOUN": SpeakingGrammarErrorType.PRONOUN,
                "PLURALITY": SpeakingGrammarErrorType.PLURALITY,
            }
            if v_clean in mapping:
                return mapping[v_clean]
            return SpeakingGrammarErrorType.OTHER
        return v

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip().upper()
            mapping = {
                "LOW": ErrorSeverity.MINOR,
                "MINOR": ErrorSeverity.MINOR,
                "MEDIUM": ErrorSeverity.MAJOR,
                "MAJOR": ErrorSeverity.MAJOR,
                "HIGH": ErrorSeverity.CRITICAL,
                "CRITICAL": ErrorSeverity.CRITICAL,
                "NONE": ErrorSeverity.MINOR,
                "TRIVIAL": ErrorSeverity.MINOR,
                "INFO": ErrorSeverity.MINOR,
            }
            if v_clean in mapping:
                return mapping[v_clean]
            return ErrorSeverity.MINOR
        return v or ErrorSeverity.MINOR


class PhonemeDiagnostic(BaseModel):
    """Phonetic-level pronunciation diagnostic and GOP score."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    word: str = Field(..., description="Word containing the phoneme issue")
    expectedPhonemeIpa: str = Field(
        ...,
        alias="expected_phoneme_ipa",
        description="Canonical target IPA phoneme symbol"
    )
    producedPhonemeIpa: Optional[str] = Field(
        default=None,
        alias="produced_phoneme_ipa",
        description="Acoustically detected IPA phoneme symbol (None if DELETION)"
    )
    errorType: PhonemeErrorType = Field(
        ...,
        alias="error_type",
        description="Phoneme error type: SUBSTITUTION, DELETION, INSERTION"
    )
    gopScore: Optional[float] = Field(
        default=None,
        alias="gop_score",
        description="Goodness-of-Pronunciation posterior score bounded [0.0, 1.0]"
    )
    feedback: str = Field(..., description="Targeted articulatory pronunciation guidance in Vietnamese")

    @field_validator("errorType", mode="before")
    @classmethod
    def normalize_error_type(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip().upper()
            if v_clean in PhonemeErrorType.__members__:
                return PhonemeErrorType(v_clean)
        return v


class SpeakingVocabularyUpgrade(BaseModel):
    """Contextual spoken lexical enhancement and collocation suggestions."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    originalWordOrPhrase: str = Field(
        ...,
        alias="original_word_or_phrase",
        description="Original vocabulary term used by student"
    )
    contextInSpeech: str = Field(
        ...,
        alias="context_in_speech",
        description="Spoken context where the term appeared"
    )
    upgradedAlternatives: List[str] = Field(
        default_factory=list,
        alias="upgraded_alternatives",
        description="More idiomatic, precise spoken alternatives"
    )
    collocationNotes: Optional[str] = Field(
        default=None,
        alias="collocation_notes",
        description="Natural spoken collocations and register notes in Vietnamese"
    )

    @property
    def original_word_or_phrase(self) -> str:
        return self.originalWordOrPhrase

    @property
    def context_in_speech(self) -> str:
        return self.contextInSpeech

    @property
    def upgraded_alternatives(self) -> List[str]:
        return self.upgradedAlternatives

    @property
    def collocation_notes(self) -> Optional[str]:
        return self.collocationNotes


class SpeakingImprovementTip(BaseModel):
    """Actionable targeted advice for speaking score progression."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    criterion: SpeakingCriterion = Field(..., description="Target assessment criterion")
    tipText: str = Field(
        ...,
        alias="tip_text",
        description="Actionable practice technique in Vietnamese"
    )
    targetBand: Optional[float] = Field(
        default=None,
        alias="target_band",
        description="Target IELTS band level for this tip"
    )

    @property
    def tip_text(self) -> str:
        return self.tipText

    @property
    def target_band(self) -> Optional[float]:
        return self.targetBand

    @property
    def category(self) -> str:
        return self.criterion.value if hasattr(self.criterion, "value") else str(self.criterion)

    @field_validator("criterion", mode="before")
    @classmethod
    def normalize_criterion(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip().upper()
            mapping = {
                "FC": SpeakingCriterion.FLUENCY_COHERENCE,
                "FLUENCY_COHERENCE": SpeakingCriterion.FLUENCY_COHERENCE,
                "LR": SpeakingCriterion.LEXICAL_RESOURCE,
                "LEXICAL_RESOURCE": SpeakingCriterion.LEXICAL_RESOURCE,
                "GRA": SpeakingCriterion.GRAMMATICAL_RANGE_ACCURACY,
                "GRAMMATICAL_RANGE_ACCURACY": SpeakingCriterion.GRAMMATICAL_RANGE_ACCURACY,
                "PR": SpeakingCriterion.PRONUNCIATION,
                "PRONUNCIATION": SpeakingCriterion.PRONUNCIATION,
            }
            if v_clean in mapping:
                return mapping[v_clean]
        return v

    @field_validator("targetBand", mode="before")
    @classmethod
    def validate_target_band(cls, v: Any) -> Optional[float]:
        return _validate_legal_band(v, "Target band")


class SpeakingCriterionFeedback(BaseModel):
    """Individual IELTS Speaking criterion evaluation."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    criterion: SpeakingCriterion = Field(..., description="Criterion identifier")
    score: Optional[float] = Field(
        default=None,
        description="Criterion band score in 0.5 step increments, or None if acoustic exclusion"
    )
    summary: str = Field(..., description="Detailed justification based on Cambridge descriptors")
    strengths: List[str] = Field(
        default_factory=list, description="Key strong points demonstrated in this criterion"
    )
    weaknesses: List[str] = Field(
        default_factory=list, description="Key limiting factors capping the score"
    )
    acousticGroundingNote: Optional[str] = Field(
        default=None,
        alias="acoustic_grounding_note",
        description="Explicit acoustic measurement justification (required for FC and PR)"
    )
    bandGapAnalysis: Optional[str] = Field(
        default=None,
        alias="band_gap_analysis",
        description="Actionable gap analysis to reach the next band level"
    )

    @property
    def acoustic_grounding_note(self) -> Optional[str]:
        return self.acousticGroundingNote

    @property
    def band_gap_analysis(self) -> Optional[str]:
        return self.bandGapAnalysis

    @field_validator("criterion", mode="before")
    @classmethod
    def normalize_criterion(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip().upper()
            mapping = {
                "FC": SpeakingCriterion.FLUENCY_COHERENCE,
                "FLUENCY": SpeakingCriterion.FLUENCY_COHERENCE,
                "FLUENCY_COHERENCE": SpeakingCriterion.FLUENCY_COHERENCE,
                "LR": SpeakingCriterion.LEXICAL_RESOURCE,
                "VOCABULARY": SpeakingCriterion.LEXICAL_RESOURCE,
                "LEXICAL_RESOURCE": SpeakingCriterion.LEXICAL_RESOURCE,
                "GRA": SpeakingCriterion.GRAMMATICAL_RANGE_ACCURACY,
                "GRAMMAR": SpeakingCriterion.GRAMMATICAL_RANGE_ACCURACY,
                "GRAMMATICAL_RANGE_ACCURACY": SpeakingCriterion.GRAMMATICAL_RANGE_ACCURACY,
                "PR": SpeakingCriterion.PRONUNCIATION,
                "PRONUNCIATION": SpeakingCriterion.PRONUNCIATION,
            }
            if v_clean in mapping:
                return mapping[v_clean]
        return v

    @field_validator("score", mode="before")
    @classmethod
    def validate_score(cls, v: Any) -> Optional[float]:
        return _validate_legal_band(v, "Criterion score")


class SpeakingFeedbackDetail(BaseModel):
    """Root structured diagnostic feedback object for IELTS Speaking attempts."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    examinerSummary: str = Field(
        ...,
        alias="examiner_summary",
        description="Overall assessment summary and high-level examiner commentary in Vietnamese"
    )
    speakingMetrics: SpeakingMetrics = Field(
        ...,
        alias="speaking_metrics",
        description="Computed acoustic and temporal speech metrics"
    )
    criteria: List[SpeakingCriterionFeedback] = Field(
        ..., description="Detailed breakdown for all 4 IELTS Speaking criteria"
    )
    grammarCorrections: List[SpeakingGrammarCorrection] = Field(
        default_factory=list,
        alias="grammar_corrections",
        description="Sequential list of spoken grammar corrections"
    )
    phonemeDiagnostics: List[PhonemeDiagnostic] = Field(
        default_factory=list,
        alias="phoneme_diagnostics",
        description="Phonetic-level error diagnostics and GOP scores"
    )
    vocabularyUpgrades: List[SpeakingVocabularyUpgrade] = Field(
        default_factory=list,
        alias="vocabulary_upgrades",
        description="Spoken vocabulary upgrades and natural collocations"
    )
    improvementTips: List[SpeakingImprovementTip] = Field(
        default_factory=list,
        alias="improvement_tips",
        description="Prioritized tips for student development"
    )

    @field_validator("criteria")
    @classmethod
    def validate_criteria_completeness(
        cls, criteria_list: List[SpeakingCriterionFeedback]
    ) -> List[SpeakingCriterionFeedback]:
        seen = set()
        for item in criteria_list:
            if item.criterion in seen:
                raise ValueError(f"Duplicate criterion '{item.criterion}' found in criteria list")
            seen.add(item.criterion)

        expected = {
            SpeakingCriterion.FLUENCY_COHERENCE,
            SpeakingCriterion.LEXICAL_RESOURCE,
            SpeakingCriterion.GRAMMATICAL_RANGE_ACCURACY,
            SpeakingCriterion.PRONUNCIATION,
        }
        missing = expected - seen
        if missing:
            raise ValueError(f"Missing required IELTS Speaking criteria: {[m.value for m in missing]}")

        return criteria_list

    @property
    def examiner_summary(self) -> str:
        return self.examinerSummary

    @property
    def speaking_metrics(self) -> SpeakingMetrics:
        return self.speakingMetrics

    @property
    def grammar_corrections(self) -> List[SpeakingGrammarCorrection]:
        return self.grammarCorrections

    @property
    def phoneme_diagnostics(self) -> List[PhonemeDiagnostic]:
        return self.phonemeDiagnostics

    @property
    def vocabulary_upgrades(self) -> List[SpeakingVocabularyUpgrade]:
        return self.vocabularyUpgrades

    @property
    def improvement_tips(self) -> List[SpeakingImprovementTip]:
        return self.improvementTips


class SpeakingEvaluationResult(BaseModel):
    """
    Top-level evaluation result container for IELTS Speaking assessment.
    Provides fault-tolerant support for acoustic exclusions, strict Decimal Cambridge rounding,
    and bi-directional camelCase / snake_case field mapping.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    overallBand: Optional[float] = Field(
        default=None,
        alias="overall_band",
        description="Official IELTS Overall Band score rounded to nearest 0.5, or None if uncalibrated",
    )
    fluencyCoherenceScore: Optional[float] = Field(
        default=None,
        alias="fluency_coherence_score",
        description="Fluency and Coherence band score (or None if excluded)",
    )
    lexicalResourceScore: Optional[float] = Field(
        default=None,
        alias="lexical_resource_score",
        description="Lexical Resource band score",
    )
    grammaticalRangeScore: Optional[float] = Field(
        default=None,
        alias="grammatical_range_score",
        description="Grammatical Range and Accuracy band score",
    )
    pronunciationScore: Optional[float] = Field(
        default=None,
        alias="pronunciation_score",
        description="Pronunciation band score (or None if excluded)",
    )
    feedbackDetail: SpeakingFeedbackDetail = Field(
        ...,
        alias="feedback_detail",
        description="Detailed diagnostic feedback payload",
    )
    evaluatedBy: str = Field(
        default="AI_AUTO",
        alias="evaluated_by",
        description="Evaluation entity: AI_AUTO, AI_AUTO_UNCALIBRATED, HUMAN_EXAMINER",
    )
    requiresHumanReview: bool = Field(
        default=False,
        alias="requires_human_review",
        description="Flag indicating if the attempt requires human examiner adjudication",
    )

    @property
    def overall_band(self) -> Optional[float]:
        return self.overallBand

    @overall_band.setter
    def overall_band(self, value: Optional[float]) -> None:
        self.overallBand = value

    @property
    def fluency_coherence_score(self) -> Optional[float]:
        return self.fluencyCoherenceScore

    @property
    def lexical_resource_score(self) -> Optional[float]:
        return self.lexicalResourceScore

    @property
    def grammatical_range_score(self) -> Optional[float]:
        return self.grammaticalRangeScore

    @property
    def pronunciation_score(self) -> Optional[float]:
        return self.pronunciationScore

    @property
    def feedback_detail(self) -> SpeakingFeedbackDetail:
        return self.feedbackDetail

    @property
    def evaluated_by(self) -> str:
        return self.evaluatedBy

    @property
    def requires_human_review(self) -> bool:
        return self.requiresHumanReview

    @field_validator(
        "overallBand",
        "fluencyCoherenceScore",
        "lexicalResourceScore",
        "grammaticalRangeScore",
        "pronunciationScore",
        mode="before",
    )
    @classmethod
    def validate_bands(cls, v: Any) -> Optional[float]:
        return _validate_legal_band(v)

    @model_validator(mode="after")
    def sync_and_validate_scores(self) -> "SpeakingEvaluationResult":
        """
        Synchronizes top-level criterion scores with feedbackDetail.criteria and
        ensures overallBand is mathematically consistent with Cambridge Decimal rounding rules.
        """
        criteria_map: Dict[SpeakingCriterion, Optional[float]] = {
            item.criterion: item.score for item in self.feedbackDetail.criteria
        }

        # Sync top-level fields from criteria if top-level was None
        if self.fluencyCoherenceScore is None:
            self.fluencyCoherenceScore = criteria_map.get(SpeakingCriterion.FLUENCY_COHERENCE)
        if self.lexicalResourceScore is None:
            self.lexicalResourceScore = criteria_map.get(SpeakingCriterion.LEXICAL_RESOURCE)
        if self.grammaticalRangeScore is None:
            self.grammaticalRangeScore = criteria_map.get(SpeakingCriterion.GRAMMATICAL_RANGE_ACCURACY)
        if self.pronunciationScore is None:
            self.pronunciationScore = criteria_map.get(SpeakingCriterion.PRONUNCIATION)

        # Cross-validate top-level with criteria items when both are specified
        for item in self.feedbackDetail.criteria:
            if item.criterion == SpeakingCriterion.FLUENCY_COHERENCE:
                if self.fluencyCoherenceScore is not None and item.score is not None:
                    if abs(self.fluencyCoherenceScore - item.score) > 1e-4:
                        item.score = self.fluencyCoherenceScore
            elif item.criterion == SpeakingCriterion.LEXICAL_RESOURCE:
                if self.lexicalResourceScore is not None and item.score is not None:
                    if abs(self.lexicalResourceScore - item.score) > 1e-4:
                        item.score = self.lexicalResourceScore
            elif item.criterion == SpeakingCriterion.GRAMMATICAL_RANGE_ACCURACY:
                if self.grammaticalRangeScore is not None and item.score is not None:
                    if abs(self.grammaticalRangeScore - item.score) > 1e-4:
                        item.score = self.grammaticalRangeScore
            elif item.criterion == SpeakingCriterion.PRONUNCIATION:
                if self.pronunciationScore is not None and item.score is not None:
                    if abs(self.pronunciationScore - item.score) > 1e-4:
                        item.score = self.pronunciationScore

        # Auto-compute or verify overall band based on available scorable criteria via Decimal rounding
        valid_scores = [
            s
            for s in [
                self.fluencyCoherenceScore,
                self.lexicalResourceScore,
                self.grammaticalRangeScore,
                self.pronunciationScore,
            ]
            if s is not None
        ]

        if valid_scores:
            computed_mean = sum(valid_scores) / len(valid_scores)
            expected_overall = cambridge_round(computed_mean)
            if self.overallBand is None:
                self.overallBand = expected_overall
        else:
            self.overallBand = None

        # Flag human review if acoustic exclusion occurred
        if self.fluencyCoherenceScore is None or self.pronunciationScore is None:
            self.requiresHumanReview = True

        return self
