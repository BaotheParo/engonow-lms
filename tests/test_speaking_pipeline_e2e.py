import asyncio
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from models.events import (
    AudioReferencePayload,
    SpeakingEventEnvelope,
    SpeakingEvaluationRequestedPayload,
)
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
            bootstrap_servers="localhost:9092"
        )
        self.consumer.consumer = AsyncMock()
        self.consumer.producer = AsyncMock()
        self.consumer.publisher = MagicMock()
        self.consumer.publisher.publish_completed = AsyncMock()
        self.consumer.publisher.publish_failed = AsyncMock()

    @patch("workers.speaking_consumer.try_acquire_inbox")
    @patch("workers.speaking_consumer.mark_inbox_completed")
    async def test_speaking_claim_check_consumption_and_completion(self, mock_completed, mock_acquire):
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
            durationSeconds=118.5
        )

        payload = SpeakingEvaluationRequestedPayload(
            attemptId=attempt_id,
            studentId=student_id,
            part="PART_2",
            audioRef=audio_ref
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
            payload=payload
        )

        raw_json = envelope.model_dump_json()
        record = MockRecord(value=raw_json.encode("utf-8"))

        await self.consumer._process_record(record)

        # Wait for background evaluation task to finish
        if self.consumer.active_tasks:
            await asyncio.gather(*self.consumer.active_tasks)

        # Verify Inbox acquired and marked completed
        mock_acquire.assert_called_once()
        mock_completed.assert_called_once_with(self.mock_db_pool, idempotency_key)

        # Verify publish_completed invoked with Cambridge score breakdown
        self.consumer.publisher.publish_completed.assert_called_once()
        call_kwargs = self.consumer.publisher.publish_completed.call_args.kwargs
        self.assertEqual(call_kwargs["attempt_id"], attempt_id)
        self.assertEqual(call_kwargs["overall_band"], 7.0)
        self.assertEqual(call_kwargs["fluency_score"], 7.0)
        self.assertIn("speechMetrics", call_kwargs["feedback_detail"])

    @patch("workers.speaking_consumer.try_acquire_inbox")
    async def test_speaking_duplicate_event_deduplication(self, mock_acquire):
        # When inbox acquisition returns False (duplicate)
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
            durationSeconds=60.0
        )

        payload = SpeakingEvaluationRequestedPayload(
            attemptId=attempt_id,
            studentId=student_id,
            part="PART_1",
            audioRef=audio_ref
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
            payload=payload
        )

        raw_json = envelope.model_dump_json()
        record = MockRecord(value=raw_json.encode("utf-8"))

        await self.consumer._process_record(record)

        # Offset committed, but no evaluation task spawned or completed event published
        self.consumer.consumer.commit.assert_called_once()
        self.consumer.publisher.publish_completed.assert_not_called()

if __name__ == "__main__":
    unittest.main()
