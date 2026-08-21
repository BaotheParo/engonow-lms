import asyncio
import logging
import json
import os
from uuid import UUID
from datetime import datetime, timezone
from typing import Set, Optional
import asyncpg
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.coordinator.assignors.sticky.sticky_assignor import StickyPartitionAssignor

from models.events import EventEnvelope, WritingEvaluationRequestedPayload
from db.inbox_repository import try_acquire_inbox, mark_inbox_completed, mark_inbox_failed
from providers.gemini_writing_provider import GeminiWritingProvider
from workers.outbox_publisher import WritingResultEventPublisher

# Custom logging adapter to inject traceId and idempotencyKey dynamically
class TraceLogAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.get("extra", {})
        trace_id = self.extra.get("traceId") or extra.get("traceId") or "-"
        idempotency_key = self.extra.get("idempotencyKey") or extra.get("idempotencyKey") or "-"
        msg_formatted = f"[traceId={trace_id} idempotencyKey={idempotency_key}] {msg}"
        return msg_formatted, kwargs

logger = TraceLogAdapter(logging.getLogger(__name__), {})

class WritingEvaluationConsumer:
    def __init__(
        self,
        db_pool: asyncpg.Pool,
        writing_provider: GeminiWritingProvider,
        concurrency_limit: int = 8,
        bootstrap_servers: str = "localhost:9092"
    ):
        self.db_pool = db_pool
        self.writing_provider = writing_provider
        self.concurrency_limit = concurrency_limit
        self.bootstrap_servers = bootstrap_servers
        self.semaphore = asyncio.Semaphore(concurrency_limit)
        
        # In-flight task tracker to avoid GC collection & manage lifecycle
        self.active_tasks: Set[asyncio.Task] = set()
        self.running = False
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.producer: Optional[AIOKafkaProducer] = None
        self.outbox_publisher: Optional[WritingResultEventPublisher] = None
        self._consume_task: Optional[asyncio.Task] = None

    async def start(self):
        self.running = True
        logger.info("Starting Writing Evaluation Consumer group_id=engonow-ai-writing-worker-v1")
        
        group_instance_id = os.getenv("KAFKA_GROUP_INSTANCE_ID")

        self.consumer = AIOKafkaConsumer(
            "engonow.writing.evaluation-requested.v1",
            bootstrap_servers=self.bootstrap_servers,
            group_id="engonow-ai-writing-worker-v1",
            group_instance_id=group_instance_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            max_poll_interval_ms=300000,
            partition_assignment_strategy=[StickyPartitionAssignor],
            session_timeout_ms=45000,
            heartbeat_interval_ms=15000
        )

        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers
        )

        await self.consumer.start()
        await self.producer.start()
        self.outbox_publisher = WritingResultEventPublisher(self.producer)
        
        logger.info("Kafka consumer and producer started successfully")
        self._consume_task = asyncio.create_task(self._consume_loop())

    async def stop(self):
        logger.info("Initiating graceful shutdown sequence...")
        self.running = False

        # Step 1: Stop polling new Kafka messages
        if self.consumer:
            logger.info("Stopping Kafka consumer...")
            await self.consumer.stop()

        # Step 2: Await and drain all active in-flight worker tasks
        if self.active_tasks:
            logger.info("Waiting for %d in-flight tasks to complete...", len(self.active_tasks))
            await asyncio.gather(*self.active_tasks, return_exceptions=True)

        if self._consume_task and not self._consume_task.done():
            self._consume_task.cancel()
            try:
                await self._consume_task
            except asyncio.CancelledError:
                pass

        # Step 3: Stop Kafka producer ONLY after all in-flight tasks have finished publishing
        if self.producer:
            logger.info("Stopping Kafka producer...")
            await self.producer.stop()
            
        logger.info("Writing Evaluation Consumer stopped cleanly")

    async def _consume_loop(self):
        """
        Resilient consumer loop wrapped in a supervisor with backoff to recover from disconnects.
        """
        backoff_seconds = 1
        while self.running:
            try:
                async for msg in self.consumer:
                    if not self.running:
                        break

                    backoff_seconds = 1  # Reset backoff on successful read
                    await self._handle_message(msg)

                # Clean exit when consumer finishes without errors
                break

            except asyncio.CancelledError:
                break
            except Exception as e:
                if self.running:
                    logger.error(
                        "Unexpected error in consumer loop: %s. Re-polling in %d seconds...",
                        str(e), backoff_seconds
                    )
                    await asyncio.sleep(backoff_seconds)
                    backoff_seconds = min(backoff_seconds * 2, 30)

    async def _handle_message(self, msg):
        # Extract tracing headers
        headers = {}
        if msg.headers:
            for k, v in msg.headers:
                try:
                    headers[k] = v.decode('utf-8')
                except Exception:
                    headers[k] = str(v)

        trace_id = headers.get("traceId") or headers.get("traceparent")
        correlation_id = headers.get("correlationId")
        
        # Check for poison pill (malformed JSON)
        try:
            payload_dict = json.loads(msg.value.decode('utf-8'))
        except Exception as ex:
            await self._route_to_dlq(msg, f"Malformed JSON: {str(ex)}", trace_id, correlation_id)
            return

        # Schema validation
        try:
            envelope = EventEnvelope.model_validate(payload_dict)
        except Exception as ex:
            await self._route_to_dlq(msg, f"Schema validation failed: {str(ex)}", trace_id, correlation_id)
            return

        # Add tracing details to current context
        envelope.traceId = envelope.traceId or trace_id
        envelope.correlationId = envelope.correlationId or correlation_id

        # Deduplication logic via Inbox Table
        async with self.db_pool.acquire() as conn:
            is_new = await try_acquire_inbox(conn, envelope)
            
        if not is_new:
            logger.info(
                "Duplicate message detected. Skipping processing.",
                extra={"traceId": envelope.traceId, "idempotencyKey": str(envelope.idempotencyKey)}
            )
            # Deduplicated message - commit offset immediately
            await self.consumer.commit()
            return

        # Successfully recorded in Inbox - commit offset to satisfy manual commit policy
        await self.consumer.commit()

        # Dispatch CPU/LLM bound generation in background task
        task = asyncio.create_task(self._process_evaluation_task(envelope))
        self.active_tasks.add(task)
        task.add_done_callback(self.active_tasks.discard)

    async def _route_to_dlq(self, msg, reason: str, trace_id: str, correlation_id: str):
        logger.critical(
            "Poison Pill message detected on partition %d offset %d: %s",
            msg.partition, msg.offset, reason,
            extra={"traceId": trace_id or "-", "idempotencyKey": "-"}
        )
        dlq_headers = [
            ("x-dead-letter-reason", reason.encode('utf-8')),
            ("x-original-topic", b"engonow.writing.evaluation-requested.v1"),
            ("x-failed-at", datetime.now(timezone.utc).isoformat().encode('utf-8')),
            ("partition", str(msg.partition).encode('utf-8')),
            ("offset", str(msg.offset).encode('utf-8'))
        ]
        if trace_id:
            dlq_headers.append(("traceId", trace_id.encode('utf-8')))
        if correlation_id:
            dlq_headers.append(("correlationId", correlation_id.encode('utf-8')))

        try:
            await self.producer.send_and_wait(
                "engonow.writing.evaluation-requested.v1.dlq",
                key=msg.key,
                value=msg.value,
                headers=dlq_headers
            )
            # Commit offset to skip poison pill
            await self.consumer.commit()
        except Exception as ex:
            logger.error("Failed to publish poison pill to DLQ: %s", str(ex))

    async def _process_evaluation_task(self, envelope: EventEnvelope):
        async with self.semaphore:
            logger.info(
                "Starting essay evaluation task",
                extra={"traceId": envelope.traceId, "idempotencyKey": str(envelope.idempotencyKey)}
            )
            payload = envelope.payload
            try:
                # Call external Gemini LLM via provider
                evaluation_result = await self.writing_provider.evaluate_essay(
                    task_type=payload.taskType.value,
                    task_prompt=payload.taskPrompt,
                    essay_text=payload.essayText
                )

                # 1. Publish completion event to Kafka
                if self.outbox_publisher:
                    await self.outbox_publisher.publish_completed(
                        submission_id=payload.submissionId,
                        raw_evaluation=evaluation_result,
                        trace_id=envelope.traceId,
                        correlation_id=envelope.correlationId,
                        original_idempotency_key=envelope.idempotencyKey
                    )

                # 2. Update Inbox row to PROCESSED
                async with self.db_pool.acquire() as conn:
                    await mark_inbox_completed(conn, envelope.idempotencyKey)

                logger.info(
                    "Successfully processed writing evaluation and published completion event.",
                    extra={"traceId": envelope.traceId, "idempotencyKey": str(envelope.idempotencyKey)}
                )

            except Exception as ex:
                logger.error(
                    "Error occurred during essay evaluation: %s", str(ex),
                    extra={"traceId": envelope.traceId, "idempotencyKey": str(envelope.idempotencyKey)}
                )
                
                # Check for transient failures (e.g. rate limit, gateway timeouts)
                is_retriable = self._check_is_retriable(ex)
                
                try:
                    if is_retriable and envelope.retryCount < 3:
                        await self._route_to_retry(envelope, str(ex))
                    else:
                        await self._route_to_failed(envelope, str(ex))
                except Exception as route_ex:
                    logger.critical(
                        "Fatal failure during error routing: %s. Forcing inbox row to FAILED.",
                        str(route_ex),
                        extra={"traceId": envelope.traceId, "idempotencyKey": str(envelope.idempotencyKey)}
                    )
                    try:
                        async with self.db_pool.acquire() as conn:
                            await mark_inbox_failed(conn, envelope.idempotencyKey, f"Fatal route error: {route_ex}")
                    except Exception:
                        pass

    def _check_is_retriable(self, ex: Exception) -> bool:
        # Simple heuristic mapping for typical Gemini transient exceptions
        error_msg = str(ex).lower()
        return "429" in error_msg or "503" in error_msg or "timeout" in error_msg or "rate limit" in error_msg

    async def _route_to_retry(self, envelope: EventEnvelope, error_msg: str):
        envelope.retryCount += 1
        logger.warning(
            "Transient error. Routing to retry topic attempt=%d error=%s",
            envelope.retryCount, error_msg,
            extra={"traceId": envelope.traceId, "idempotencyKey": str(envelope.idempotencyKey)}
        )
        
        try:
            # Update retry count and error details in Inbox
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE inbox_events SET retry_count = $1, error_message = $2 WHERE idempotency_key = $3",
                    envelope.retryCount, error_msg, envelope.idempotencyKey
                )
            
            headers = [
                ("traceId", envelope.traceId.encode('utf-8') if envelope.traceId else b""),
                ("correlationId", envelope.correlationId.encode('utf-8') if envelope.correlationId else b""),
                ("idempotencyKey", str(envelope.idempotencyKey).encode('utf-8'))
            ]
            
            await self.producer.send_and_wait(
                "engonow.writing.evaluation-requested.v1.retry.30s",
                key=str(envelope.payload.submissionId).encode('utf-8'),
                value=envelope.model_dump_json().encode('utf-8'),
                headers=headers
            )
        except Exception as ex:
            logger.error("Failed to publish to retry topic: %s", str(ex))
            raise

    async def _route_to_failed(self, envelope: EventEnvelope, error_msg: str):
        logger.error(
            "Permanent failure. Routing to evaluation-failed topic error=%s",
            error_msg,
            extra={"traceId": envelope.traceId, "idempotencyKey": str(envelope.idempotencyKey)}
        )

        try:
            if self.outbox_publisher:
                await self.outbox_publisher.publish_failed(
                    submission_id=envelope.payload.submissionId,
                    error_code="EVALUATION_FAILED",
                    error_msg=error_msg,
                    is_retriable=False,
                    trace_id=envelope.traceId,
                    correlation_id=envelope.correlationId
                )

            async with self.db_pool.acquire() as conn:
                await mark_inbox_failed(conn, envelope.idempotencyKey, error_msg)

        except Exception as ex:
            logger.error("Failed to publish to evaluation-failed topic: %s", str(ex))
            raise
