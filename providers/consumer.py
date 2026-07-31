"""Asynchronous event transport abstractions for the speaking AI worker."""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping
from typing import Any


logger = logging.getLogger("engonow.ai_worker.consumer")

EventPayload = dict[str, Any]
EventHandler = Callable[[EventPayload], Awaitable[EventPayload]]
ResultPublisher = Callable[[EventPayload], Awaitable[None]]

_LOCAL_STOP = object()


class BaseEventConsumer(ABC):
    """Lifecycle and listening contract implemented by every request transport."""

    @abstractmethod
    async def start(self) -> None:
        """Allocate transport resources."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop intake and wait for active message handling to finish."""

    @abstractmethod
    async def start_listening(
        self,
        handler: EventHandler,
        publisher: ResultPublisher,
    ) -> None:
        """Consume events until stopped, publishing one result per event."""


class BaseEventPublisher(ABC):
    """Lifecycle and publication contract for result transports."""

    @abstractmethod
    async def start(self) -> None:
        """Allocate transport resources."""

    @abstractmethod
    async def stop(self) -> None:
        """Flush and release transport resources."""

    @abstractmethod
    async def publish(self, payload: EventPayload) -> None:
        """Publish a result payload."""


class LocalEventBroker:
    """In-process topic channels backed by non-blocking ``asyncio.Queue`` objects."""

    def __init__(self) -> None:
        self._topics: defaultdict[str, asyncio.Queue[object]] = defaultdict(
            asyncio.Queue
        )

    async def publish(
        self,
        topic: str,
        payload: Mapping[str, Any],
    ) -> None:
        await self._topics[topic].put(dict(payload))

    async def receive(self, topic: str) -> EventPayload:
        message = await self._topics[topic].get()
        self._topics[topic].task_done()
        if not isinstance(message, dict):
            raise TypeError(f"Local topic '{topic}' received a non-event message")
        return message

    def queue(self, topic: str) -> asyncio.Queue[object]:
        """Return a topic queue for consumer coordination and test instrumentation."""
        return self._topics[topic]


class LocalEventConsumer(BaseEventConsumer):
    """Concurrent local consumer used by tests and dependency-free benchmarks."""

    def __init__(
        self,
        broker: LocalEventBroker,
        topic: str,
        max_in_flight: int = 5,
    ) -> None:
        if max_in_flight < 1:
            raise ValueError("max_in_flight must be at least 1")
        self._broker = broker
        self._topic = topic
        self._max_in_flight = max_in_flight
        self._running = False
        self._listener_task: asyncio.Task[Any] | None = None
        self._stopped = asyncio.Event()
        self._active_tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        self._running = True
        self._stopped.clear()

    async def stop(self) -> None:
        if self._running:
            self._running = False
            await self._broker.queue(self._topic).put(_LOCAL_STOP)

        listener_task = self._listener_task
        if (
            listener_task is not None
            and listener_task is not asyncio.current_task()
            and not listener_task.done()
        ):
            await self._stopped.wait()
        else:
            await self._drain_active_tasks()

    async def enqueue(self, payload: Mapping[str, Any]) -> None:
        """Publish a request to this consumer's local input topic."""
        await self._broker.publish(self._topic, payload)

    async def start_listening(
        self,
        handler: EventHandler,
        publisher: ResultPublisher,
    ) -> None:
        await self.start()
        self._listener_task = asyncio.current_task()
        capacity = asyncio.Semaphore(self._max_in_flight)
        request_queue = self._broker.queue(self._topic)

        try:
            while True:
                message = await request_queue.get()
                if message is _LOCAL_STOP:
                    request_queue.task_done()
                    break
                if not isinstance(message, dict):
                    request_queue.task_done()
                    logger.error(
                        "[LOCAL CONSUMER] Ignoring non-dictionary event on topic %s",
                        self._topic,
                    )
                    continue

                await capacity.acquire()
                task = asyncio.create_task(
                    self._handle_local_message(
                        message,
                        handler,
                        publisher,
                        request_queue,
                        capacity,
                    )
                )
                self._active_tasks.add(task)
                task.add_done_callback(self._active_tasks.discard)
        finally:
            self._running = False
            await self._drain_active_tasks()
            self._stopped.set()

    async def _handle_local_message(
        self,
        message: EventPayload,
        handler: EventHandler,
        publisher: ResultPublisher,
        request_queue: asyncio.Queue[object],
        capacity: asyncio.Semaphore,
    ) -> None:
        try:
            result = await handler(message)
            await publisher(result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "[LOCAL CONSUMER] Event handling failed on topic %s",
                self._topic,
            )
        finally:
            request_queue.task_done()
            capacity.release()

    async def _drain_active_tasks(self) -> None:
        if self._active_tasks:
            await asyncio.gather(*tuple(self._active_tasks), return_exceptions=True)


class LocalEventPublisher(BaseEventPublisher):
    """Result publisher targeting a ``LocalEventBroker`` topic."""

    def __init__(self, broker: LocalEventBroker, topic: str) -> None:
        self._broker = broker
        self._topic = topic

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def publish(self, payload: EventPayload) -> None:
        await self._broker.publish(self._topic, payload)


class KafkaEventConsumer(BaseEventConsumer):
    """Kafka request consumer with manual contiguous offset commits."""

    def __init__(
        self,
        topic: str,
        bootstrap_servers: str,
        consumer_group: str,
        max_batch_size: int = 5,
    ) -> None:
        if max_batch_size < 1:
            raise ValueError("max_batch_size must be at least 1")
        self._topic = topic
        self._bootstrap_servers = bootstrap_servers
        self._consumer_group = consumer_group
        self._max_batch_size = max_batch_size
        self._consumer: Any = None
        self._offset_and_metadata_type: Any = None
        self._topic_partition_type: Any = None
        self._running = False
        self._listener_task: asyncio.Task[Any] | None = None
        self._stopped = asyncio.Event()

    async def start(self) -> None:
        if self._consumer is not None:
            self._running = True
            return

        try:
            from aiokafka import AIOKafkaConsumer
            from aiokafka.structs import OffsetAndMetadata, TopicPartition
        except ImportError as exc:
            raise RuntimeError(
                "BROKER_TYPE=KAFKA requires aiokafka. "
                "Install it with: pip install -r requirements-worker.txt"
            ) from exc

        self._consumer = AIOKafkaConsumer(
            self._topic,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._consumer_group,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        self._offset_and_metadata_type = OffsetAndMetadata
        self._topic_partition_type = TopicPartition
        await self._consumer.start()
        self._running = True
        self._stopped.clear()
        logger.info(
            "[KAFKA CONSUMER] Listening topic=%s group=%s",
            self._topic,
            self._consumer_group,
        )

    async def stop(self) -> None:
        self._running = False
        listener_task = self._listener_task
        if (
            listener_task is not None
            and listener_task is not asyncio.current_task()
            and not listener_task.done()
        ):
            await self._stopped.wait()
        else:
            await self._close_consumer()

    async def start_listening(
        self,
        handler: EventHandler,
        publisher: ResultPublisher,
    ) -> None:
        await self.start()
        self._listener_task = asyncio.current_task()

        try:
            while self._running:
                batches = await self._consumer.getmany(
                    timeout_ms=1000,
                    max_records=self._max_batch_size,
                )
                records = [
                    record
                    for partition_records in batches.values()
                    for record in partition_records
                ]
                if not records:
                    continue

                outcomes = await asyncio.gather(
                    *(
                        self._handle_kafka_record(record, handler, publisher)
                        for record in records
                    ),
                    return_exceptions=True,
                )
                await self._commit_contiguous_offsets(records, outcomes)
        finally:
            self._running = False
            await self._close_consumer()
            self._stopped.set()

    async def _handle_kafka_record(
        self,
        record: Any,
        handler: EventHandler,
        publisher: ResultPublisher,
    ) -> None:
        raw_value = record.value
        if isinstance(raw_value, bytes):
            raw_value = raw_value.decode("utf-8")
        payload = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
        if not isinstance(payload, dict):
            raise ValueError(
                f"Kafka event at offset {record.offset} must be a JSON object"
            )

        result = await handler(payload)
        await publisher(result)

    async def _commit_contiguous_offsets(
        self,
        records: list[Any],
        outcomes: list[Any],
    ) -> None:
        indexed_by_partition: defaultdict[Any, list[tuple[Any, Any]]] = defaultdict(
            list
        )
        for record, outcome in zip(records, outcomes):
            topic_partition = self._topic_partition_type(
                record.topic,
                record.partition,
            )
            indexed_by_partition[topic_partition].append((record, outcome))

        commit_offsets: dict[Any, Any] = {}
        for partition, partition_outcomes in indexed_by_partition.items():
            partition_outcomes.sort(key=lambda item: item[0].offset)
            last_successful_offset: int | None = None
            first_failed_offset: int | None = None

            for record, outcome in partition_outcomes:
                if isinstance(outcome, BaseException):
                    first_failed_offset = record.offset
                    logger.error(
                        "[KAFKA CONSUMER] Processing failed topic=%s "
                        "partition=%s offset=%s: %s",
                        record.topic,
                        record.partition,
                        record.offset,
                        outcome,
                    )
                    break
                last_successful_offset = record.offset

            if last_successful_offset is not None:
                commit_offsets[partition] = self._offset_and_metadata_type(
                    last_successful_offset + 1,
                    "",
                )
            if first_failed_offset is not None:
                self._consumer.seek(partition, first_failed_offset)

        if commit_offsets:
            await self._consumer.commit(commit_offsets)

    async def _close_consumer(self) -> None:
        if self._consumer is not None:
            consumer = self._consumer
            self._consumer = None
            await consumer.stop()


class KafkaEventPublisher(BaseEventPublisher):
    """Kafka result publisher configured for acknowledged delivery."""

    def __init__(self, topic: str, bootstrap_servers: str) -> None:
        self._topic = topic
        self._bootstrap_servers = bootstrap_servers
        self._producer: Any = None

    async def start(self) -> None:
        if self._producer is not None:
            return
        try:
            from aiokafka import AIOKafkaProducer
        except ImportError as exc:
            raise RuntimeError(
                "BROKER_TYPE=KAFKA requires aiokafka. "
                "Install it with: pip install -r requirements-worker.txt"
            ) from exc

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            acks="all",
        )
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer is not None:
            producer = self._producer
            self._producer = None
            await producer.stop()

    async def publish(self, payload: EventPayload) -> None:
        if self._producer is None:
            raise RuntimeError("Kafka result publisher has not been started")
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        await self._producer.send_and_wait(self._topic, serialized)
