import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional, Set
from uuid import UUID

import asyncpg
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.coordinator.assignors.sticky.sticky_assignor import StickyPartitionAssignor

from db.inbox_repository import try_acquire_inbox, mark_inbox_completed, mark_inbox_failed
from models.events import EventEnvelope, SpeakingEvaluationRequestedPayload
from workers.speaking_publisher import SpeakingResultEventPublisher

logger = logging.getLogger("workers.speaking_consumer")

class SpeakingEvaluationConsumer:
    """
    Kafka Consumer Worker for IELTS Speaking assessment.
    Implements the Claim-Check pattern (never receives binary audio on Kafka),
    Dual-Inbox Idempotency, and Non-blocking Concurrency Control.
    """
    def __init__(
        self,
        db_pool: Optional[asyncpg.Pool],
        concurrency_limit: int = 8,
        bootstrap_servers: str = "localhost:9092"
    ):
        self.db_pool = db_pool
        self.concurrency_limit = concurrency_limit
        self.bootstrap_servers = bootstrap_servers
        self.semaphore = asyncio.Semaphore(concurrency_limit)
        self.active_tasks: Set[asyncio.Task] = set()
        self.running = False
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.producer: Optional[AIOKafkaProducer] = None
        self.publisher: Optional[SpeakingResultEventPublisher] = None
        self._consume_task: Optional[asyncio.Task] = None

    async def start(self):
        self.running = True
        logger.info("Starting Speaking Evaluation Consumer group_id=engonow-ai-speaking-worker-v1")

        self.consumer = AIOKafkaConsumer(
            "engonow.speaking.evaluation-requested.v1",
            bootstrap_servers=self.bootstrap_servers,
            group_id="engonow-ai-speaking-worker-v1",
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
        self.publisher = SpeakingResultEventPublisher(self.producer)

        logger.info("Speaking Kafka consumer and producer started successfully")
        self._consume_task = asyncio.create_task(self._consume_loop())

    async def stop(self):
        logger.info("Stopping Speaking Evaluation Consumer...")
        self.running = False

        if self.consumer:
            await self.consumer.stop()

        if self.active_tasks:
            logger.info("Waiting for %d active speaking tasks to drain...", len(self.active_tasks))
            await asyncio.gather(*self.active_tasks, return_exceptions=True)

        if self._consume_task and not self._consume_task.done():
            self._consume_task.cancel()
            try:
                await self._consume_task
            except asyncio.CancelledError:
                pass

        if self.producer:
            await self.producer.stop()

        logger.info("Speaking Evaluation Consumer stopped cleanly")

    async def _consume_loop(self):
        try:
            async for record in self.consumer:
                if not self.running:
                    break

                try:
                    await self._process_record(record)
                except Exception as e:
                    logger.error("Error processing record at offset %d: %s", record.offset, str(e), exc_info=True)
                    # Acknowledge offset to prevent poison pill loop
                    await self.consumer.commit()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Unexpected error in speaking consume loop: %s", str(e), exc_info=True)

    async def _process_record(self, record):
        raw_json = record.value.decode("utf-8")
        data = json.loads(raw_json)

        event_id = UUID(data["eventId"])
        idempotency_key = UUID(data["idempotencyKey"])
        trace_id = data.get("traceId")
        correlation_id = data.get("correlationId")

        payload_data = data["payload"]
        attempt_id = UUID(payload_data["attemptId"])

        # 1. Atomic Inbox Acquisition (if db_pool is provided)
        if self.db_pool:
            acquired = await try_acquire_inbox(
                self.db_pool,
                event_id,
                idempotency_key,
                data.get("eventType", "SPEAKING_EVALUATION_REQUESTED"),
                data.get("source", "engonow-lms-backend"),
                raw_json
            )
            if not acquired:
                logger.warning("[DUPLICATE EVENT] IdempotencyKey %s already processed. Skipping.", idempotency_key)
                await self.consumer.commit()
                return

        # 2. Commit offset immediately to acknowledge acquisition
        await self.consumer.commit()

        # 3. Spawn background evaluation coroutine
        task = asyncio.create_task(
            self._evaluate_speaking_task(
                attempt_id=attempt_id,
                idempotency_key=idempotency_key,
                payload_data=payload_data,
                trace_id=trace_id,
                correlation_id=correlation_id
            )
        )
        self.active_tasks.add(task)
        task.add_done_callback(self.active_tasks.discard)

    async def _evaluate_speaking_task(
        self,
        attempt_id: UUID,
        idempotency_key: UUID,
        payload_data: dict,
        trace_id: Optional[str],
        correlation_id: Optional[str]
    ):
        async with self.semaphore:
            try:
                audio_ref = payload_data.get("audioRef", {})
                object_key = audio_ref.get("objectKey", "")
                checksum_sha256 = audio_ref.get("checksumSha256", "")
                duration_seconds = audio_ref.get("durationSeconds", 60.0)

                logger.info("[SPEAKING EVALUATION] Evaluating attempt %s, audioKey=%s, duration=%.1fs",
                    attempt_id, object_key, duration_seconds)

                # Simulated Acoustic & LLM Multimodal Analysis
                await asyncio.sleep(0.05)

                fluency_score = 7.0
                lexical_score = 7.5
                grammar_score = 7.0
                pronunciation_score = 7.0
                overall_band = 7.0

                feedback_detail = {
                    "transcript": "Sample transcript of the student speaking recording...",
                    "speechMetrics": {
                        "wpm": 142.5,
                        "pauseCount": 6,
                        "speechDurationSeconds": float(duration_seconds),
                        "fillerWordsCount": 2,
                        "repetitionCount": 1
                    },
                    "phoneticDiagnostics": [
                        {
                            "word": "development",
                            "expectedIpa": "/dɪˈvel.əp.mənt/",
                            "actualIpa": "/dɪˈvel.əp.mənt/",
                            "timestampMs": 1200,
                            "confidenceScore": 0.95
                        }
                    ],
                    "criteria": [
                        {
                            "criterion": "FLUENCY_COHERENCE",
                            "score": fluency_score,
                            "summary": "Speaks fluently with rare hesitation.",
                            "strengths": ["Good pacing"],
                            "weaknesses": ["Occasional pause"]
                        },
                        {
                            "criterion": "LEXICAL_RESOURCE",
                            "score": lexical_score,
                            "summary": "Wide range of vocabulary used flexibly.",
                            "strengths": ["Idiomatic vocabulary"],
                            "weaknesses": ["Minor collocation error"]
                        },
                        {
                            "criterion": "GRAMMATICAL_RANGE_ACCURACY",
                            "score": grammar_score,
                            "summary": "Mix of simple and complex structures.",
                            "strengths": ["Complex sentences"],
                            "weaknesses": ["Minor tense slip"]
                        },
                        {
                            "criterion": "PRONUNCIATION",
                            "score": pronunciation_score,
                            "summary": "Clear pronunciation and intonation.",
                            "strengths": ["Clear consonant clusters"],
                            "weaknesses": ["Minor stress slip"]
                        }
                    ],
                    "improvementTips": [
                        {
                            "category": "FLUENCY_COHERENCE",
                            "tipText": "Use more varied discourse markers.",
                            "targetBand": 8.0
                        }
                    ]
                }

                # Publish completed event
                if self.publisher:
                    await self.publisher.publish_completed(
                        attempt_id=attempt_id,
                        fluency_score=fluency_score,
                        lexical_score=lexical_score,
                        grammar_score=grammar_score,
                        pronunciation_score=pronunciation_score,
                        overall_band=overall_band,
                        feedback_detail=feedback_detail,
                        idempotency_key=idempotency_key,
                        trace_id=trace_id,
                        correlation_id=correlation_id
                    )

                if self.db_pool:
                    await mark_inbox_completed(self.db_pool, idempotency_key)

            except Exception as ex:
                logger.error("[SPEAKING EVALUATION] Fatal error evaluating attempt %s: %s", attempt_id, str(ex), exc_info=True)
                if self.publisher:
                    await self.publisher.publish_failed(
                        attempt_id=attempt_id,
                        error_code="ACOUSTIC_EVALUATION_ERROR",
                        error_message=str(ex),
                        is_retriable=False,
                        idempotency_key=idempotency_key,
                        trace_id=trace_id,
                        correlation_id=correlation_id
                    )
                if self.db_pool:
                    await mark_inbox_failed(self.db_pool, idempotency_key, str(ex))
