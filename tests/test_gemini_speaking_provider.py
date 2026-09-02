"""
tests/test_gemini_speaking_provider.py
======================================
Comprehensive test suite for GeminiSpeakingProvider and authoritative Cambridge rounding.
Verifies short-circuit routing, circuit breaker integration, deterministic overall band recomputation,
and Cambridge rounding tie-breaks.
"""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock

from acoustic.phonetic_models import (
    FullAcousticAnalysisResult,
    IntonationAnalysis,
    WordStressAnalysis,
)
from providers.base import ProviderCallError
from providers.gemini_speaking_provider import GeminiSpeakingProvider
from providers.rounding import (
    calculate_overall_band,
    is_legal_band_value,
    round_to_nearest_half_band,
)


class TestGeminiSpeakingProvider(unittest.TestCase):

    def setUp(self):
        self.mock_gemini_client = AsyncMock()
        self.mock_circuit_breaker = MagicMock()
        self.mock_circuit_breaker.allow_request.return_value = True

        self.provider = GeminiSpeakingProvider(
            gemini_client=self.mock_gemini_client,
            circuit_breaker=self.mock_circuit_breaker,
        )

        self.sample_acoustic_result = FullAcousticAnalysisResult(
            speaking_rate_wpm=128.0,
            articulation_rate_wpm=145.0,
            phonation_ratio=0.72,
            total_duration_seconds=30.0,
            phonation_time_seconds=21.6,
            word_count=64,
            pause_analysis={"cognitive_pause_count": 4},
            phoneme_errors=[],
            word_stress_analysis=WordStressAnalysis(
                total_polysyllabic_words=10,
                correctly_stressed_words=8,
                stress_accuracy_ratio=0.80,
            ),
            intonation_analysis=IntonationAnalysis(
                pitch_range_hz=110.0,
                pitch_standard_deviation_hz=22.0,
                pitch_coefficient_of_variation=0.17,
                monotone_flag=False,
                dominant_contour_pattern="FALLING",
            ),
            excluded_from_automated_scoring=False,
            exclusion_reason=None,
        )

    def test_rounding_cambridge_rule_exact_ties(self):
        """
        Test 1: Cambridge half-band rounding rule with exact boundary values:
        - 6.125 -> 6.0
        - 6.25  -> 6.5
        - 6.375 -> 6.5
        - 6.625 -> 6.5
        - 6.75  -> 7.0
        - 6.875 -> 7.0
        """
        self.assertEqual(round_to_nearest_half_band(6.125), 6.0)
        self.assertEqual(round_to_nearest_half_band(6.25), 6.5)
        self.assertEqual(round_to_nearest_half_band(6.375), 6.5)
        self.assertEqual(round_to_nearest_half_band(6.625), 6.5)
        self.assertEqual(round_to_nearest_half_band(6.75), 7.0)
        self.assertEqual(round_to_nearest_half_band(6.875), 7.0)

        # Verify is_legal_band_value
        self.assertTrue(is_legal_band_value(0.0))
        self.assertTrue(is_legal_band_value(6.5))
        self.assertTrue(is_legal_band_value(9.0))
        self.assertTrue(is_legal_band_value("7.5"))
        self.assertFalse(is_legal_band_value(6.3))
        self.assertFalse(is_legal_band_value(9.5))
        self.assertFalse(is_legal_band_value(-0.5))
        self.assertFalse(is_legal_band_value("invalid"))

        # Verify calculate_overall_band across partial and full criteria
        self.assertEqual(calculate_overall_band(6.0, 6.5, 6.0, 6.5), 6.5)
        self.assertEqual(calculate_overall_band(None, 6.5, 6.0, None), 6.5)
        self.assertIsNone(calculate_overall_band(None, None, None, None))

    def test_speaking_evaluation_short_circuit_on_exclusion(self):
        """
        Test 2: When acoustic_result.excluded_from_automated_scoring is True,
        evaluate_speaking() MUST short-circuit immediately without calling the Gemini API.
        """
        excluded_acoustic = FullAcousticAnalysisResult(
            speaking_rate_wpm=45.0,
            articulation_rate_wpm=50.0,
            phonation_ratio=0.20,
            total_duration_seconds=15.0,
            phonation_time_seconds=3.0,
            word_count=12,
            pause_analysis={},
            phoneme_errors=[],
            word_stress_analysis=WordStressAnalysis(0, 0, 0.0),
            intonation_analysis=IntonationAnalysis(0.0, 0.0, 0.0, True, "FLAT"),
            excluded_from_automated_scoring=True,
            exclusion_reason="Severe audio dropout > 20%",
        )

        result = asyncio.run(
            self.provider.evaluate_speaking(
                question="Describe your hometown.",
                transcript="I live in a small town.",
                acoustic_result=excluded_acoustic,
                exam_part="PART1",
            )
        )

        # Gemini API must never be invoked
        self.assertEqual(self.mock_gemini_client.generate_content_async.call_count, 0)
        self.mock_circuit_breaker.allow_request.assert_not_called()

        # Result verification
        self.assertIsNone(result.overallBand)
        self.assertIsNone(result.fluencyCoherenceScore)
        self.assertIsNone(result.lexicalResourceScore)
        self.assertIsNone(result.grammaticalRangeScore)
        self.assertIsNone(result.pronunciationScore)
        self.assertTrue(result.requiresHumanReview)
        self.assertIn("Severe audio dropout > 20%", result.feedbackDetail.examinerSummary)
        self.assertEqual(len(result.feedbackDetail.criteria), 4)

    def test_speaking_evaluation_normal_flow_overwrites_overall_band(self):
        """
        Test 3: Normal evaluation flow invokes Gemini API and deterministically recomputes
        overall_band, overriding any erroneous arithmetic returned by the LLM.
        FC=6.0, LR=6.5, GRA=6.0, PR=6.5 -> Mean = 6.25 -> Cambridge Overall Band = 6.5.
        """
        llm_mock_payload = {
            "overallBand": 6.0,  # Erroneous calculation by LLM (should be 6.5)
            "fluencyCoherenceScore": 6.0,
            "lexicalResourceScore": 6.5,
            "grammaticalRangeScore": 6.0,
            "pronunciationScore": 6.5,
            "feedbackDetail": {
                "examinerSummary": "Thí sinh có bài nói tương đối tốt.",
                "speakingMetrics": {
                    "totalWords": 64,
                    "speakingRateWpm": 128.0,
                    "articulationRateWpm": 145.0,
                    "phonationRatio": 0.72,
                    "pauseCount": 4,
                    "totalPauseDurationSeconds": 2.1,
                    "stressAccuracyRatio": 0.80,
                    "pitchVariationCv": 0.17,
                    "monotoneFlag": False,
                    "dominantContour": "FALLING",
                },
                "criteria": [
                    {
                        "criterion": "FLUENCY_COHERENCE",
                        "score": 6.0,
                        "summary": "Tốc độ nói ổn định.",
                        "strengths": ["Lưu loát"],
                        "weaknesses": [],
                        "acousticGroundingNote": "Speaking rate 128 WPM.",
                    },
                    {
                        "criterion": "LEXICAL_RESOURCE",
                        "score": 6.5,
                        "summary": "Từ vựng tốt.",
                        "strengths": ["Từ vựng chính xác"],
                        "weaknesses": [],
                    },
                    {
                        "criterion": "GRAMMATICAL_RANGE_ACCURACY",
                        "score": 6.0,
                        "summary": "Ngữ pháp đạt yêu cầu.",
                        "strengths": ["Câu phức"],
                        "weaknesses": [],
                    },
                    {
                        "criterion": "PRONUNCIATION",
                        "score": 6.5,
                        "summary": "Phát âm rõ ràng.",
                        "strengths": ["Trọng âm chuẩn"],
                        "weaknesses": [],
                        "acousticGroundingNote": "Stress accuracy 80%.",
                    },
                ],
                "grammarCorrections": [],
                "phonemeDiagnostics": [],
                "vocabularyUpgrades": [],
                "improvementTips": [],
            },
        }

        mock_response = MagicMock()
        mock_response.text = json.dumps(llm_mock_payload)
        self.mock_gemini_client.generate_content_async = AsyncMock(return_value=mock_response)

        result = asyncio.run(
            self.provider.evaluate_speaking(
                question="Describe a memorable trip.",
                transcript="Last year I traveled to Da Nang with my family and it was wonderful.",
                acoustic_result=self.sample_acoustic_result,
                exam_part="PART2",
            )
        )

        # Gemini API must be called once
        self.assertEqual(self.mock_gemini_client.generate_content_async.call_count, 1)
        self.mock_circuit_breaker.allow_request.assert_called_once()
        self.mock_circuit_breaker.record_success.assert_called_once()

        # Overall band must be deterministically overridden to 6.5
        self.assertEqual(result.overallBand, 6.5)
        self.assertEqual(result.fluencyCoherenceScore, 6.0)
        self.assertEqual(result.lexicalResourceScore, 6.5)
        self.assertEqual(result.grammaticalRangeScore, 6.0)
        self.assertEqual(result.pronunciationScore, 6.5)
        self.assertFalse(result.requiresHumanReview)

    def test_circuit_breaker_rejection(self):
        """
        Test 4: When circuit breaker allow_request() returns False,
        evaluate_speaking() raises ProviderCallError immediately without invoking Gemini API.
        """
        self.mock_circuit_breaker.allow_request.return_value = False

        with self.assertRaises(ProviderCallError):
            asyncio.run(
                self.provider.evaluate_speaking(
                    question="Describe your favorite book.",
                    transcript="I really like reading science fiction novels.",
                    acoustic_result=self.sample_acoustic_result,
                    exam_part="PART1",
                )
            )

        self.assertEqual(self.mock_gemini_client.generate_content_async.call_count, 0)


if __name__ == "__main__":
    unittest.main()
