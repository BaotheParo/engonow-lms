import json
import logging
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)

class WritingResultEventPublisher:
    def __init__(self, producer: AIOKafkaProducer):
        self.producer = producer

    async def publish_completed(
        self,
        submission_id: UUID,
        raw_evaluation: Dict[str, Any],
        trace_id: Optional[str],
        correlation_id: Optional[str],
        original_idempotency_key: Optional[UUID] = None
    ) -> None:
        """
        Publishes a canonical WRITING_EVALUATION_COMPLETED event to Kafka.
        """
        event_id = uuid4()
        idempotency_key = uuid4()  # Minted for reverse flow deduplication
        now = datetime.now(timezone.utc).isoformat()

        # Extract criterion scores from evaluation output
        criteria = raw_evaluation.get("criteria", {})
        ta_score = float(criteria.get("TASK_ACHIEVEMENT", {}).get("band") or criteria.get("TASK_RESPONSE", {}).get("band") or 6.0)
        cc_score = float(criteria.get("COHERENCE_COHESION", {}).get("band") or 6.0)
        lr_score = float(criteria.get("LEXICAL_RESOURCE", {}).get("band") or 6.0)
        gra_score = float(criteria.get("GRAMMATICAL_RANGE_ACCURACY", {}).get("band") or 6.0)
        
        # Calculate raw average for reference; Java Core LMS will perform official Cambridge rounding
        raw_avg = (ta_score + cc_score + lr_score + gra_score) / 4.0
        overall_band = raw_evaluation.get("overallBand") or round(raw_avg * 2) / 2.0

        feedback_detail = raw_evaluation.get("feedbackDetail") or raw_evaluation

        payload = {
            "submissionId": str(submission_id),
            "taskAchievementScore": ta_score,
            "coherenceCohesionScore": cc_score,
            "lexicalResourceScore": lr_score,
            "grammaticalRangeScore": gra_score,
            "overallBand": float(overall_band),
            "feedbackDetail": feedback_detail
        }

        envelope = {
            "eventId": str(event_id),
            "idempotencyKey": str(idempotency_key),
            "eventType": "WRITING_EVALUATION_COMPLETED",
            "schemaVersion": "1.0",
            "occurredAt": now,
            "producedAt": now,
            "traceId": trace_id or "-",
            "correlationId": correlation_id or str(submission_id),
            "source": "engonow-ai-writing-service",
            "retryCount": 0,
            "payload": payload
        }

        headers = [
            ("eventId", str(event_id).encode("utf-8")),
            ("idempotencyKey", str(idempotency_key).encode("utf-8")),
            ("eventType", b"WRITING_EVALUATION_COMPLETED"),
            ("schemaVersion", b"1.0"),
            ("traceId", (trace_id or "-").encode("utf-8")),
            ("correlationId", (correlation_id or str(submission_id)).encode("utf-8"))
        ]

        logger.info(
            "[OUTBOX PUBLISHER] Publishing WRITING_EVALUATION_COMPLETED event for submissionId=%s eventId=%s idempotencyKey=%s",
            submission_id, event_id, idempotency_key,
            extra={"traceId": trace_id, "idempotencyKey": str(idempotency_key)}
        )

        await self.producer.send_and_wait(
            "engonow.writing.evaluation-completed.v1",
            key=str(submission_id).encode("utf-8"),
            value=json.dumps(envelope).encode("utf-8"),
            headers=headers
        )

    async def publish_failed(
        self,
        submission_id: UUID,
        error_code: str,
        error_msg: str,
        is_retriable: bool,
        trace_id: Optional[str],
        correlation_id: Optional[str] = None
    ) -> None:
        """
        Publishes a canonical WRITING_EVALUATION_FAILED event to Kafka.
        """
        event_id = uuid4()
        idempotency_key = uuid4()
        now = datetime.now(timezone.utc).isoformat()

        payload = {
            "submissionId": str(submission_id),
            "errorCode": error_code,
            "errorMessage": error_msg,
            "isRetriable": is_retriable,
            "failedAt": now
        }

        envelope = {
            "eventId": str(event_id),
            "idempotencyKey": str(idempotency_key),
            "eventType": "WRITING_EVALUATION_FAILED",
            "schemaVersion": "1.0",
            "occurredAt": now,
            "producedAt": now,
            "traceId": trace_id or "-",
            "correlationId": correlation_id or str(submission_id),
            "source": "engonow-ai-writing-service",
            "retryCount": 0,
            "payload": payload
        }

        headers = [
            ("eventId", str(event_id).encode("utf-8")),
            ("idempotencyKey", str(idempotency_key).encode("utf-8")),
            ("eventType", b"WRITING_EVALUATION_FAILED"),
            ("schemaVersion", b"1.0"),
            ("traceId", (trace_id or "-").encode("utf-8")),
            ("correlationId", (correlation_id or str(submission_id)).encode("utf-8"))
        ]

        logger.error(
            "[OUTBOX PUBLISHER] Publishing WRITING_EVALUATION_FAILED event for submissionId=%s error=%s",
            submission_id, error_msg,
            extra={"traceId": trace_id, "idempotencyKey": str(idempotency_key)}
        )

        await self.producer.send_and_wait(
            "engonow.writing.evaluation-failed.v1",
            key=str(submission_id).encode("utf-8"),
            value=json.dumps(envelope).encode("utf-8"),
            headers=headers
        )
