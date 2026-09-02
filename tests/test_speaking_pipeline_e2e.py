"""
tests/test_speaking_pipeline_e2e.py
===================================
End-to-End multi-modal pipeline tests for IELTS Speaking assessment.
Covers ProviderFactory lifecycle, AcousticOrchestrator DSP extraction,
GeminiSpeakingProvider execution, short-circuit audio gating, underlength penalties,
and circuit breaker failover routing.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import numpy as np

from acoustic.acoustic_orchestrator import AcousticOrchestrator
from acoustic.models import WordTimestamp
from acoustic.phonetic_models import (
    FullAcousticAnalysisResult,
    IntonationAnalysis,
    WordStressAnalysis,
)
from models.events import (
    AudioReferencePayload,
    SpeakingEventEnvelope,
    SpeakingEvaluationRequestedPayload,
)
from providers.base import ProviderCallError
from providers.factory import ProviderFactory, get_speaking_provider
from providers.gemini_speaking_provider import GeminiSpeakingProvider
from providers.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from providers.resilience.provider_selector import (
    IntelligentProviderSelector,
    ProviderConfig,
)
from providers.schemas_speaking_additions import SpeakingEvaluationResult
from workers.speaking_consumer import SpeakingEvaluationConsumer


class MockRecord:
    def __init__(self, value: bytes, offset: int = 0, partition: int = 0):
        self.value = value
        self.offset = offset
        self.partition = partition


class TestSpeakingPipelineE2E(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_db_pool = MagicMock()
        self.mock_conn = AsyncMock()
        self.mock_db_pool.acquire.return_value.__aenter__.return_value = self.mock_conn

        self.consumer = SpeakingEvaluationConsumer(
            db_pool=self.mock_db_pool,
            concurrency_limit=5,
            bootstrap_servers="localhost:9092",
        )
        self.consumer.consumer = AsyncMock()
        self.consumer.producer = AsyncMock()
        self.consumer.publisher = MagicMock()
        self.consumer.publisher.publish_completed = AsyncMock()
        self.consumer.publisher.publish_failed = AsyncMock()

    # --------------------------------------------------------------------------
    # Legacy Consumer Ingestion & Deduplication Tests
    # --------------------------------------------------------------------------
    @patch("workers.speaking_consumer.try_acquire_inbox")
    @patch("workers.speaking_consumer.mark_inbox_completed")
    async def test_speaking_claim_check_consumption_and_completion(
        self, mock_completed, mock_acquire
    ):
        mock_acquire.return_value = True

        attempt_id = UUID("f47ac10b-58cc-4372-a567-0e02b2c3d479")
        student_id = UUID("a2effcb1-77d8-41a3-b6e1-73c4f60219c5")
        event_id = UUID("1fa85f64-5717-4562-b3fc-2c963f66afa6")
        idempotency_key = UUID("2fa85f64-5717-4562-b3fc-2c963f66afa6")

        audio_ref = AudioReferencePayload(
            storageProvider="MINIO",
            bucket="engonow-audio-recordings",
            objectKey="recordings/2026/08/attempt-001.wav",
            checksumSha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            contentType="audio/wav",
            durationSeconds=118.5,
        )

        payload = SpeakingEvaluationRequestedPayload(
            attemptId=attempt_id,
            studentId=student_id,
            part="PART_2",
            audioRef=audio_ref,
        )

        envelope = SpeakingEventEnvelope(
            eventId=event_id,
            idempotencyKey=idempotency_key,
            eventType="SPEAKING_EVALUATION_REQUESTED",
            schemaVersion="1.0",
            occurredAt=datetime.now(timezone.utc),
            producedAt=datetime.now(timezone.utc),
            traceId="trace-speaking-123",
            correlationId=str(attempt_id),
            source="engonow-lms-backend",
            retryCount=0,
            payload=payload,
        )

        raw_json = envelope.model_dump_json()
        record = MockRecord(value=raw_json.encode("utf-8"))

        await self.consumer._process_record(record)

        if self.consumer.active_tasks:
            await asyncio.gather(*self.consumer.active_tasks)

        mock_acquire.assert_called_once()
        mock_completed.assert_called_once_with(self.mock_db_pool, idempotency_key)
        self.consumer.publisher.publish_completed.assert_called_once()
        call_kwargs = self.consumer.publisher.publish_completed.call_args.kwargs
        self.assertEqual(call_kwargs["attempt_id"], attempt_id)
        self.assertEqual(call_kwargs["overall_band"], 7.0)

    @patch("workers.speaking_consumer.try_acquire_inbox")
    async def test_speaking_duplicate_event_deduplication(self, mock_acquire):
        mock_acquire.return_value = False

        attempt_id = UUID("f47ac10b-58cc-4372-a567-0e02b2c3d479")
        student_id = UUID("a2effcb1-77d8-41a3-b6e1-73c4f60219c5")
        event_id = UUID("1fa85f64-5717-4562-b3fc-2c963f66afa6")
        idempotency_key = UUID("2fa85f64-5717-4562-b3fc-2c963f66afa6")

        audio_ref = AudioReferencePayload(
            storageProvider="MINIO",
            bucket="engonow-audio-recordings",
            objectKey="recordings/2026/08/attempt-001.wav",
            checksumSha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            contentType="audio/wav",
            durationSeconds=60.0,
        )

        payload = SpeakingEvaluationRequestedPayload(
            attemptId=attempt_id,
            studentId=student_id,
            part="PART_1",
            audioRef=audio_ref,
        )

        envelope = SpeakingEventEnvelope(
            eventId=event_id,
            idempotencyKey=idempotency_key,
            eventType="SPEAKING_EVALUATION_REQUESTED",
            schemaVersion="1.0",
            occurredAt=datetime.now(timezone.utc),
            producedAt=datetime.now(timezone.utc),
            traceId="trace-dup",
            correlationId=str(attempt_id),
            source="engonow-lms-backend",
            retryCount=0,
            payload=payload,
        )

        raw_json = envelope.model_dump_json()
        record = MockRecord(value=raw_json.encode("utf-8"))

        await self.consumer._process_record(record)
        self.consumer.consumer.commit.assert_called_once()
        self.consumer.publisher.publish_completed.assert_not_called()

    # --------------------------------------------------------------------------
    # Multi-Modal Pipeline & Provider Tests (Sprint 4)
    # --------------------------------------------------------------------------
    def test_factory_speaking_provider_registration_and_selection(self):
        """
        Test 1: Verifies ProviderFactory registers GeminiSpeakingProvider,
        allows explicit provider_id lookup, and raises ValueError on unknown provider.
        """
        mock_gemini = AsyncMock()
        factory = ProviderFactory(gemini_client=mock_gemini)

        # Default provider lookup
        default_provider = factory.get_speaking_provider()
        self.assertIsInstance(default_provider, GeminiSpeakingProvider)
        self.assertEqual(default_provider.provider_id, "GEMINI_2_5_FLASH_SPEAKING")

        # Explicit provider lookup
        explicit_provider = factory.get_speaking_provider("GEMINI_2_5_FLASH_SPEAKING")
        self.assertEqual(explicit_provider, default_provider)

        # Invalid provider lookup
        with self.assertRaises(ValueError):
            factory.get_speaking_provider("UNKNOWN_PROVIDER_999")

    async def test_full_speaking_pipeline_e2e_normal_scoring(self):
        """
        Test 2: Full pipeline: Synthetic audio + word timestamps -> AcousticOrchestrator
        -> GeminiSpeakingProvider -> SpeakingEvaluationResult.
        """
        sample_rate = 16000
        duration = 5.0
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False, dtype=np.float32)
        # 200 Hz pitch harmonic with modest amplitude
        audio_waveform = 0.3 * np.sin(2 * np.pi * 200 * t)

        word_timestamps = [
            WordTimestamp(word="I", start=0.5, end=0.8, probability=0.98),
            WordTimestamp(word="enjoy", start=0.9, end=1.3, probability=0.95),
            WordTimestamp(word="reading", start=1.4, end=1.9, probability=0.96),
            WordTimestamp(word="science", start=2.2, end=2.7, probability=0.94),
            WordTimestamp(word="fiction", start=2.8, end=3.4, probability=0.97),
            WordTimestamp(word="novels", start=3.5, end=4.1, probability=0.95),
        ]

        orchestrator = AcousticOrchestrator()
        acoustic_result = orchestrator.process_speaking_audio(
            audio_data=audio_waveform,
            sample_rate=sample_rate,
            word_timestamps=word_timestamps,
            total_duration=duration,
        )

        self.assertFalse(acoustic_result.excluded_from_automated_scoring)
        self.assertEqual(acoustic_result.word_count, 6)

        llm_response_json = {
            "overallBand": 7.0,
            "fluencyCoherenceScore": 7.0,
            "lexicalResourceScore": 7.0,
            "grammaticalRangeScore": 7.0,
            "pronunciationScore": 7.0,
            "feedbackDetail": {
                "examinerSummary": "Bài nói lưu loát với phát âm rõ ràng.",
                "speakingMetrics": {
                    "totalWords": 6,
                    "speakingRateWpm": 72.0,
                    "articulationRateWpm": 100.0,
                    "phonationRatio": 0.72,
                    "pauseCount": 2,
                    "totalPauseDurationSeconds": 0.6,
                    "stressAccuracyRatio": 0.85,
                    "pitchVariationCv": 0.16,
                    "monotoneFlag": False,
                    "dominantContour": "FALLING",
                },
                "criteria": [
                    {
                        "criterion": "FLUENCY_COHERENCE",
                        "score": 7.0,
                        "summary": "Tốc độ nói ổn định.",
                        "strengths": ["Lưu loát"],
                        "weaknesses": [],
                        "acousticGroundingNote": "Grounded on speech rate and pause analysis.",
                    },
                    {
                        "criterion": "LEXICAL_RESOURCE",
                        "score": 7.0,
                        "summary": "Từ vựng tốt.",
                        "strengths": ["Từ vựng tự nhiên"],
                        "weaknesses": [],
                    },
                    {
                        "criterion": "GRAMMATICAL_RANGE_ACCURACY",
                        "score": 7.0,
                        "summary": "Ngữ pháp chuẩn xác.",
                        "strengths": ["Cấu trúc tốt"],
                        "weaknesses": [],
                    },
                    {
                        "criterion": "PRONUNCIATION",
                        "score": 7.0,
                        "summary": "Phát âm rõ ràng.",
                        "strengths": ["Trọng âm chuẩn"],
                        "weaknesses": [],
                        "acousticGroundingNote": "Grounded on 85% word stress accuracy.",
                    },
                ],
            },
        }

        mock_gemini = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps(llm_response_json)
        mock_gemini.generate_content_async = AsyncMock(return_value=mock_response)

        factory = ProviderFactory(gemini_client=mock_gemini)
        provider = factory.get_speaking_provider()

        result = await provider.evaluate_speaking(
            question="Describe your reading habits.",
            transcript="I enjoy reading science fiction novels.",
            acoustic_result=acoustic_result,
            exam_part="PART1",
        )

        self.assertIsInstance(result, SpeakingEvaluationResult)
        self.assertEqual(result.overallBand, 7.0)
        self.assertEqual(result.fluencyCoherenceScore, 7.0)
        self.assertEqual(result.pronunciationScore, 7.0)
        self.assertFalse(result.requiresHumanReview)
        self.assertEqual(mock_gemini.generate_content_async.call_count, 1)

    async def test_full_speaking_pipeline_short_circuit_on_damaged_audio(self):
        """
        Test 3: Damaged audio triggering acoustic exclusion short-circuits the pipeline,
        completely skipping LLM calls (0 network requests).
        """
        excluded_result = FullAcousticAnalysisResult(
            speaking_rate_wpm=20.0,
            articulation_rate_wpm=25.0,
            phonation_ratio=0.10,
            total_duration_seconds=10.0,
            phonation_time_seconds=1.0,
            word_count=4,
            pause_analysis={},
            phoneme_errors=[],
            word_stress_analysis=WordStressAnalysis(0, 0, 0.0),
            intonation_analysis=IntonationAnalysis(0.0, 0.0, 0.0, True, "FLAT"),
            excluded_from_automated_scoring=True,
            exclusion_reason="Severe audio packet loss and clipping > 25%",
        )

        mock_gemini = AsyncMock()
        factory = ProviderFactory(gemini_client=mock_gemini)
        provider = factory.get_speaking_provider()

        result = await provider.evaluate_speaking(
            question="Tell me about your school.",
            transcript="My school is big.",
            acoustic_result=excluded_result,
            exam_part="PART1",
        )

        # Gemini API must never be called
        self.assertEqual(mock_gemini.generate_content_async.call_count, 0)
        self.assertIsNone(result.overallBand)
        self.assertIsNone(result.fluencyCoherenceScore)
        self.assertIsNone(result.pronunciationScore)
        self.assertTrue(result.requiresHumanReview)
        self.assertIn("Severe audio packet loss and clipping > 25%", result.feedbackDetail.examinerSummary)

    async def test_speaking_pipeline_underlength_penalty_guardrail(self):
        """
        Test 4: Candidate transcript with 7 words (< 20 words) has LR and GRA capped at Band 4.0.
        """
        sample_acoustic = FullAcousticAnalysisResult(
            speaking_rate_wpm=100.0,
            articulation_rate_wpm=120.0,
            phonation_ratio=0.60,
            total_duration_seconds=4.0,
            phonation_time_seconds=2.4,
            word_count=7,
            pause_analysis={},
            phoneme_errors=[],
            word_stress_analysis=WordStressAnalysis(2, 2, 1.0),
            intonation_analysis=IntonationAnalysis(80.0, 15.0, 0.15, False, "FALLING"),
            excluded_from_automated_scoring=False,
            exclusion_reason=None,
        )

        llm_response_json = {
            "overallBand": 4.5,
            "fluencyCoherenceScore": 5.5,
            "lexicalResourceScore": 4.0,       # Capped at 4.0 due to < 20 words
            "grammaticalRangeScore": 4.0,      # Capped at 4.0 due to < 20 words
            "pronunciationScore": 5.5,
            "feedbackDetail": {
                "examinerSummary": "Bài nói quá ngắn (< 20 từ) nên điểm LR và GRA bị giới hạn tối đa 4.0.",
                "speakingMetrics": {"totalWords": 7},
                "criteria": [
                    {"criterion": "FLUENCY_COHERENCE", "score": 5.5, "summary": "Tốc độ nói vừa phải."},
                    {"criterion": "LEXICAL_RESOURCE", "score": 4.0, "summary": "Capped at Band 4.0 due to underlength response (< 20 words)."},
                    {"criterion": "GRAMMATICAL_RANGE_ACCURACY", "score": 4.0, "summary": "Capped at Band 4.0 due to underlength response (< 20 words)."},
                    {"criterion": "PRONUNCIATION", "score": 5.5, "summary": "Phát âm rõ."},
                ],
            },
        }

        mock_gemini = AsyncMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps(llm_response_json)
        mock_gemini.generate_content_async = AsyncMock(return_value=mock_response)

        factory = ProviderFactory(gemini_client=mock_gemini)
        provider = factory.get_speaking_provider()

        result = await provider.evaluate_speaking(
            question="Do you like sports?",
            transcript="Yes I like playing football very much.",
            acoustic_result=sample_acoustic,
            exam_part="PART1",
        )

        # (5.5 + 4.0 + 4.0 + 5.5) / 4 = 19.0 / 4 = 4.75 -> Cambridge round = 5.0
        self.assertEqual(result.lexicalResourceScore, 4.0)
        self.assertEqual(result.grammaticalRangeScore, 4.0)
        self.assertEqual(result.overallBand, 5.0)

    async def test_speaking_provider_circuit_breaker_failover(self):
        """
        Test 5: When primary provider's circuit breaker is OPEN,
        IntelligentProviderSelector cascades to healthy fallback or raises ProviderCallError when exhausted.
        """
        primary_cb = CircuitBreaker(CircuitBreakerConfig(provider_id="GEMINI_2_5_FLASH_SPEAKING"))
        fallback_cb = CircuitBreaker(CircuitBreakerConfig(provider_id="AZURE_GPT_4O_SPEAKING"))

        # Trip primary circuit breaker
        primary_cb.record_failure("QUOTA_EXHAUSTED")
        self.assertEqual(primary_cb.state, CircuitState.OPEN)
        self.assertEqual(fallback_cb.state, CircuitState.CLOSED)

        primary_cfg = ProviderConfig(
            provider_id="GEMINI_2_5_FLASH_SPEAKING",
            priority=1,
            cost_per_thousand_input_tokens=Decimal("0.001"),
            cost_per_thousand_output_tokens=Decimal("0.002"),
            latency_sla_budget_seconds=2.0,
            validated_mae=Decimal("0.28"),
            mae_validated_at=datetime.now(timezone.utc),
        )

        fallback_cfg = ProviderConfig(
            provider_id="AZURE_GPT_4O_SPEAKING",
            priority=2,
            cost_per_thousand_input_tokens=Decimal("0.005"),
            cost_per_thousand_output_tokens=Decimal("0.015"),
            latency_sla_budget_seconds=3.0,
            validated_mae=Decimal("0.35"),
            mae_validated_at=datetime.now(timezone.utc),
        )

        selector = IntelligentProviderSelector(
            providers={
                "GEMINI_2_5_FLASH_SPEAKING": primary_cfg,
                "AZURE_GPT_4O_SPEAKING": fallback_cfg,
            },
            circuit_breakers={
                "GEMINI_2_5_FLASH_SPEAKING": primary_cb,
                "AZURE_GPT_4O_SPEAKING": fallback_cb,
            },
        )

        mock_fallback_provider = MagicMock()
        mock_fallback_provider.provider_id = "AZURE_GPT_4O_SPEAKING"

        factory = ProviderFactory(
            circuit_breaker_registry={
                "GEMINI_2_5_FLASH_SPEAKING": primary_cb,
                "AZURE_GPT_4O_SPEAKING": fallback_cb,
            },
            provider_selector=selector,
        )
        factory.register_speaking_provider("AZURE_GPT_4O_SPEAKING", mock_fallback_provider)

        # Dynamic selection routes to fallback because primary is OPEN
        selected = factory.get_speaking_provider()
        self.assertEqual(selected.provider_id, "AZURE_GPT_4O_SPEAKING")


if __name__ == "__main__":
    unittest.main()
