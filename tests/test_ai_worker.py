"""Tests for the asynchronous speaking event worker."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

import ai_worker
from providers.base import EvaluationStatus, UnifiedSpeakingResult
from providers.consumer import (
    LocalEventBroker,
    LocalEventConsumer,
    LocalEventPublisher,
)
from telemetry.metrics import EVALUATION_REQUESTS_TOTAL


REQUIRED_RESULT_FIELDS = {
    "session_id",
    "pronunciation_score",
    "fluency_score",
    "grammar_score",
    "lexical_score",
    "status",
    "genuine_word_coverage",
}


def successful_result(session_id: str) -> UnifiedSpeakingResult:
    return UnifiedSpeakingResult(
        session_id=session_id,
        provider_used="GROQ_LOCAL",
        pronunciation_score=7,
        fluency_score=7,
        grammar_score=8,
        lexical_score=8,
        status=EvaluationStatus.SUCCESS,
        genuine_word_coverage=0.91,
        feedback_text="Strong, well-supported response.",
        processing_time_ms=125.0,
        provider_metadata={"warnings": []},
    )


class AiWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_metrics_are_recorded_on_evaluation(self) -> None:
        provider = Mock()
        provider.provider_name = "GROQ_LOCAL"
        provider.evaluate = AsyncMock(
            return_value=successful_result("session-metrics")
        )
        success_counter = EVALUATION_REQUESTS_TOTAL.labels(
            provider="GROQ_LOCAL",
            status="SUCCESS",
        )
        counter_before = success_counter._value.get()

        with patch("ai_worker.get_speaking_provider", return_value=provider):
            result_payload = await ai_worker.process_speaking_request(
                {
                    "session_id": "session-metrics",
                    "questions_metadata": [],
                    "audio_url": (
                        "https://cdn.example.test/session-metrics.mp3"
                    ),
                }
            )

        self.assertEqual(result_payload["status"], "SUCCESS")
        self.assertEqual(success_counter._value.get(), counter_before + 1)

    async def test_local_consumer_publishes_complete_result(self) -> None:
        broker = LocalEventBroker()
        consumer = LocalEventConsumer(
            broker=broker,
            topic="ielts-speaking-requests",
            max_in_flight=2,
        )
        publisher = LocalEventPublisher(
            broker=broker,
            topic="ielts-speaking-results",
        )
        provider = Mock()
        provider.evaluate = AsyncMock(return_value=successful_result("session-101"))

        await publisher.start()
        with patch("ai_worker.get_speaking_provider", return_value=provider):
            listener_task = asyncio.create_task(
                consumer.start_listening(
                    handler=ai_worker.process_speaking_request,
                    publisher=publisher.publish,
                )
            )
            try:
                await consumer.enqueue(
                    {
                        "eventType": "SPEAKING_EVALUATION_REQUESTED",
                        "sessionId": "session-101",
                        "questionsMetadata": [
                            {
                                "part": "PART_1",
                                "question": "Where do you live?",
                            }
                        ],
                        "audioUrl": "https://cdn.example.test/session-101.mp3",
                    }
                )
                result_payload = await asyncio.wait_for(
                    broker.receive("ielts-speaking-results"),
                    timeout=1.0,
                )
            finally:
                await consumer.stop()
                await listener_task
                await publisher.stop()

        self.assertTrue(REQUIRED_RESULT_FIELDS.issubset(result_payload))
        self.assertEqual(result_payload["session_id"], "session-101")
        self.assertEqual(result_payload["status"], "SUCCESS")
        provider.evaluate.assert_awaited_once()

    async def test_process_request_invokes_configured_provider(self) -> None:
        provider = Mock()
        provider.evaluate = AsyncMock(return_value=successful_result("booking-42"))

        with patch(
            "ai_worker.get_speaking_provider",
            return_value=provider,
        ) as provider_factory:
            result_payload = await ai_worker.process_speaking_request(
                {
                    "session_id": "booking-42",
                    "questions_metadata": "Part 2: Describe a memorable journey.",
                    "audio_url": "https://cdn.example.test/booking-42.wav",
                    "audio_filename": "booking-42.wav",
                }
            )

        provider_factory.assert_called_once_with()
        provider.evaluate.assert_awaited_once_with(
            session_id="booking-42",
            audio_url="https://cdn.example.test/booking-42.wav",
            gemini_api_key=ai_worker.CONFIG.gemini_api_key,
            questions_metadata="Part 2: Describe a memorable journey.",
            audio_bytes=None,
            audio_filename="booking-42.wav",
        )
        self.assertEqual(result_payload["provider_used"], "GROQ_LOCAL")

    async def test_provider_exception_returns_system_error_payload(self) -> None:
        provider = Mock()
        provider.evaluate = AsyncMock(
            side_effect=RuntimeError("Upstream model unavailable")
        )

        with patch("ai_worker.get_speaking_provider", return_value=provider):
            result_payload = await ai_worker.process_speaking_request(
                {
                    "aggregate_id": "session-error",
                    "questions_metadata": [],
                    "audio_url": "https://cdn.example.test/session-error.mp3",
                }
            )

        self.assertTrue(REQUIRED_RESULT_FIELDS.issubset(result_payload))
        self.assertEqual(result_payload["session_id"], "session-error")
        self.assertEqual(result_payload["status"], "SYSTEM_ERROR")
        self.assertEqual(result_payload["genuine_word_coverage"], 0.0)
        self.assertEqual(
            result_payload["provider_metadata"]["error"],
            "Upstream model unavailable",
        )


if __name__ == "__main__":
    unittest.main()
