import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4
from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)

class SpeakingResultEventPublisher:
    """
    Publishes canonical evaluation completed, failed, retry, and DLQ events
    for the IELTS Speaking assessment pipeline.
    """
    def __init__(
        self,
        producer: AIOKafkaProducer,
        completed_topic: str = "engonow.speaking.evaluation-completed.v1",
        failed_topic: str = "engonow.speaking.evaluation-failed.v1",
        retry_topic: str = "engonow.speaking.evaluation-requested.v1.retry.30s",
        dlq_topic: str = "engonow.speaking.evaluation-requested.v1.dlq"
    ):
        self.producer = producer
        self.completed_topic = completed_topic
        self.failed_topic = failed_topic
        self.retry_topic = retry_topic
        self.dlq_topic = dlq_topic

    async def publish_completed(
        self,
        attempt_id: UUID,
        fluency_score: float,
        lexical_score: float,
        grammar_score: float,
        pronunciation_score: float,
        overall_band: float,
        feedback_detail: Dict[str, Any],
        idempotency_key: Optional[UUID] = None,
        trace_id: Optional[str] = None,
        correlation_id: Optional[str] = None
    ):
        now = datetime.now(timezone.utc).isoformat()
        envelope = {
            "eventId": str(uuid4()),
            "idempotencyKey": str(idempotency_key or attempt_id),
            "eventType": "SPEAKING_EVALUATION_COMPLETED",
            "schemaVersion": "1.0",
            "occurredAt": now,
            "producedAt": now,
            "traceId": trace_id or str(uuid4()),
            "correlationId": correlation_id or str(attempt_id),
            "source": "engonow-ai-speaking-worker",
            "retryCount": 0,
            "payload": {
                "attemptId": str(attempt_id),
                "fluencyCoherenceScore": fluency_score,
                "lexicalResourceScore": lexical_score,
                "grammaticalRangeScore": grammar_score,
                "pronunciationScore": pronunciation_score,
                "overallBand": overall_band,
                "feedbackDetail": feedback_detail
            }
        }

        headers = [
            ("eventId", envelope["eventId"].encode("utf-8")),
            ("traceId", (envelope["traceId"] or "").encode("utf-8")),
            ("correlationId", (envelope["correlationId"] or "").encode("utf-8")),
            ("eventType", envelope["eventType"].encode("utf-8")),
        ]

        payload_bytes = json.dumps(envelope).encode("utf-8")
        await self.producer.send_and_wait(
            topic=self.completed_topic,
            key=str(attempt_id).encode("utf-8"),
            value=payload_bytes,
            headers=headers
        )
        logger.info("[SPEAKING PUBLISHER] Published completed event for attempt %s", attempt_id)

    async def publish_failed(
        self,
        attempt_id: UUID,
        error_code: str,
        error_message: str,
        is_retriable: bool,
        idempotency_key: Optional[UUID] = None,
        trace_id: Optional[str] = None,
        correlation_id: Optional[str] = None
    ):
        now = datetime.now(timezone.utc).isoformat()
        envelope = {
            "eventId": str(uuid4()),
            "idempotencyKey": str(idempotency_key or attempt_id),
            "eventType": "SPEAKING_EVALUATION_FAILED",
            "schemaVersion": "1.0",
            "occurredAt": now,
            "producedAt": now,
            "traceId": trace_id or str(uuid4()),
            "correlationId": correlation_id or str(attempt_id),
            "source": "engonow-ai-speaking-worker",
            "retryCount": 0,
            "payload": {
                "attemptId": str(attempt_id),
                "errorCode": error_code,
                "errorMessage": error_message,
                "isRetriable": is_retriable,
                "failedAt": now
            }
        }

        headers = [
            ("eventId", envelope["eventId"].encode("utf-8")),
            ("traceId", (envelope["traceId"] or "").encode("utf-8")),
            ("correlationId", (envelope["correlationId"] or "").encode("utf-8")),
            ("eventType", envelope["eventType"].encode("utf-8")),
        ]

        payload_bytes = json.dumps(envelope).encode("utf-8")
        await self.producer.send_and_wait(
            topic=self.failed_topic,
            key=str(attempt_id).encode("utf-8"),
            value=payload_bytes,
            headers=headers
        )
        logger.info("[SPEAKING PUBLISHER] Published failed event for attempt %s: %s", attempt_id, error_code)

    async def publish_retry(
        self,
        raw_message_bytes: bytes,
        partition_key: bytes,
        retry_count: int,
        headers: list
    ):
        await self.producer.send_and_wait(
            topic=self.retry_topic,
            key=partition_key,
            value=raw_message_bytes,
            headers=headers
        )
        logger.info("[SPEAKING PUBLISHER] Published retry message (attempt %d) to %s", retry_count, self.retry_topic)

    async def publish_dlq(
        self,
        raw_message_bytes: bytes,
        partition_key: bytes,
        headers: list
    ):
        await self.producer.send_and_wait(
            topic=self.dlq_topic,
            key=partition_key,
            value=raw_message_bytes,
            headers=headers
        )
        logger.info("[SPEAKING PUBLISHER] Published poisoned message to DLQ topic %s", self.dlq_topic)
