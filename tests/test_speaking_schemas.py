"""
tests/test_speaking_schemas.py
==============================
Unit tests for IELTS Speaking Pydantic v2 domain schemas, Decimal Cambridge rounding,
and bi-directional camelCase / snake_case serialization aliases.
"""

from decimal import Decimal
import unittest
from providers.schemas_speaking_additions import (
    SpeakingEvaluationResult,
    SpeakingFeedbackDetail,
    SpeakingCriterionFeedback,
    SpeakingMetrics,
    SpeakingCriterion,
    _validate_legal_band,
    cambridge_round,
)


class TestSpeakingSchemas(unittest.TestCase):

    def test_validate_legal_band_accepts_none_and_valid_bands(self):
        self.assertIsNone(_validate_legal_band(None))
        self.assertIsNone(_validate_legal_band("null"))
        self.assertIsNone(_validate_legal_band("None"))
        self.assertIsNone(_validate_legal_band(""))

        self.assertEqual(_validate_legal_band(6.5), 6.5)
        self.assertEqual(_validate_legal_band("7.0"), 7.0)
        self.assertEqual(_validate_legal_band(8), 8.0)
        self.assertEqual(_validate_legal_band(Decimal("7.5")), 7.5)

        with self.assertRaises(ValueError):
            _validate_legal_band(6.3)  # Invalid non-0.5 step

        with self.assertRaises(ValueError):
            _validate_legal_band(9.5)  # Out of range

        with self.assertRaises(ValueError):
            _validate_legal_band(-0.5)

    def test_cambridge_rounding_decimal_precision(self):
        """
        Tests exact Cambridge rounding boundary thresholds using Decimal arithmetic:
        - [x.00, x.24] -> x.0
        - [x.25, x.74] -> x.5
        - [x.75, x.99] -> (x+1).0
        """
        self.assertEqual(cambridge_round(6.0), 6.0)
        self.assertEqual(cambridge_round(6.125), 6.5)   # 6.125 -> 6.25 -> 6.5
        self.assertEqual(cambridge_round(6.25), 6.5)    # 6.25 -> 6.5
        self.assertEqual(cambridge_round(6.375), 6.5)   # 6.375 -> 6.5
        self.assertEqual(cambridge_round(6.5), 6.5)
        self.assertEqual(cambridge_round(6.625), 7.0)   # 6.625 -> 6.75 -> 7.0
        self.assertEqual(cambridge_round(6.75), 7.0)    # 6.75 -> 7.0
        self.assertEqual(cambridge_round(6.875), 7.0)   # 6.875 -> 7.0
        self.assertEqual(cambridge_round("7.25"), 7.5)
        self.assertEqual(cambridge_round(Decimal("7.75")), 8.0)

    def test_valid_speaking_evaluation_result_camel_case(self):
        payload = {
            "overallBand": 6.5,
            "fluencyCoherenceScore": 6.5,
            "lexicalResourceScore": 7.0,
            "grammaticalRangeScore": 6.0,
            "pronunciationScore": 6.5,
            "feedbackDetail": {
                "examinerSummary": "Bài nói tốt với sự lưu loát và từ vựng phong phú.",
                "speakingMetrics": {
                    "totalWords": 120,
                    "speakingRateWpm": 125.0,
                    "articulationRateWpm": 140.0,
                    "phonationRatio": 0.70,
                    "pauseCount": 6,
                    "totalPauseDurationSeconds": 3.5,
                    "stressAccuracyRatio": 0.80,
                    "pitchVariationCv": 0.17,
                    "monotoneFlag": False,
                    "dominantContour": "FALLING",
                },
                "criteria": [
                    {
                        "criterion": "FLUENCY_COHERENCE",
                        "score": 6.5,
                        "summary": "Tốc độ nói ổn định.",
                        "strengths": ["Lưu loát"],
                        "weaknesses": ["Ngập ngừng nhẹ"],
                        "acousticGroundingNote": "Speaking rate 125 WPM.",
                    },
                    {
                        "criterion": "LEXICAL_RESOURCE",
                        "score": 7.0,
                        "summary": "Từ vựng đa dạng.",
                        "strengths": ["Collocations tự nhiên"],
                        "weaknesses": [],
                    },
                    {
                        "criterion": "GRAMMATICAL_RANGE_ACCURACY",
                        "score": 6.0,
                        "summary": "Cấu trúc câu đa dạng.",
                        "strengths": ["Mệnh đề quan hệ"],
                        "weaknesses": ["Lỗi thì quá khứ"],
                    },
                    {
                        "criterion": "PRONUNCIATION",
                        "score": 6.5,
                        "summary": "Phát âm rõ ràng.",
                        "strengths": ["Trọng âm chuẩn"],
                        "weaknesses": ["Âm đuôi /θ/"],
                        "acousticGroundingNote": "Stress accuracy 80%.",
                    },
                ],
                "grammarCorrections": [
                    {
                        "startIndex": 5,
                        "endIndex": 20,
                        "originalUtterance": "she have a car",
                        "correctedUtterance": "she has a car",
                        "errorType": "SUBJECT_VERB_AGREEMENT",
                        "severity": "MAJOR",
                        "explanation": "Chủ ngữ 'she' đi với 'has'.",
                    }
                ],
                "phonemeDiagnostics": [
                    {
                        "word": "think",
                        "expectedPhonemeIpa": "θ",
                        "producedPhonemeIpa": "s",
                        "errorType": "SUBSTITUTION",
                        "gopScore": 0.55,
                        "feedback": "Phát âm âm /θ/ thay vì /s/.",
                    }
                ],
                "vocabularyUpgrades": [
                    {
                        "originalWordOrPhrase": "very good",
                        "contextInSpeech": "it was very good",
                        "upgradedAlternatives": ["exceptional", "outstanding"],
                        "collocationNotes": "Tăng tính học thuật.",
                    }
                ],
                "improvementTips": [
                    {
                        "criterion": "FLUENCY_COHERENCE",
                        "tipText": "Tập shadowing hàng ngày.",
                        "targetBand": 7.0,
                    }
                ],
            },
        }

        result = SpeakingEvaluationResult.model_validate(payload)
        self.assertEqual(result.overallBand, 6.5)
        self.assertEqual(result.fluencyCoherenceScore, 6.5)
        self.assertEqual(result.lexicalResourceScore, 7.0)
        self.assertFalse(result.requiresHumanReview)
        self.assertEqual(len(result.feedbackDetail.grammarCorrections), 1)

    def test_valid_speaking_evaluation_result_snake_case(self):
        """
        Verifies that full snake_case JSON from external services parses seamlessly
        without validation errors due to populate_by_name=True and aliases.
        """
        payload = {
            "overall_band": 7.0,
            "fluency_coherence_score": 7.0,
            "lexical_resource_score": 7.0,
            "grammatical_range_score": 7.0,
            "pronunciation_score": 7.0,
            "evaluated_by": "AI_AUTO",
            "requires_human_review": False,
            "feedback_detail": {
                "examiner_summary": "Thí sinh có khả năng diễn đạt lưu loát.",
                "speaking_metrics": {
                    "total_words": 150,
                    "speaking_rate_wpm": 135.0,
                    "articulation_rate_wpm": 155.0,
                    "phonation_ratio": 0.75,
                    "pause_count": 5,
                    "total_pause_duration_seconds": 2.5,
                    "stress_accuracy_ratio": 0.85,
                    "pitch_variation_cv": 0.18,
                    "monotone_flag": False,
                    "dominant_contour": "FALLING",
                },
                "criteria": [
                    {
                        "criterion": "FLUENCY_COHERENCE",
                        "score": 7.0,
                        "summary": "Lưu loát tốt.",
                        "strengths": ["Tự nhiên"],
                        "weaknesses": [],
                        "acoustic_grounding_note": "Speaking rate 135 WPM",
                        "band_gap_analysis": "Luyện mở rộng câu",
                    },
                    {
                        "criterion": "LEXICAL_RESOURCE",
                        "score": 7.0,
                        "summary": "Từ vựng tốt.",
                        "strengths": ["Từ vựng phong phú"],
                        "weaknesses": [],
                    },
                    {
                        "criterion": "GRAMMATICAL_RANGE_ACCURACY",
                        "score": 7.0,
                        "summary": "Ngữ pháp chính xác.",
                        "strengths": ["Ít lỗi ngữ pháp"],
                        "weaknesses": [],
                    },
                    {
                        "criterion": "PRONUNCIATION",
                        "score": 7.0,
                        "summary": "Phát âm rõ ràng.",
                        "strengths": ["Trọng âm chuẩn"],
                        "weaknesses": [],
                        "acoustic_grounding_note": "Stress ratio 85%",
                    },
                ],
                "grammar_corrections": [
                    {
                        "start_index": 0,
                        "end_index": 10,
                        "original_utterance": "I is happy",
                        "corrected_utterance": "I am happy",
                        "error_type": "TENSE",
                        "severity": "MAJOR",
                        "explanation": "Động từ to be đi với I là am.",
                        "better_alternative": "I feel delighted",
                    }
                ],
                "phoneme_diagnostics": [
                    {
                        "word": "water",
                        "expected_phoneme_ipa": "w",
                        "produced_phoneme_ipa": "v",
                        "error_type": "SUBSTITUTION",
                        "gop_score": 0.60,
                        "feedback": "Phát âm âm /w/.",
                    }
                ],
                "vocabulary_upgrades": [
                    {
                        "original_word_or_phrase": "big problem",
                        "context_in_speech": "this is a big problem",
                        "upgraded_alternatives": ["pressing challenge", "formidable issue"],
                        "collocation_notes": "Sử dụng từ nâng cao.",
                    }
                ],
                "improvement_tips": [
                    {
                        "criterion": "PRONUNCIATION",
                        "tip_text": "Tập phát âm chuẩn nguyên âm đôi.",
                        "target_band": 7.5,
                    }
                ],
            },
        }

        result = SpeakingEvaluationResult.model_validate(payload)
        self.assertEqual(result.overallBand, 7.0)
        self.assertEqual(result.fluencyCoherenceScore, 7.0)
        self.assertEqual(result.feedbackDetail.speakingMetrics.totalWords, 150)
        self.assertEqual(len(result.feedbackDetail.grammarCorrections), 1)
        self.assertEqual(result.feedbackDetail.grammarCorrections[0].startIndex, 0)
        self.assertEqual(result.feedbackDetail.phonemeDiagnostics[0].expectedPhonemeIpa, "w")

    def test_fault_tolerant_acoustic_exclusion_with_null_scores(self):
        """
        Verifies that when FC and PR are null due to acoustic exclusion,
        the schema parses without raising ValidationError, computes overall band from
        available criteria (LR, GRA), and sets requiresHumanReview to True.
        """
        payload = {
            "overall_band": None,
            "fluency_coherence_score": None,
            "lexical_resource_score": 6.5,
            "grammatical_range_score": 6.0,
            "pronunciation_score": None,
            "feedback_detail": {
                "examiner_summary": "Acoustic exclusion: Audio dropped out due to network issue.",
                "speaking_metrics": {
                    "total_words": 85,
                },
                "criteria": [
                    {
                        "criterion": "FLUENCY_COHERENCE",
                        "score": None,
                        "summary": "Excluded due to technical audio dropout.",
                        "strengths": [],
                        "weaknesses": [],
                        "acoustic_grounding_note": "Excluded: technical dropout > 15%",
                    },
                    {
                        "criterion": "LEXICAL_RESOURCE",
                        "score": 6.5,
                        "summary": "Good vocabulary range.",
                        "strengths": ["Natural collocations"],
                        "weaknesses": [],
                    },
                    {
                        "criterion": "GRAMMATICAL_RANGE_ACCURACY",
                        "score": 6.0,
                        "summary": "Good grammatical range.",
                        "strengths": ["Compound sentences"],
                        "weaknesses": [],
                    },
                    {
                        "criterion": "PRONUNCIATION",
                        "score": None,
                        "summary": "Excluded due to technical audio dropout.",
                        "strengths": [],
                        "weaknesses": [],
                        "acoustic_grounding_note": "Excluded: technical dropout > 15%",
                    },
                ],
            },
        }

        result = SpeakingEvaluationResult.model_validate(payload)
        self.assertIsNone(result.fluencyCoherenceScore)
        self.assertIsNone(result.pronunciationScore)
        self.assertEqual(result.lexicalResourceScore, 6.5)
        self.assertEqual(result.grammaticalRangeScore, 6.0)
        # Average of 6.5 and 6.0 is 6.25 -> Cambridge round (6.25 -> 6.5)
        self.assertEqual(result.overallBand, 6.5)
        self.assertTrue(result.requiresHumanReview)


if __name__ == "__main__":
    unittest.main()
