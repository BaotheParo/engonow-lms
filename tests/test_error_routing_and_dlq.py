import asyncio
import json
from uuid import uuid4
from datetime import datetime, timezone
import unittest
from unittest.mock import AsyncMock, MagicMock

from workers.error_handler import (
    ResilientRoutingHandler,
    NonRetriableProcessingError,
    RetriableProcessingError
)
from models.events import EventEnvelope, WritingEvaluationRequestedPayload
from providers.schemas import TaskType

class TestErrorRoutingAndDlq(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_producer = AsyncMock()
        self.handler = ResilientRoutingHandler(self.mock_producer)

    async def test_poison_pill_routes_to_dlq_immediately(self):
        mock_record = MagicMock()
        mock_record.topic = "engonow.writing.evaluation-requested.v1"
        mock_record.partition = 2
        mock_record.offset = 100
        mock_record.key = b"sub-123"
        mock_record.value = b"INVALID_JSON_{{"

        exc = NonRetriableProcessingError("Malformed JSON")

        route = await self.handler.handle_processing_error(exc, mock_record, envelope=None)
        self.assertEqual(route, "DLQ")

        self.mock_producer.send_and_wait.assert_called_once()
        args, kwargs = self.mock_producer.send_and_wait.call_args
        self.assertEqual(args[0], "engonow.writing.evaluation-requested.v1.dlq")
        self.assertEqual(kwargs["key"], b"sub-123")
        self.assertEqual(kwargs["value"], b"INVALID_JSON_{{")

        header_dict = {h[0]: h[1] for h in kwargs["headers"]}
        self.assertEqual(header_dict["x-dead-letter-reason"], b"Malformed JSON")
        self.assertEqual(header_dict["x-original-topic"], b"engonow.writing.evaluation-requested.v1")
        self.assertEqual(header_dict["x-original-partition"], b"2")
        self.assertEqual(header_dict["x-original-offset"], b"100")

    async def test_rate_limit_429_routes_to_retry_topic(self):
        submission_id = uuid4()
        envelope = EventEnvelope(
            eventId=uuid4(),
            idempotencyKey=uuid4(),
            eventType="WRITING_EVALUATION_REQUESTED",
            occurredAt=datetime.now(timezone.utc),
            producedAt=datetime.now(timezone.utc),
            source="test",
            retryCount=0,
            payload=WritingEvaluationRequestedPayload(
                submissionId=submission_id,
                studentId=uuid4(),
                taskType=TaskType.TASK2,
                taskPrompt="Prompt text",
                essayText="Essay text",
                wordCount=150
            )
        )

        mock_record = MagicMock()
        mock_record.topic = "engonow.writing.evaluation-requested.v1"
        mock_record.partition = 0
        mock_record.offset = 55
        mock_record.key = str(submission_id).encode("utf-8")

        exc = RetriableProcessingError("HTTP 429: Resource Exhausted")

        route = await self.handler.handle_processing_error(exc, mock_record, envelope=envelope)
        self.assertEqual(route, "RETRY")
        self.assertEqual(envelope.retryCount, 1)

        self.mock_producer.send_and_wait.assert_called_once()
        args, kwargs = self.mock_producer.send_and_wait.call_args
        self.assertEqual(args[0], "engonow.writing.evaluation-requested.v1.retry.30s")

        header_dict = {h[0]: h[1] for h in kwargs["headers"]}
        self.assertEqual(header_dict["x-retry-delay-ms"], b"30000")

    async def test_exhausted_retries_routes_to_dlq(self):
        submission_id = uuid4()
        envelope = EventEnvelope(
            eventId=uuid4(),
            idempotencyKey=uuid4(),
            eventType="WRITING_EVALUATION_REQUESTED",
            occurredAt=datetime.now(timezone.utc),
            producedAt=datetime.now(timezone.utc),
            source="test",
            retryCount=3,  # Already at max retries
            payload=WritingEvaluationRequestedPayload(
                submissionId=submission_id,
                studentId=uuid4(),
                taskType=TaskType.TASK2,
                taskPrompt="Prompt text",
                essayText="Essay text",
                wordCount=150
            )
        )

        mock_record = MagicMock()
        mock_record.topic = "engonow.writing.evaluation-requested.v1"
        mock_record.partition = 1
        mock_record.offset = 77
        mock_record.key = str(submission_id).encode("utf-8")

        exc = RetriableProcessingError("HTTP 503: Service Unavailable")

        route = await self.handler.handle_processing_error(exc, mock_record, envelope=envelope)
        self.assertEqual(route, "DLQ")

        self.mock_producer.send_and_wait.assert_called_once()
        args, kwargs = self.mock_producer.send_and_wait.call_args
        self.assertEqual(args[0], "engonow.writing.evaluation-requested.v1.dlq")

        header_dict = {h[0]: h[1] for h in kwargs["headers"]}
        self.assertIn(b"MAX_RETRIES_EXCEEDED", header_dict["x-dead-letter-reason"])
