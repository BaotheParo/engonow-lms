"""Async event consumer for IELTS speaking evaluations."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import os
import signal
import time
from contextlib import suppress
from enum import Enum
from typing import Any

from prometheus_client import start_http_server

from providers.base import EvaluationStatus, UnifiedSpeakingResult
from providers.config import CONFIG, WORKER_CONFIG, WorkerConfig
from providers.consumer import (
    BaseEventConsumer,
    BaseEventPublisher,
    EventPayload,
    KafkaEventConsumer,
    KafkaEventPublisher,
    LocalEventBroker,
    LocalEventConsumer,
    LocalEventPublisher,
)
from providers.factory import get_speaking_provider
from telemetry.drift_monitor import CUSUMDriftDetector
from telemetry.metrics import (
    DRIFT_ALERTS_TOTAL,
    EVALUATION_LATENCY_SECONDS,
    EVALUATION_REQUESTS_TOTAL,
    GENUINE_WORD_COVERAGE,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("engonow.ai_worker")

_result_publisher: BaseEventPublisher | None = None
_evaluation_semaphore: asyncio.Semaphore | None = None
_semaphore_loop: asyncio.AbstractEventLoop | None = None
coverage_drift_detector = CUSUMDriftDetector(
    target_mean=0.80,
    std_dev=0.15,
    slack_k=0.5,
    threshold_h=4.0,
)


def _get_evaluation_semaphore() -> asyncio.Semaphore:
    global _evaluation_semaphore, _semaphore_loop

    loop = asyncio.get_running_loop()
    if _evaluation_semaphore is None or _semaphore_loop is not loop:
        _evaluation_semaphore = asyncio.Semaphore(
            WORKER_CONFIG.concurrency_limit
        )
        _semaphore_loop = loop
    return _evaluation_semaphore


def _first_present(payload: EventPayload, *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is not None and value != "":
            return value
    return None


def _unwrap_outbox_payload(event_payload: EventPayload) -> EventPayload:
    embedded_payload = event_payload.get("payload")
    has_direct_evaluation_fields = any(
        key in event_payload
        for key in (
            "questions_metadata",
            "questionsMetadata",
            "audio_url",
            "audioUrl",
            "audio_bytes",
            "audioBytes",
        )
    )
    if embedded_payload is None or has_direct_evaluation_fields:
        return event_payload

    if isinstance(embedded_payload, str):
        embedded_payload = json.loads(embedded_payload)
    if not isinstance(embedded_payload, dict):
        raise ValueError("Outbox event payload must be a JSON object")

    normalized = dict(embedded_payload)
    aggregate_id = _first_present(
        event_payload,
        "aggregate_id",
        "aggregateId",
    )
    if aggregate_id is not None:
        normalized.setdefault("aggregate_id", aggregate_id)
    return normalized


def _normalize_questions_metadata(value: Any) -> str:
    if value is None:
        raise ValueError("questions_metadata is required")
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _decode_audio_bytes(value: Any) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    if not isinstance(value, str):
        raise ValueError("audio_bytes must be bytes or a base64-encoded string")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("audio_bytes is not valid base64") from exc


def _normalize_result_status(result_payload: EventPayload) -> None:
    raw_status = result_payload.get("status")
    if isinstance(raw_status, Enum):
        raw_status = raw_status.value
    status = str(raw_status)
    status_mapping = {
        EvaluationStatus.SUCCESS.value: "SUCCESS",
        EvaluationStatus.PARTIAL.value: "PARTIAL_SUCCESS_LOW_AUDIO_CONF",
        EvaluationStatus.FAILED.value: "SYSTEM_ERROR",
    }
    result_payload["status"] = status_mapping.get(status, status)


def _metric_label(value: Any, fallback: str = "UNKNOWN") -> str:
    """Return a bounded, non-empty string suitable for a metric label."""
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized:
            return normalized
    return fallback


def _record_evaluation_metrics(
    provider_name: str,
    result_payload: EventPayload,
    evaluation_duration_seconds: float | None,
) -> None:
    """Record telemetry without allowing metric failures to break processing."""
    status = _metric_label(result_payload.get("status"))

    try:
        EVALUATION_REQUESTS_TOTAL.labels(
            provider=provider_name,
            status=status,
        ).inc()

        if evaluation_duration_seconds is not None:
            EVALUATION_LATENCY_SECONDS.labels(
                provider=provider_name
            ).observe(evaluation_duration_seconds)

        if status == "SUCCESS":
            coverage = float(
                result_payload.get("genuine_word_coverage", 0.0)
            )
            GENUINE_WORD_COVERAGE.labels(provider=provider_name).observe(
                coverage
            )
    except Exception:
        logger.exception(
            "[TELEMETRY] Failed to record evaluation metrics for provider=%s "
            "status=%s",
            provider_name,
            status,
        )


def _monitor_coverage_drift(result_payload: EventPayload) -> None:
    """Update the coverage CUSUM without disrupting successful evaluations."""
    if result_payload.get("status") != "SUCCESS":
        return

    try:
        coverage = float(result_payload.get("genuine_word_coverage", 0.0))
        if not coverage_drift_detector.update(coverage):
            return

        logger.critical(
            "[DRIFT DETECTED] Genuine word coverage has significantly "
            "degraded! Provider API may have changed. Triggering "
            "recalibration alert."
        )
        coverage_drift_detector.reset()
        DRIFT_ALERTS_TOTAL.inc()
    except Exception:
        logger.exception(
            "[TELEMETRY] Failed to update genuine word coverage drift monitor"
        )


def _error_result(
    session_id: str,
    error: Exception,
    processing_time_ms: float,
) -> EventPayload:
    result = UnifiedSpeakingResult(
        session_id=session_id,
        provider_used=CONFIG.provider_name,
        pronunciation_score=max(1, min(9, CONFIG.fallback_score_pr)),
        fluency_score=max(1, min(9, CONFIG.fallback_score_fc)),
        grammar_score=max(1, min(9, CONFIG.fallback_score_gra)),
        lexical_score=max(1, min(9, CONFIG.fallback_score_lr)),
        status="SYSTEM_ERROR",
        genuine_word_coverage=0.0,
        feedback_text=(
            "Evaluation failed due to a worker processing error. "
            "The request can be retried safely."
        ),
        processing_time_ms=processing_time_ms,
        provider_metadata={
            "error": str(error),
            "error_type": type(error).__name__,
            "warnings": ["WORKER_PROCESSING_FAILED"],
        },
    )
    result.validate_scores()
    return result.to_dict()


async def process_speaking_request(event_payload: EventPayload) -> EventPayload:
    """Validate and evaluate one speaking event without dropping failures."""
    started_at = time.perf_counter()
    session_id = "UNKNOWN"
    provider_name = "UNKNOWN"
    evaluation_duration_seconds: float | None = None
    result_payload: EventPayload | None = None

    try:
        payload = _unwrap_outbox_payload(event_payload)
        raw_session_id = _first_present(
            payload,
            "session_id",
            "sessionId",
            "aggregate_id",
            "aggregateId",
        )
        if raw_session_id is None:
            raise ValueError("session_id or aggregate_id is required")
        session_id = str(raw_session_id)

        questions_metadata = _normalize_questions_metadata(
            _first_present(
                payload,
                "questions_metadata",
                "questionsMetadata",
            )
        )
        audio_url_value = _first_present(
            payload,
            "audio_url",
            "audioUrl",
            "file_reference",
            "fileReference",
        )
        audio_url = str(audio_url_value) if audio_url_value is not None else None
        audio_bytes = _decode_audio_bytes(
            _first_present(payload, "audio_bytes", "audioBytes")
        )
        if audio_url is None and audio_bytes is None:
            raise ValueError("audio_url, file reference, or audio_bytes is required")

        audio_filename_value = _first_present(
            payload,
            "audio_filename",
            "audioFilename",
        )
        audio_filename = (
            str(audio_filename_value)
            if audio_filename_value is not None
            else "audio.mp3"
        )

        logger.info("[AI WORKER] Intake request for session_id=%s", session_id)

        async with _get_evaluation_semaphore():
            provider = get_speaking_provider()
            provider_name = _metric_label(
                getattr(provider, "provider_name", None),
                fallback=CONFIG.provider_name,
            )
            evaluation_started_at = time.perf_counter()
            try:
                result = await provider.evaluate(
                    session_id=session_id,
                    audio_url=audio_url,
                    gemini_api_key=CONFIG.gemini_api_key,
                    questions_metadata=questions_metadata,
                    audio_bytes=audio_bytes,
                    audio_filename=audio_filename,
                )
            finally:
                evaluation_duration_seconds = (
                    time.perf_counter() - evaluation_started_at
                )

        if not isinstance(result, UnifiedSpeakingResult):
            raise TypeError(
                "Speaking provider must return UnifiedSpeakingResult, "
                f"received {type(result).__name__}"
            )
        result.validate_scores()
        result_payload = result.to_dict()
        provider_name = _metric_label(
            result_payload.get("provider_used"),
            fallback=provider_name,
        )
        _normalize_result_status(result_payload)
        _monitor_coverage_drift(result_payload)
        return result_payload
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception(
            "[AI WORKER] Evaluation failed for session_id=%s: %s",
            session_id,
            exc,
        )
        result_payload = _error_result(
            session_id=session_id,
            error=exc,
            processing_time_ms=(time.perf_counter() - started_at) * 1000,
        )
        return result_payload
    finally:
        if result_payload is not None:
            _record_evaluation_metrics(
                provider_name=provider_name,
                result_payload=result_payload,
                evaluation_duration_seconds=evaluation_duration_seconds,
            )


async def publish_result(result_payload: EventPayload) -> None:
    """Publish one standardized result through the configured broker."""
    if _result_publisher is None:
        raise RuntimeError("AI worker result publisher is not configured")
    await _result_publisher.publish(result_payload)
    logger.info(
        "[AI WORKER] Successfully published result for session_id=%s",
        result_payload.get("session_id"),
    )


def build_worker_transport(
    config: WorkerConfig,
) -> tuple[BaseEventConsumer, BaseEventPublisher, LocalEventBroker | None]:
    """Create matching request-consumer and result-publisher transports."""
    if config.broker_type == "LOCAL":
        local_broker = LocalEventBroker()
        return (
            LocalEventConsumer(
                broker=local_broker,
                topic=config.speaking_requests_topic,
                max_in_flight=config.concurrency_limit,
            ),
            LocalEventPublisher(
                broker=local_broker,
                topic=config.speaking_results_topic,
            ),
            local_broker,
        )

    return (
        KafkaEventConsumer(
            topic=config.speaking_requests_topic,
            bootstrap_servers=config.kafka_bootstrap_servers,
            consumer_group=config.kafka_consumer_group,
            max_batch_size=config.concurrency_limit,
        ),
        KafkaEventPublisher(
            topic=config.speaking_results_topic,
            bootstrap_servers=config.kafka_bootstrap_servers,
        ),
        None,
    )


def _install_shutdown_handlers(shutdown_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()

    def request_shutdown() -> None:
        if not shutdown_event.is_set():
            logger.info("[AI WORKER] Shutdown signal received")
            shutdown_event.set()

    for shutdown_signal in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(shutdown_signal, request_shutdown)
        except (NotImplementedError, RuntimeError):
            try:
                signal.signal(
                    shutdown_signal,
                    lambda _signum, _frame: loop.call_soon_threadsafe(
                        request_shutdown
                    ),
                )
            except (ValueError, OSError):
                logger.debug(
                    "[AI WORKER] Signal handler unavailable for %s",
                    shutdown_signal,
                )


async def run_worker(shutdown_event: asyncio.Event | None = None) -> None:
    """Core consumer loop for processing speaking requests."""
    global _result_publisher

    consumer, result_publisher, _local_broker = build_worker_transport(
        WORKER_CONFIG
    )
    _result_publisher = result_publisher

    if shutdown_event is None:
        shutdown_event = asyncio.Event()
        _install_shutdown_handlers(shutdown_event)

    listener_task: asyncio.Task[None] | None = None
    shutdown_task: asyncio.Task[bool] | None = None
    try:
        await result_publisher.start()
        logger.info(
            "[AI WORKER] Starting broker=%s requests_topic=%s "
            "results_topic=%s concurrency=%d",
            WORKER_CONFIG.broker_type,
            WORKER_CONFIG.speaking_requests_topic,
            WORKER_CONFIG.speaking_results_topic,
            WORKER_CONFIG.concurrency_limit,
        )

        listener_task = asyncio.create_task(
            consumer.start_listening(
                handler=process_speaking_request,
                publisher=publish_result,
            )
        )
        shutdown_task = asyncio.create_task(shutdown_event.wait())
        completed, _pending = await asyncio.wait(
            {listener_task, shutdown_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if listener_task in completed:
            await listener_task
            raise RuntimeError("Event consumer stopped unexpectedly")

        await consumer.stop()
        await listener_task
        logger.info("[AI WORKER] Graceful shutdown complete")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.critical(
            "[AI WORKER] Fatal worker crash: %s",
            exc,
            exc_info=True,
        )
        raise
    finally:
        await consumer.stop()
        await result_publisher.stop()
        _result_publisher = None
        if shutdown_task is not None and not shutdown_task.done():
            shutdown_task.cancel()
            with suppress(asyncio.CancelledError):
                await shutdown_task


async def main() -> None:
    """Run the standalone CLI worker with Prometheus server."""
    metrics_port = int(os.getenv("METRICS_PORT", "9090"))
    start_http_server(metrics_port)
    logger.info(
        "[TELEMETRY] Prometheus metrics server started on port %d",
        metrics_port,
    )
    await run_worker()


# ==============================================================================
# Production FastAPI Application (Gunicorn UvicornWorker Entrypoint)
# ==============================================================================
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from telemetry.metrics_server import get_prometheus_metrics


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Manages the background Kafka event consumer during the FastAPI lifecycle."""
    shutdown_event = asyncio.Event()
    worker_task = asyncio.create_task(run_worker(shutdown_event=shutdown_event))
    try:
        yield
    finally:
        shutdown_event.set()
        worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await worker_task


app = FastAPI(
    title="ENGONOW AI Worker",
    description="Multimodal Acoustic Engine, Provider Router, and Prometheus Metrics Exporter",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint conforming to Docker HEALTHCHECK and load balancer probes."""
    return {
        "status": "UP",
        "service": "engonow-ai-worker",
        "broker": WORKER_CONFIG.broker_type,
        "provider": CONFIG.provider_name,
    }


@app.get("/metrics")
async def metrics_endpoint() -> Response:
    """Prometheus multi-process metrics aggregation endpoint."""
    data, content_type = get_prometheus_metrics()
    return Response(content=data, media_type=content_type)


if __name__ == "__main__":
    asyncio.run(main())

