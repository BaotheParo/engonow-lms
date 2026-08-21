import asyncio
import json
from uuid import UUID, uuid4
import unittest
from unittest.mock import AsyncMock

from workers.outbox_publisher import WritingResultEventPublisher

class TestWritingResultEventPublisher(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_producer = AsyncMock()
        self.publisher = WritingResultEventPublisher(self.mock_producer)

    async def test_publish_completed_success(self):
        submission_id = uuid4()
        raw_evaluation = {
            "criteria": {
                "TASK_ACHIEVEMENT": {"band": 6.5, "feedback": "Good response"},
                "COHERENCE_COHESION": {"band": 6.0, "feedback": "Clear flow"},
                "LEXICAL_RESOURCE": {"band": 6.5, "feedback": "Good vocabulary"},
                "GRAMMATICAL_RANGE_ACCURACY": {"band": 6.0, "feedback": "Accurate"}
            },
            "overallBand": 6.5,
            "feedbackDetail": {
                "examinerSummary": "Solid essay with minor grammatical slips.",
                "essayMetrics": {
                    "wordCount": 260,
                    "paragraphCount": 4,
                    "sentenceCount": 15,
                    "avgSentenceLength": 17.3
                }
            }
        }

        await self.publisher.publish_completed(
            submission_id=submission_id,
            raw_evaluation=raw_evaluation,
            trace_id="test-trace-123",
            correlation_id=str(submission_id)
        )

        self.mock_producer.send_and_wait.assert_called_once()
        args, kwargs = self.mock_producer.send_and_wait.call_args
        self.assertEqual(args[0], "engonow.writing.evaluation-completed.v1")
        self.assertEqual(kwargs["key"], str(submission_id).encode("utf-8"))

        envelope = json.loads(kwargs["value"].decode("utf-8"))
        self.assertEqual(envelope["eventType"], "WRITING_EVALUATION_COMPLETED")
        self.assertEqual(envelope["schemaVersion"], "1.0")
        self.assertEqual(envelope["traceId"], "test-trace-123")
        self.assertEqual(envelope["payload"]["submissionId"], str(submission_id))
        self.assertEqual(envelope["payload"]["taskAchievementScore"], 6.5)
        self.assertEqual(envelope["payload"]["coherenceCohesionScore"], 6.0)
        self.assertEqual(envelope["payload"]["lexicalResourceScore"], 6.5)
        self.assertEqual(envelope["payload"]["grammaticalRangeScore"], 6.0)
        self.assertEqual(envelope["payload"]["overallBand"], 6.5)

    async def test_publish_failed_success(self):
        submission_id = uuid4()
        await self.publisher.publish_failed(
            submission_id=submission_id,
            error_code="GEMINI_API_ERROR",
            error_msg="Rate limit exceeded",
            is_retriable=False,
            trace_id="test-trace-456",
            correlation_id=str(submission_id)
        )

        self.mock_producer.send_and_wait.assert_called_once()
        args, kwargs = self.mock_producer.send_and_wait.call_args
        self.assertEqual(args[0], "engonow.writing.evaluation-failed.v1")
        self.assertEqual(kwargs["key"], str(submission_id).encode("utf-8"))

        envelope = json.loads(kwargs["value"].decode("utf-8"))
        self.assertEqual(envelope["eventType"], "WRITING_EVALUATION_FAILED")
        self.assertEqual(envelope["payload"]["submissionId"], str(submission_id))
        self.assertEqual(envelope["payload"]["errorCode"], "GEMINI_API_ERROR")
        self.assertEqual(envelope["payload"]["errorMessage"], "Rate limit exceeded")
        self.assertFalse(envelope["payload"]["isRetriable"])
