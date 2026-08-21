import json
import logging
from datetime import datetime, timezone
from typing import Optional, Any
from aiokafka import AIOKafkaProducer

from models.events import EventEnvelope

logger = logging.getLogger(__name__)

class NonRetriableProcessingError(Exception):
    """Errors that cannot be resolved by retrying (e.g. malformed JSON, schema violation)."""
    pass

class RetriableProcessingError(Exception):
    """Transient errors that may resolve with backoff (e.g. HTTP 429, HTTP 503, timeouts)."""
    pass

class ResilientRoutingHandler:
    def __init__(self, producer: AIOKafkaProducer):
        self.producer = producer

    async def handle_processing_error(
        self,
        exc: Exception,
        raw_record: Any,
        envelope: Optional[EventEnvelope] = None
    ) -> str:
        """
        Routes the failed message to either a non-blocking retry topic or DLQ.
        Returns the routing destination: 'RETRY' or 'DLQ'.
        """
        topic = getattr(raw_record, "topic", "engonow.writing.evaluation-requested.v1")
        partition = str(getattr(raw_record, "partition", 0))
        offset = str(getattr(raw_record, "offset", 0))
        key = getattr(raw_record, "key", None)
        value = getattr(raw_record, "value", None)

        now = datetime.now(timezone.utc).isoformat()
        trace_id = envelope.traceId if (envelope and envelope.traceId) else "-"
        correlation_id = envelope.correlationId if (envelope and envelope.correlationId) else "-"

        # 1. Non-retriable error or unparseable envelope -> Send to DLQ immediately
        if isinstance(exc, NonRetriableProcessingError) or envelope is None:
            reason = str(exc)
            logger.critical(
                "[DLQ ROUTED] Poison-pill message routed to DLQ topic=engonow.writing.evaluation-requested.v1.dlq partition=%s offset=%s error=%s",
                partition, offset, reason,
                extra={"traceId": trace_id, "idempotencyKey": str(envelope.idempotencyKey) if envelope else "-"}
            )

            dlq_headers = [
                ("x-dead-letter-reason", reason.encode("utf-8")),
                ("x-original-topic", topic.encode("utf-8") if isinstance(topic, str) else topic),
                ("x-original-partition", partition.encode("utf-8")),
                ("x-original-offset", offset.encode("utf-8")),
                ("x-failed-at", now.encode("utf-8")),
                ("traceId", trace_id.encode("utf-8")),
                ("correlationId", correlation_id.encode("utf-8"))
            ]

            await self.producer.send_and_wait(
                "engonow.writing.evaluation-requested.v1.dlq",
                key=key,
                value=value if isinstance(value, bytes) else str(value).encode("utf-8"),
                headers=dlq_headers
            )
            return "DLQ"

        # 2. Retriable error with remaining retry budget -> Route to 30s retry topic
        if isinstance(exc, RetriableProcessingError) and envelope.retryCount < 3:
            envelope.retryCount += 1
            envelope.producedAt = datetime.now(timezone.utc)
            
            logger.warning(
                "[RETRY SCHEDULED] Message retry #%d scheduled on retry topic for submissionId=%s error=%s",
                envelope.retryCount, envelope.payload.submissionId, str(exc),
                extra={"traceId": trace_id, "idempotencyKey": str(envelope.idempotencyKey)}
            )

            retry_headers = [
                ("x-retry-delay-ms", b"30000"),
                ("x-original-topic", topic.encode("utf-8") if isinstance(topic, str) else topic),
                ("x-original-partition", partition.encode("utf-8")),
                ("x-original-offset", offset.encode("utf-8")),
                ("x-failed-at", now.encode("utf-8")),
                ("traceId", trace_id.encode("utf-8")),
                ("correlationId", correlation_id.encode("utf-8")),
                ("idempotencyKey", str(envelope.idempotencyKey).encode("utf-8"))
            ]

            await self.producer.send_and_wait(
                "engonow.writing.evaluation-requested.v1.retry.30s",
                key=key or str(envelope.payload.submissionId).encode("utf-8"),
                value=envelope.model_dump_json().encode("utf-8"),
                headers=retry_headers
            )
            return "RETRY"

        # 3. Retries exhausted (retryCount >= 3) -> Escalate to DLQ
        exhausted_reason = f"MAX_RETRIES_EXCEEDED: {str(exc)}"
        logger.critical(
            "[DLQ ROUTED - RETRIES EXHAUSTED] Message exceeded max retries (%d). Routing to DLQ. error=%s",
            envelope.retryCount, str(exc),
            extra={"traceId": trace_id, "idempotencyKey": str(envelope.idempotencyKey)}
        )

        dlq_headers = [
            ("x-dead-letter-reason", exhausted_reason.encode("utf-8")),
            ("x-original-topic", topic.encode("utf-8") if isinstance(topic, str) else topic),
            ("x-original-partition", partition.encode("utf-8")),
            ("x-original-offset", offset.encode("utf-8")),
            ("x-failed-at", now.encode("utf-8")),
            ("traceId", trace_id.encode("utf-8")),
            ("correlationId", correlation_id.encode("utf-8")),
            ("idempotencyKey", str(envelope.idempotencyKey).encode("utf-8"))
        ]

        await self.producer.send_and_wait(
            "engonow.writing.evaluation-requested.v1.dlq",
            key=key or str(envelope.payload.submissionId).encode("utf-8"),
            value=envelope.model_dump_json().encode("utf-8"),
            headers=dlq_headers
        )
        return "DLQ"
