"""
workers/calibration_drift_consumer.py
======================================
Resilient Kafka Drift Consumer & Telemetry Alert Publisher.
Consumes ground-truth evaluation pairs, executes Two-Sided CUSUM detection,
emits alerts to calibration.alerts.v1, and manages the automated drift_hold circuit breaker.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import uuid
from typing import Any, Callable, Dict, Optional
from pydantic import BaseModel, Field

from telemetry.cusum_detector import CusumDetector, CusumState, CusumStepResult
from telemetry.cusum_state_manager import CusumStateManager

logger = logging.getLogger(__name__)

TOPIC_GROUND_TRUTH_AVAILABLE = "calibration.ground-truth.available"
TOPIC_CALIBRATION_ALERTS = "calibration.alerts.v1"
CONSUMER_GROUP_DRIFT_MONITOR = "engonow-drift-monitor-v1"

class GroundTruthSampleEvent(BaseModel):
    eventId: str = Field(default_factory=lambda: str(uuid.uuid4()))
    subsystem: str  # WRITING or SPEAKING
    criterion: str  # e.g., TASK_RESPONSE, FLUENCY_COHERENCE
    aiScore: float
    referenceBand: float
    occurredAt: Optional[str] = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class DriftAlertEvent(BaseModel):
    alertId: str = Field(default_factory=lambda: str(uuid.uuid4()))
    subsystem: str
    criterion: str
    arm: str  # "UPPER_ARM_C_PLUS" or "LOWER_ARM_C_MINUS"
    severity: str  # "CRITICAL" or "WARNING"
    triggeringValue: float
    sampleCountSinceLastReset: int
    detectedAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    recommendedAction: str

class CalibrationDriftConsumer:
    """
    Kafka consumer monitoring real-time AI scoring accuracy against ground-truth samples.
    """

    def __init__(
        self,
        state_manager: CusumStateManager,
        detector: Optional[CusumDetector] = None,
        kafka_producer: Optional[Any] = None
    ):
        self.state_manager = state_manager
        self.detector = detector if detector is not None else CusumDetector()
        self.kafka_producer = kafka_producer
        self._running = False
        self._checkpoint_task: Optional[asyncio.Task] = None

    async def process_sample(self, event: GroundTruthSampleEvent) -> Optional[DriftAlertEvent]:
        """
        Idempotently processes a single GroundTruthSampleEvent.
        """
        # 1. Event Deduplication Guard
        is_dup = await self.state_manager.is_duplicate_event(event.subsystem, event.criterion, event.eventId)
        if is_dup:
            logger.info(
                "[CUSUM DUP] Event %s for %s.%s already processed. Skipping.",
                event.eventId, event.subsystem, event.criterion
            )
            return None

        # 2. Retrieve Current State
        current_state = await self.state_manager.get_state(event.subsystem, event.criterion)

        # 3. Calculate CUSUM Step
        step_result = self.detector.step(current_state, event.aiScore, event.referenceBand)

        # 4. Atomically Persist New State & Mark Dedup
        await self.state_manager.save_state_and_mark_dedup(step_result.new_state, event.eventId)

        # Update Prometheus SPC Gauges
        try:
            from telemetry.metrics import (
                CUSUM_C_PLUS_GAUGE,
                CUSUM_C_MINUS_GAUGE,
                CALIBRATION_SAMPLE_FORWARDED
            )
            CUSUM_C_PLUS_GAUGE.labels(subsystem=event.subsystem, criterion=event.criterion).set(step_result.new_state.c_plus)
            CUSUM_C_MINUS_GAUGE.labels(subsystem=event.subsystem, criterion=event.criterion).set(step_result.new_state.c_minus)
            CALIBRATION_SAMPLE_FORWARDED.labels(subsystem=event.subsystem, sampling_reason="GROUND_TRUTH_INGESTION").inc()
        except Exception as e:
            logger.debug("[CUSUM METRICS] Metric update error: %s", str(e))

        # 5. Check and Route Alerts
        alert = None
        if step_result.c_plus_triggered:
            # Model Accuracy Degradation Breach
            alert = DriftAlertEvent(
                subsystem=event.subsystem,
                criterion=event.criterion,
                arm="UPPER_ARM_C_PLUS",
                severity="CRITICAL",
                triggeringValue=step_result.trigger_value,
                sampleCountSinceLastReset=step_result.new_state.sample_count,
                recommendedAction="HALT_AUTO_PROMOTION_AND_RERUN_GATEKEEPER"
            )
            # Trip the drift_hold circuit breaker flag
            await self.state_manager.set_drift_hold(
                True,
                f"CUSUM C+ degradation breach on {event.subsystem}.{event.criterion} (value={step_result.trigger_value:.4f} >= {self.detector.h})"
            )
            await self._publish_alert(alert)

        elif step_result.c_minus_triggered:
            # Suspicious Zero Error / Contamination Breach
            alert = DriftAlertEvent(
                subsystem=event.subsystem,
                criterion=event.criterion,
                arm="LOWER_ARM_C_MINUS",
                severity="WARNING",
                triggeringValue=step_result.trigger_value,
                sampleCountSinceLastReset=step_result.new_state.sample_count,
                recommendedAction="INVESTIGATE_POSSIBLE_CORPUS_CONTAMINATION_OR_CACHING_BUG"
            )
            await self._publish_alert(alert)

        return alert

    async def _publish_alert(self, alert: DriftAlertEvent) -> None:
        """Publishes DriftAlertEvent to Kafka calibration.alerts.v1."""
        logger.warning(
            "[CUSUM ALERT] Emitting %s alert for %s.%s (%s) value=%.4f",
            alert.severity, alert.subsystem, alert.criterion, alert.arm, alert.triggeringValue
        )
        if self.kafka_producer:
            key = f"{alert.subsystem}:{alert.criterion}".encode("utf-8")
            payload = alert.model_dump_json().encode("utf-8")
            try:
                if hasattr(self.kafka_producer, "send_and_wait"):
                    await self.kafka_producer.send_and_wait(TOPIC_CALIBRATION_ALERTS, value=payload, key=key)
                elif hasattr(self.kafka_producer, "send"):
                    self.kafka_producer.send(TOPIC_CALIBRATION_ALERTS, value=payload, key=key)
            except Exception as e:
                logger.error("[CUSUM ALERT] Failed to publish alert to Kafka: %s", str(e))

    async def start_periodic_checkpoint(self, interval_seconds: int = 60) -> None:
        """Starts background periodic checkpointing of Redis state to PostgreSQL."""
        self._running = True

        async def _loop():
            while self._running:
                try:
                    await asyncio.sleep(interval_seconds)
                    await self.state_manager.checkpoint_to_postgres()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("[CUSUM CHECKPOINT TASK] Checkpoint error: %s", str(e))

        self._checkpoint_task = asyncio.create_task(_loop())

    async def stop(self) -> None:
        """Gracefully stops periodic background tasks."""
        self._running = False
        if self._checkpoint_task:
            self._checkpoint_task.cancel()
            try:
                await self._checkpoint_task
            except asyncio.CancelledError:
                pass
