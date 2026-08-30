"""
tests/test_deep_health_and_security.py
======================================
Unit and integration test suite verifying deep tiered health check evaluation,
circuit breaker provider statuses, and multi-process Prometheus metric aggregation.
"""

import unittest
import asyncio
import os
import tempfile
import shutil
from unittest.mock import AsyncMock, MagicMock

from providers.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState
from telemetry.health_checker import get_deep_health_status
from telemetry.metrics_server import get_prometheus_metrics


class TestDeepHealthAndSecurity(unittest.TestCase):

    def setUp(self):
        self.primary_cb = CircuitBreaker(CircuitBreakerConfig(provider_id="GEMINI_2_5_FLASH"))
        self.fallback_cb = CircuitBreaker(CircuitBreakerConfig(provider_id="AZURE_GPT_4O"))

    def test_health_degraded_when_primary_open_and_fallback_closed(self):
        """
        Test 1: When the primary LLM provider trips to OPEN due to quota exhaustion / rate limit
        but a valid fallback is CLOSED (healthy), deep health status evaluates to DEGRADED.
        """
        # Trip primary circuit breaker
        self.primary_cb.record_failure("QUOTA_EXHAUSTED")
        self.assertEqual(self.primary_cb.state, CircuitState.OPEN)
        self.assertEqual(self.fallback_cb.state, CircuitState.CLOSED)

        circuit_breakers = {
            "GEMINI_2_5_FLASH": self.primary_cb,
            "AZURE_GPT_4O": self.fallback_cb,
        }

        health_result = asyncio.run(get_deep_health_status(circuit_breakers=circuit_breakers))

        self.assertEqual(health_result["status"], "DEGRADED")
        self.assertEqual(health_result["components"]["aiProviders"]["GEMINI_2_5_FLASH"], "DOWN")
        self.assertEqual(health_result["components"]["aiProviders"]["AZURE_GPT_4O"], "UP")
        self.assertEqual(health_result["components"]["aiProviders"]["overallStatus"], "DEGRADED")

    def test_health_down_when_all_providers_open(self):
        """
        Test 2: When all configured AI providers trip to OPEN, deep health status evaluates to DOWN.
        """
        self.primary_cb.record_failure("QUOTA_EXHAUSTED")
        self.fallback_cb.record_failure("QUOTA_EXHAUSTED")

        self.assertEqual(self.primary_cb.state, CircuitState.OPEN)
        self.assertEqual(self.fallback_cb.state, CircuitState.OPEN)

        circuit_breakers = {
            "GEMINI_2_5_FLASH": self.primary_cb,
            "AZURE_GPT_4O": self.fallback_cb,
        }

        health_result = asyncio.run(get_deep_health_status(circuit_breakers=circuit_breakers))

        self.assertEqual(health_result["status"], "DOWN")
        self.assertEqual(health_result["components"]["aiProviders"]["overallStatus"], "DOWN")

    def test_multiprocess_prometheus_metric_scraping(self):
        """
        Test 3: Verifies that get_prometheus_metrics() aggregates multi-process metrics
        when PROMETHEUS_MULTIPROC_DIR is configured without raising exceptions.
        """
        temp_dir = tempfile.mkdtemp(prefix="prom_multiproc_test_")
        old_env = os.environ.get("PROMETHEUS_MULTIPROC_DIR")

        try:
            os.environ["PROMETHEUS_MULTIPROC_DIR"] = temp_dir
            payload, content_type = get_prometheus_metrics()

            self.assertIsInstance(payload, bytes)
            self.assertIn("text/plain", content_type)
        finally:
            if old_env is not None:
                os.environ["PROMETHEUS_MULTIPROC_DIR"] = old_env
            else:
                os.environ.pop("PROMETHEUS_MULTIPROC_DIR", None)
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
