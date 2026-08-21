import asyncio
import logging
import json
import os
from datetime import datetime, timezone
from typing import Optional, Set, Dict
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from aiokafka.coordinator.assignors.sticky.sticky_assignor import StickyPartitionAssignor

from models.events import EventEnvelope

logger = logging.getLogger(__name__)

class WritingRetryConsumer:
    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        retry_delay_seconds: float = 30.0,
        max_concurrent_retries: int = 16
    ):
        self.bootstrap_servers = bootstrap_servers
        self.retry_delay_seconds = retry_delay_seconds
        self.semaphore = asyncio.Semaphore(max_concurrent_retries)
        self.running = False
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.producer: Optional[AIOKafkaProducer] = None
        self._consume_task: Optional[asyncio.Task] = None
        self.active_tasks: Set[asyncio.Task] = set()
        self._offset_lock = asyncio.Lock()
        self._highest_committed_offsets: Dict[TopicPartition, int] = {}

    async def start(self):
        self.running = True
        logger.info("Starting Writing Retry Consumer on topic=engonow.writing.evaluation-requested.v1.retry.30s")

        group_instance_id = os.getenv("KAFKA_RETRY_GROUP_INSTANCE_ID")

        self.consumer = AIOKafkaConsumer(
            "engonow.writing.evaluation-requested.v1.retry.30s",
            bootstrap_servers=self.bootstrap_servers,
            group_id="engonow-ai-writing-retry-worker-v1",
            group_instance_id=group_instance_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
            partition_assignment_strategy=[StickyPartitionAssignor],
            session_timeout_ms=45000,
            heartbeat_interval_ms=15000
        )

        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers
        )

        await self.consumer.start()
        await self.producer.start()

        self._consume_task = asyncio.create_task(self._consume_loop())
        logger.info("Writing Retry Consumer started successfully")

    async def stop(self):
        logger.info("Stopping Writing Retry Consumer...")
        self.running = False

        # 1. Stop polling new messages
        if self.consumer:
            logger.info("Stopping Kafka consumer...")
            await self.consumer.stop()

        # 2. Drain in-flight delayed retry tasks (allowing pending publishes to finish)
        if self.active_tasks:
            logger.info("Waiting for %d in-flight retry delay tasks to complete...", len(self.active_tasks))
            await asyncio.gather(*self.active_tasks, return_exceptions=True)

        if self._consume_task and not self._consume_task.done():
            self._consume_task.cancel()
            try:
                await self._consume_task
            except asyncio.CancelledError:
                pass

        # 3. Safely stop producer after tasks finish publishing
        if self.producer:
            logger.info("Stopping Kafka producer...")
            await self.producer.stop()

        logger.info("Writing Retry Consumer stopped cleanly")

    async def _consume_loop(self):
        backoff_seconds = 1
        while self.running:
            try:
                async for msg in self.consumer:
                    if not self.running:
                        break

                    backoff_seconds = 1

                    # Offload delayed wait and dispatch to non-blocking background task
                    task = asyncio.create_task(self._process_delayed_retry(msg))
                    self.active_tasks.add(task)
                    task.add_done_callback(self.active_tasks.discard)

                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self.running:
                    logger.error("Error in retry consumer loop: %s. Backoff %ds...", str(e), backoff_seconds)
                    await asyncio.sleep(backoff_seconds)
                    backoff_seconds = min(backoff_seconds * 2, 30)

    async def _process_delayed_retry(self, msg):
        async with self.semaphore:
            try:
                payload_dict = json.loads(msg.value.decode("utf-8"))
                envelope = EventEnvelope.model_validate(payload_dict)

                now_utc = datetime.now(timezone.utc)
                produced_at = envelope.producedAt
                if produced_at.tzinfo is None:
                    produced_at = produced_at.replace(tzinfo=timezone.utc)

                elapsed_seconds = (now_utc - produced_at).total_seconds()
                remaining_delay = max(0.0, self.retry_delay_seconds - elapsed_seconds)

                if remaining_delay > 0:
                    logger.info(
                        "[RETRY DELAY] Enforcing non-blocking wait of %.1fs for submissionId=%s attempt=%d",
                        remaining_delay, envelope.payload.submissionId, envelope.retryCount
                    )
                    await asyncio.sleep(remaining_delay)

                headers = [
                    ("traceId", envelope.traceId.encode("utf-8") if envelope.traceId else b""),
                    ("correlationId", envelope.correlationId.encode("utf-8") if envelope.correlationId else b""),
                    ("idempotencyKey", str(envelope.idempotencyKey).encode("utf-8")),
                    ("x-replayed-from-retry", b"true")
                ]

                # Re-publish to primary topic for evaluation
                await self.producer.send_and_wait(
                    "engonow.writing.evaluation-requested.v1",
                    key=msg.key,
                    value=envelope.model_dump_json().encode("utf-8"),
                    headers=headers
                )

                logger.info(
                    "[RETRY RE-DISPATCH] Successfully re-submitted retry attempt #%d to primary topic for submissionId=%s",
                    envelope.retryCount, envelope.payload.submissionId
                )

                # Commit Kafka offset ONLY after send_and_wait completes successfully
                await self._commit_partition_offset(msg)

            except Exception as ex:
                logger.error("Failed to re-dispatch retry message on partition %d offset %d: %s",
                             msg.partition, msg.offset, str(ex))
                # For unparseable/fatal poison messages on retry topic, advance offset to prevent poison block
                if isinstance(ex, (json.JSONDecodeError, ValueError)):
                    await self._commit_partition_offset(msg)

    async def _commit_partition_offset(self, msg):
        if not self.consumer:
            return

        tp = TopicPartition(msg.topic, msg.partition)
        target_offset = msg.offset + 1

        async with self._offset_lock:
            highest = self._highest_committed_offsets.get(tp, -1)
            if target_offset > highest:
                try:
                    await self.consumer.commit({tp: target_offset})
                    self._highest_committed_offsets[tp] = target_offset
                except Exception as commit_err:
                    logger.warn("Failed to commit offset %d for %s: %s", target_offset, tp, str(commit_err))
