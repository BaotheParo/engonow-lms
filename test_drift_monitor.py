"""Unit tests for the streaming CUSUM drift detector."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, Mock, patch

import ai_worker
from providers.base import EvaluationStatus, UnifiedSpeakingResult
from telemetry.drift_monitor import CUSUMDriftDetector
from telemetry.metrics import DRIFT_ALERTS_TOTAL


class CUSUMDriftDetectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.detector = CUSUMDriftDetector(
            target_mean=0.80,
            std_dev=0.10,
            slack_k=0.5,
            threshold_h=4.0,
        )

    def test_detects_silent_downward_api_degradation(self) -> None:
        normal_values = [0.78, 0.82, 0.85, 0.75] * 5
        for value in normal_values:
            with self.subTest(phase="normal", value=value):
                self.assertFalse(self.detector.update(value))

        degraded_values = [0.42, 0.38, 0.45]
        detection_iteration = None
        for iteration in range(1, 11):
            value = degraded_values[(iteration - 1) % len(degraded_values)]
            if self.detector.update(value):
                detection_iteration = iteration
                break

        self.assertIsNotNone(
            detection_iteration,
            "CUSUM did not detect the simulated provider degradation",
        )
        self.assertLessEqual(detection_iteration, 5)

    def test_upward_shift_does_not_trigger_downward_detector(self) -> None:
        for value in [0.90, 0.95, 1.00] * 10:
            self.assertFalse(self.detector.update(value))
        self.assertEqual(self.detector.s_low, 0.0)

    def test_reset_clears_accumulated_state(self) -> None:
        self.detector.update(0.60)
        self.assertGreater(self.detector.s_low, 0.0)

        self.detector.reset()

        self.assertEqual(self.detector.s_low, 0.0)


class CoverageDriftIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        ai_worker.coverage_drift_detector.reset()

    def tearDown(self) -> None:
        ai_worker.coverage_drift_detector.reset()

    async def test_worker_triggers_and_resets_drift_alert(self) -> None:
        provider = Mock()
        provider.provider_name = "GROQ_LOCAL"
        provider.evaluate = AsyncMock(
            side_effect=[
                self._successful_result("degraded-1", 0.42),
                self._successful_result("degraded-2", 0.38),
            ]
        )
        alerts_before = DRIFT_ALERTS_TOTAL._value.get()

        with (
            patch("ai_worker.get_speaking_provider", return_value=provider),
            self.assertLogs("engonow.ai_worker", level="CRITICAL") as logs,
        ):
            for iteration in range(1, 3):
                await ai_worker.process_speaking_request(
                    {
                        "session_id": f"degraded-{iteration}",
                        "questions_metadata": [],
                        "audio_url": (
                            f"https://cdn.example.test/degraded-{iteration}.mp3"
                        ),
                    }
                )

        self.assertTrue(
            any("[DRIFT DETECTED]" in message for message in logs.output)
        )
        self.assertEqual(DRIFT_ALERTS_TOTAL._value.get(), alerts_before + 1)
        self.assertEqual(ai_worker.coverage_drift_detector.s_low, 0.0)

    @staticmethod
    def _successful_result(
        session_id: str,
        coverage: float,
    ) -> UnifiedSpeakingResult:
        return UnifiedSpeakingResult(
            session_id=session_id,
            provider_used="GROQ_LOCAL",
            pronunciation_score=7,
            fluency_score=7,
            grammar_score=7,
            lexical_score=7,
            status=EvaluationStatus.SUCCESS,
            genuine_word_coverage=coverage,
            feedback_text="Evaluation completed.",
        )


if __name__ == "__main__":
    unittest.main()
