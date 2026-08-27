"""
tests/test_cusum_drift_monitor.py
=================================
Automated test suite for Real-Time Two-Sided CUSUM Drift Detection,
Redis State Management, Deduplication, and Kafka Alert Emission.
"""

import asyncio
import random
import unittest
from unittest.mock import AsyncMock, MagicMock
from telemetry.cusum_detector import CusumDetector, CusumState
from telemetry.cusum_state_manager import CusumStateManager, InMemoryStateBackend
from workers.calibration_drift_consumer import (
    CalibrationDriftConsumer,
    GroundTruthSampleEvent,
    DriftAlertEvent
)

class TestCusumDriftMonitor(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.detector = CusumDetector(target_mae=0.50, k=0.10, h=2.50)
        self.state_backend = InMemoryStateBackend()
        self.state_manager = CusumStateManager(redis_client=self.state_backend)

    def test_pure_cusum_degradation_triggers_upper_arm(self):
        """
        Sustained high error stream (|error| = 0.90 -> d_i = 0.40).
        With k=0.10, each step adds 0.30 to C+.
        After 9 steps, C+ reaches 2.70 >= 2.50 and triggers CRITICAL alert.
        """
        state = CusumState(subsystem="WRITING", criterion="TASK_RESPONSE")
        triggered = False
        step_count = 0
        final_result = None

        for i in range(12):
            step_count += 1
            # AI = 7.4, Ref = 6.5 -> |error| = 0.90
            res = self.detector.step(state, ai_score=7.4, reference_band=6.5)
            state = res.new_state
            if res.c_plus_triggered:
                triggered = True
                final_result = res
                break

        self.assertTrue(triggered)
        self.assertEqual(step_count, 9)
        self.assertEqual(final_result.alert_severity, "CRITICAL")
        self.assertGreaterEqual(final_result.trigger_value, 2.50)
        # Verify state resets to 0.0
        self.assertEqual(final_result.new_state.c_plus, 0.0)
        self.assertEqual(final_result.new_state.c_minus, 0.0)
        self.assertIsNotNone(final_result.new_state.last_reset_at)

    def test_pure_cusum_contamination_triggers_lower_arm(self):
        """
        Sustained zero error stream (|error| = 0.00 -> d_i = -0.50).
        With k=0.10, each step adds 0.40 to C-.
        After 7 steps, C- reaches 2.80 >= 2.50 and triggers WARNING alert.
        """
        state = CusumState(subsystem="SPEAKING", criterion="PRONUNCIATION")
        triggered = False
        step_count = 0
        final_result = None

        for i in range(10):
            step_count += 1
            # AI = 7.0, Ref = 7.0 -> |error| = 0.00
            res = self.detector.step(state, ai_score=7.0, reference_band=7.0)
            state = res.new_state
            if res.c_minus_triggered:
                triggered = True
                final_result = res
                break

        self.assertTrue(triggered)
        self.assertEqual(step_count, 7)
        self.assertEqual(final_result.alert_severity, "WARNING")
        self.assertGreaterEqual(final_result.trigger_value, 2.50)
        # Verify state resets to 0.0
        self.assertEqual(final_result.new_state.c_plus, 0.0)
        self.assertEqual(final_result.new_state.c_minus, 0.0)

    def test_stable_in_control_stream_does_not_drift(self):
        """
        50 in-control samples with mean |error| = 0.40 (< 0.50).
        Neither arm should ever cross 2.50.
        """
        state = CusumState(subsystem="WRITING", criterion="COHERENCE_COHESION")
        random.seed(42)

        for _ in range(50):
            # Error oscillating between 0.3 and 0.5
            err = random.choice([0.30, 0.40, 0.45, 0.50])
            ref = 6.5
            ai = ref + err
            res = self.detector.step(state, ai_score=ai, reference_band=ref)
            state = res.new_state

            self.assertFalse(res.c_plus_triggered)
            self.assertFalse(res.c_minus_triggered)
            self.assertLess(state.c_plus, 2.50)
            self.assertLess(state.c_minus, 2.50)

    async def test_state_manager_deduplication_and_drift_hold(self):
        """
        Verifies authoritative event deduplication and system drift_hold flag governance.
        """
        kafka_producer = MagicMock()
        consumer = CalibrationDriftConsumer(
            state_manager=self.state_manager,
            detector=self.detector,
            kafka_producer=kafka_producer
        )

        event = GroundTruthSampleEvent(
            eventId="evt-unique-001",
            subsystem="WRITING",
            criterion="LEXICAL_RESOURCE",
            aiScore=7.5,
            referenceBand=7.0
        )

        # 1. First ingestion -> Processed
        alert1 = await consumer.process_sample(event)
        self.assertIsNone(alert1)  # 1 step is below threshold

        state = await self.state_manager.get_state("WRITING", "LEXICAL_RESOURCE")
        self.assertEqual(state.sample_count, 1)

        # 2. Duplicate ingestion of the same event ID -> Skipped
        alert_dup = await consumer.process_sample(event)
        self.assertIsNone(alert_dup)

        state_after_dup = await self.state_manager.get_state("WRITING", "LEXICAL_RESOURCE")
        self.assertEqual(state_after_dup.sample_count, 1)  # No increment

        # 3. Test system drift_hold circuit breaker
        self.assertFalse(await self.state_manager.is_drift_hold_active())

        await self.state_manager.set_drift_hold(True, "Critical accuracy degradation detected")
        self.assertTrue(await self.state_manager.is_drift_hold_active())

        # Test PostgreSQL checkpointing
        checkpoint_count = await self.state_manager.checkpoint_to_postgres()
        self.assertEqual(checkpoint_count, 1)

        # Clear active Redis hash to simulate node crash / cold start
        self.state_backend.hashes.clear()

        recovered_state = await self.state_manager.get_state("WRITING", "LEXICAL_RESOURCE")
        self.assertEqual(recovered_state.sample_count, 1)

    async def test_end_to_end_critical_drift_trips_circuit_breaker(self):
        """
        E2E simulation: High-error events processed by consumer triggers Kafka alert
        and sets system drift_hold flag to True.
        """
        kafka_producer = MagicMock()
        kafka_producer.send_and_wait = AsyncMock()

        consumer = CalibrationDriftConsumer(
            state_manager=self.state_manager,
            detector=self.detector,
            kafka_producer=kafka_producer
        )

        alerts = []
        for i in range(5):
            evt = GroundTruthSampleEvent(
                eventId=f"evt-deg-{i}",
                subsystem="SPEAKING",
                criterion="FLUENCY_COHERENCE",
                aiScore=8.0,
                referenceBand=6.5  # Error 1.50 -> d_i = 1.00 (+0.90 per step)
            )
            alert = await consumer.process_sample(evt)
            if alert:
                alerts.append(alert)

        # After 3 steps of +0.90, C+ reaches 2.70 >= 2.50 and triggers 1st alert
        self.assertGreaterEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, "CRITICAL")
        self.assertEqual(alerts[0].arm, "UPPER_ARM_C_PLUS")
        self.assertTrue(await self.state_manager.is_drift_hold_active())
        self.assertTrue(kafka_producer.send_and_wait.called)

    async def test_dedup_set_ttl_refresh_on_sadd(self):
        """
        Verifies that every SADD to the deduplication set refreshes the 7-day TTL countdown.
        """
        state = CusumState(subsystem="WRITING", criterion="TASK_RESPONSE")
        await self.state_manager.save_state_and_mark_dedup(state, event_id="evt-ttl-001")

        dedup_key = "cusum:dedup:WRITING:TASK_RESPONSE"
        self.assertEqual(self.state_backend.ttls.get(dedup_key), 7 * 24 * 3600)

        # Second event refreshes TTL
        await self.state_manager.save_state_and_mark_dedup(state, event_id="evt-ttl-002")
        self.assertEqual(self.state_backend.ttls.get(dedup_key), 7 * 24 * 3600)

    async def test_postgres_batch_checkpoint_transaction(self):
        """
        Verifies that checkpoint_to_postgres groups multiple state records into a single batch transaction.
        """
        mock_pg = MagicMock()
        mock_pg.executemany = AsyncMock()
        mock_tx = MagicMock()
        mock_tx.__aenter__ = AsyncMock(return_value=mock_tx)
        mock_tx.__aexit__ = AsyncMock(return_value=None)
        mock_pg.transaction = MagicMock(return_value=mock_tx)

        # Redis backend with 2 active states
        mock_redis = MagicMock()
        mock_redis.keys_pattern = AsyncMock(return_value=["cusum:state:WRITING:TR", "cusum:state:WRITING:CC"])
        mock_redis.hgetall = AsyncMock(side_effect=[
            {"c_plus": "0.3", "c_minus": "0.0", "sample_count": "5"},
            {"c_plus": "0.1", "c_minus": "0.2", "sample_count": "10"}
        ])

        manager = CusumStateManager(redis_client=mock_redis, pg_conn=mock_pg)
        checkpoint_count = await manager.checkpoint_to_postgres()

        self.assertEqual(checkpoint_count, 2)
        mock_pg.transaction.assert_called_once()
        mock_pg.executemany.assert_called_once()
        # Verify 2 records batched in single query
        args, _ = mock_pg.executemany.call_args
        records = args[1]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0][0], "WRITING")
        self.assertEqual(records[0][1], "TR")
        self.assertEqual(records[1][0], "WRITING")
        self.assertEqual(records[1][1], "CC")

if __name__ == "__main__":
    unittest.main()
