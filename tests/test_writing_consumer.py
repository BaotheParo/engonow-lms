import asyncio
import json
from uuid import UUID
from datetime import datetime, timezone
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from workers.writing_consumer import WritingEvaluationConsumer
from models.events import EventEnvelope, WritingEvaluationRequestedPayload
from providers.schemas import TaskType
from providers.gemini_writing_provider import GeminiWritingProvider

class MockConsumer:
    def __init__(self, messages):
        self.messages = messages
        self.commit = AsyncMock()

    def __aiter__(self):
        async def gen():
            for m in self.messages:
                yield m
        return gen()

class TestWritingConsumer(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_db_pool = MagicMock()
        self.mock_conn = AsyncMock()
        
        # Configure mock db pool context manager
        self.mock_db_pool.acquire.return_value.__aenter__.return_value = self.mock_conn
        
        self.mock_provider = MagicMock(spec=GeminiWritingProvider)
        self.mock_provider.evaluate_essay = AsyncMock(return_value={"score": 8.0, "feedback": "Excellent"})
        
        self.consumer_worker = WritingEvaluationConsumer(
            db_pool=self.mock_db_pool,
            writing_provider=self.mock_provider,
            concurrency_limit=5,
            bootstrap_servers="localhost:9092"
        )
        
        self.consumer_worker.producer = AsyncMock()

    @patch("workers.writing_consumer.try_acquire_inbox")
    @patch("workers.writing_consumer.mark_inbox_completed")
    async def test_successful_consumption_and_inbox_dedup(self, mock_completed, mock_acquire):
        # 1. Message 1 -> New processing
        mock_acquire.return_value = True
        
        payload = WritingEvaluationRequestedPayload(
            submissionId=UUID("4fa85f64-5717-4562-b3fc-2c963f66afa6"),
            studentId=UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
            taskType=TaskType.TASK2,
            taskPrompt="Discuss pollution solutions",
            essayText="Governments should implement carbon taxes.",
            wordCount=300
        )
        envelope = EventEnvelope(
            eventId=UUID("1fa85f64-5717-4562-b3fc-2c963f66afa6"),
            idempotencyKey=UUID("1fa85f64-5717-4562-b3fc-2c963f66afa6"),
            eventType="WRITING_EVALUATION_REQUESTED",
            occurredAt=datetime.now(timezone.utc),
            producedAt=datetime.now(timezone.utc),
            source="test",
            payload=payload
        )

        mock_msg = MagicMock()
        mock_msg.value = envelope.model_dump_json().encode('utf-8')
        mock_msg.headers = []
        mock_msg.partition = 0
        mock_msg.offset = 12

        self.consumer_worker.consumer = MockConsumer([mock_msg])
        self.consumer_worker.running = True

        # Process the messages
        await self.consumer_worker._consume_loop()

        # Wait for spawned tasks to finish processing
        await asyncio.sleep(0.1)

        # Verify try_acquire_inbox and evaluate_essay invoked, offset committed
        mock_acquire.assert_called_once()
        self.mock_provider.evaluate_essay.assert_called_once_with(
            task_type="TASK2",
            task_prompt="Discuss pollution solutions",
            essay_text="Governments should implement carbon taxes."
        )
        mock_completed.assert_called_once_with(self.mock_conn, envelope.idempotencyKey)
        self.consumer_worker.consumer.commit.assert_called_once()

        # Reset mocks for duplicate test
        self.mock_provider.evaluate_essay.reset_mock()
        mock_acquire.reset_mock()
        mock_completed.reset_mock()

        # 2. Message 2 -> Duplicate processing (returns False)
        mock_acquire.return_value = False
        self.consumer_worker.consumer = MockConsumer([mock_msg])
        await self.consumer_worker._consume_loop()
        await asyncio.sleep(0.1)

        # Verify duplicate bypassed the provider, but committed offset
        mock_acquire.assert_called_once()
        self.mock_provider.evaluate_essay.assert_not_called()
        mock_completed.assert_not_called()
        self.consumer_worker.consumer.commit.assert_called_once()

    async def test_poison_pill_sent_to_dlq_and_offset_committed(self):
        mock_msg = MagicMock()
        mock_msg.value = b"invalid json string data"
        mock_msg.headers = []
        mock_msg.partition = 1
        mock_msg.offset = 42

        self.consumer_worker.consumer = MockConsumer([mock_msg])
        self.consumer_worker.running = True

        await self.consumer_worker._consume_loop()

        # Verify routed to DLQ and offset committed to skip poison pill
        self.consumer_worker.producer.send_and_wait.assert_called_once()
        args, kwargs = self.consumer_worker.producer.send_and_wait.call_args
        self.assertEqual(args[0], "engonow.writing.evaluation-requested.v1.dlq")
        self.assertEqual(kwargs["key"], mock_msg.key)
        self.assertEqual(kwargs["value"], mock_msg.value)
        
        header_keys = [h[0] for h in kwargs["headers"]]
        self.assertIn("x-dead-letter-reason", header_keys)
        self.assertIn("x-original-topic", header_keys)
        self.assertIn("x-failed-at", header_keys)
        self.assertIn("partition", header_keys)
        self.assertIn("offset", header_keys)
        self.consumer_worker.consumer.commit.assert_called_once()

    @patch("workers.writing_consumer.try_acquire_inbox")
    async def test_concurrency_semaphore_limits_in_flight_tasks(self, mock_acquire):
        mock_acquire.return_value = True
        
        # Simulate long Gemini evaluation duration
        eval_event = asyncio.Event()
        async def slow_evaluation(*args, **kwargs):
            await eval_event.wait()
            return {"score": 8.0}
        self.mock_provider.evaluate_essay.side_effect = slow_evaluation

        payload = WritingEvaluationRequestedPayload(
            submissionId=UUID("4fa85f64-5717-4562-b3fc-2c963f66afa6"),
            studentId=UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"),
            taskType=TaskType.TASK2,
            taskPrompt="Discuss pollution solutions",
            essayText="Governments should implement carbon taxes.",
            wordCount=300
        )
        envelope = EventEnvelope(
            eventId=UUID("1fa85f64-5717-4562-b3fc-2c963f66afa6"),
            idempotencyKey=UUID("1fa85f64-5717-4562-b3fc-2c963f66afa6"),
            eventType="WRITING_EVALUATION_REQUESTED",
            occurredAt=datetime.now(timezone.utc),
            producedAt=datetime.now(timezone.utc),
            source="test",
            payload=payload
        )

        mock_msg = MagicMock()
        mock_msg.value = envelope.model_dump_json().encode('utf-8')
        mock_msg.headers = []

        # Send 20 concurrent messages
        messages = [mock_msg] * 20
        self.consumer_worker.consumer = MockConsumer(messages)
        self.consumer_worker.running = True

        await self.consumer_worker._consume_loop()
        await asyncio.sleep(0.1)

        # Semaphore limit is 5. We expect exactly 5 active/blocked calls, 15 queued in semaphore
        self.assertEqual(self.consumer_worker.semaphore._value, 0)
        
        # Release the evaluation block
        eval_event.set()
        await asyncio.sleep(0.1)
        
        # Verify provider called 20 times in total
        self.assertEqual(self.mock_provider.evaluate_essay.call_count, 20)
