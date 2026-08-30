"""
tests/test_circuit_breaker_and_selector.py
==========================================
Unit test suite verifying the pure Circuit Breaker state machine,
weighted failure rate calculations, supervised synthetic canary ramp,
multi-provider intelligent scoring, dynamic failover, and uncalibrated model governance.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
import time
import unittest

from providers.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    FailureSignal,
)
from providers.resilience.provider_selector import (
    IntelligentProviderSelector,
    ProviderConfig,
    SelectionResult,
)


class TestCircuitBreakerAndSelector(unittest.TestCase):

    def setUp(self):
        self.default_cb_config = CircuitBreakerConfig(
            provider_id="TEST_PROVIDER",
            rolling_window_size=20,
            minimum_call_volume_threshold=10,
            failure_rate_threshold_to_open=0.50,
            initial_reset_timeout_seconds=30.0,
            max_reset_timeout_seconds=300.0,
            reset_timeout_backoff_multiplier=2.0,
            half_open_ramp_percentages=[10, 50, 100],
            half_open_ramp_step_duration_seconds=120.0,
            half_open_ramp_failure_tolerance=0.10,
        )

    def test_hard_trip_quota_exhausted(self):
        """
        Test 1: QUOTA_EXHAUSTED immediately trips the circuit breaker to OPEN,
        bypassing the rolling window and minimum volume thresholds.
        """
        cb = CircuitBreaker(self.default_cb_config)
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.allow_request())

        # Record hard trip signal
        cb.record_failure(FailureSignal.QUOTA_EXHAUSTED)

        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.allow_request())

    def test_weighted_failure_rate_threshold(self):
        """
        Test 2: Verifies weighted failure rate accumulation in a rolling window of 20 calls.
        8 successes (0.0) + 10 SCHEMA_VALIDATION_FAILURE (weight 0.5 * 10 = 5.0) + 4 RATE_LIMITED_429 (weight 1.0 * 4 = 4.0).
        Total weighted failures = 9.0 out of 20 = 45% -> Stays CLOSED (< 50%).
        Adding 2 TIMEOUT (weight 1.0 * 2 = 2.0) -> Weighted failure rate >= 50% -> Trips to OPEN.
        """
        cb = CircuitBreaker(self.default_cb_config)

        # 8 successes
        for _ in range(8):
            cb.record_success()

        # 10 Schema validation failures (weight 0.5 each = 5.0)
        for _ in range(10):
            cb.record_failure(FailureSignal.SCHEMA_VALIDATION_FAILURE)

        # 4 Rate limited 429 failures (weight 1.0 each = 4.0)
        # Window size 20 drops the first 2 successes -> window has 6 successes (0.0) + 10 schema (5.0) + 4 rate limit (4.0) = 9.0/20 = 45%
        for _ in range(4):
            cb.record_failure(FailureSignal.RATE_LIMITED_429)

        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.allow_request())

        # Add 2 TIMEOUT failures (weight 1.0 each = 2.0)
        # Window now has 4 successes + 10 schema (5.0) + 4 rate limit (4.0) + 2 timeouts (2.0) = 11.0/20 = 55% (>= 50%)
        cb.record_failure(FailureSignal.TIMEOUT)
        cb.record_failure(FailureSignal.TIMEOUT)

        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.allow_request())

    def test_half_open_supervised_ramp_and_canary(self):
        """
        Test 3: Verifies supervised synthetic canary probe, exponential timeout backoff,
        and staged real-traffic ramp (10% -> 50% -> 100% -> CLOSED).
        """
        cb = CircuitBreaker(self.default_cb_config)

        # Trip to OPEN
        cb.record_failure(FailureSignal.QUOTA_EXHAUSTED)
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertEqual(cb.current_reset_timeout, 30.0)

        # Advance time past initial reset timeout (30s)
        cb.last_state_change_time = time.time() - 31.0

        # allow_request() transitions OPEN -> HALF_OPEN (real traffic initially blocked)
        self.assertFalse(cb.allow_request())
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)
        self.assertFalse(cb.is_canary_passed)

        # Case A: Canary probe fails -> Trips back to OPEN with doubled reset timeout (60s)
        cb.record_canary_result(is_success=False)
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertEqual(cb.current_reset_timeout, 60.0)

        # Advance time past backed-off timeout (60s)
        cb.last_state_change_time = time.time() - 61.0
        self.assertFalse(cb.allow_request())
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

        # Case B: Canary probe succeeds -> Begins staged ramp
        cb.record_canary_result(is_success=True)
        self.assertTrue(cb.is_canary_passed)
        self.assertEqual(cb.half_open_step_index, 0)  # Step 0: 10% ramp

        # Step 0 (10%) duration expires (120s) -> Advances to Step 1 (50%)
        cb.half_open_step_start_time = time.time() - 121.0
        cb.allow_request()
        self.assertEqual(cb.half_open_step_index, 1)  # Step 1: 50% ramp
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

        # Step 1 (50%) duration expires (120s) -> Advances to Step 2 (100%)
        cb.half_open_step_start_time = time.time() - 121.0
        cb.allow_request()
        self.assertEqual(cb.half_open_step_index, 2)  # Step 2: 100% ramp
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

        # Step 2 (100%) duration expires (120s) -> Transitions back to CLOSED
        cb.half_open_step_start_time = time.time() - 121.0
        allowed = cb.allow_request()
        self.assertTrue(allowed)
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertEqual(cb.current_reset_timeout, 30.0)

    def test_provider_selector_uncalibrated_fallback_tagging(self):
        """
        Test 4: Verifies intelligent routing, latency headroom/cost scoring,
        and uncalibrated fallback model governance.
        """
        now = datetime.now(timezone.utc)

        gemini_cfg = ProviderConfig(
            provider_id="GEMINI_2_5_FLASH",
            priority=1,
            cost_per_thousand_input_tokens=Decimal("0.075"),
            cost_per_thousand_output_tokens=Decimal("0.300"),
            latency_sla_budget_seconds=5.0,
            validated_mae=Decimal("0.42"),
            mae_validated_at=now,
            requires_human_review_fallback=False,
        )

        groq_cfg = ProviderConfig(
            provider_id="GROQ_LLAMA_3_3_70B",
            priority=2,
            cost_per_thousand_input_tokens=Decimal("0.590"),
            cost_per_thousand_output_tokens=Decimal("0.790"),
            latency_sla_budget_seconds=3.0,
            validated_mae=None,  # Uncalibrated fallback!
            mae_validated_at=None,
            requires_human_review_fallback=False,
        )

        providers = {
            "GEMINI_2_5_FLASH": gemini_cfg,
            "GROQ_LLAMA_3_3_70B": groq_cfg,
        }

        gemini_cb = CircuitBreaker(CircuitBreakerConfig(provider_id="GEMINI_2_5_FLASH"))
        groq_cb = CircuitBreaker(CircuitBreakerConfig(provider_id="GROQ_LLAMA_3_3_70B"))
        breakers = {
            "GEMINI_2_5_FLASH": gemini_cb,
            "GROQ_LLAMA_3_3_70B": groq_cb,
        }

        selector = IntelligentProviderSelector(providers, breakers)
        selector.update_observed_latency("GEMINI_2_5_FLASH", p95_seconds=1.2)
        selector.update_observed_latency("GROQ_LLAMA_3_3_70B", p95_seconds=0.8)

        # 1. When primary is CLOSED -> Selects Gemini with AI_AUTO (no human review)
        result1 = selector.select_provider()
        self.assertEqual(result1.selected_provider_id, "GEMINI_2_5_FLASH")
        self.assertEqual(result1.evaluated_by, "AI_AUTO")
        self.assertFalse(result1.requires_human_review)
        self.assertEqual(result1.candidate_cascade_order, ["GEMINI_2_5_FLASH", "GROQ_LLAMA_3_3_70B"])

        # 2. Trip Gemini to OPEN -> Dynamically fails over to Groq with AI_AUTO_UNCALIBRATED
        gemini_cb.record_failure(FailureSignal.QUOTA_EXHAUSTED)
        self.assertEqual(gemini_cb.state, CircuitState.OPEN)

        result2 = selector.select_provider()
        self.assertEqual(result2.selected_provider_id, "GROQ_LLAMA_3_3_70B")
        self.assertEqual(result2.evaluated_by, "AI_AUTO_UNCALIBRATED")
        self.assertTrue(result2.requires_human_review)
        self.assertEqual(result2.candidate_cascade_order, ["GROQ_LLAMA_3_3_70B"])

    def test_all_providers_open_raises_exception(self):
        """
        Test 5: When all configured providers have OPEN circuit breakers,
        selector raises RuntimeError("ALL_PROVIDERS_UNAVAILABLE").
        """
        gemini_cfg = ProviderConfig(
            provider_id="GEMINI_2_5_FLASH",
            priority=1,
            cost_per_thousand_input_tokens=Decimal("0.075"),
            cost_per_thousand_output_tokens=Decimal("0.300"),
            latency_sla_budget_seconds=5.0,
        )

        providers = {"GEMINI_2_5_FLASH": gemini_cfg}
        gemini_cb = CircuitBreaker(CircuitBreakerConfig(provider_id="GEMINI_2_5_FLASH"))
        gemini_cb.record_failure(FailureSignal.QUOTA_EXHAUSTED)
        breakers = {"GEMINI_2_5_FLASH": gemini_cb}

        selector = IntelligentProviderSelector(providers, breakers)

        with self.assertRaises(RuntimeError) as ctx:
            selector.select_provider()
        self.assertIn("ALL_PROVIDERS_UNAVAILABLE", str(ctx.exception))

    def test_expired_gatekeeper_mae_triggers_uncalibrated_flag(self):
        """
        Test 6: Validates that an MAE older than 90 days is flagged as uncalibrated.
        """
        expired_date = datetime.now(timezone.utc) - timedelta(days=95)
        provider_cfg = ProviderConfig(
            provider_id="AZURE_GPT_4O",
            priority=1,
            cost_per_thousand_input_tokens=Decimal("2.50"),
            cost_per_thousand_output_tokens=Decimal("10.00"),
            latency_sla_budget_seconds=4.0,
            validated_mae=Decimal("0.38"),
            mae_validated_at=expired_date,  # 95 days old (> 90 days)
        )

        self.assertFalse(provider_cfg.is_mae_valid(max_age_days=90))

        providers = {"AZURE_GPT_4O": provider_cfg}
        breakers = {"AZURE_GPT_4O": CircuitBreaker(CircuitBreakerConfig(provider_id="AZURE_GPT_4O"))}
        selector = IntelligentProviderSelector(providers, breakers)

        res = selector.select_provider()
        self.assertEqual(res.selected_provider_id, "AZURE_GPT_4O")
        self.assertEqual(res.evaluated_by, "AI_AUTO_UNCALIBRATED")
        self.assertTrue(res.requires_human_review)

    def test_naive_datetime_normalization_in_mae_valid(self):
        """
        Test 7: Validates that an offset-naive datetime in mae_validated_at
        is normalized to UTC without raising TypeError during age calculation.
        """
        naive_dt = datetime.now() - timedelta(days=10)  # Naive datetime
        cfg = ProviderConfig(
            provider_id="TEST_NAIVE_TZ",
            priority=1,
            cost_per_thousand_input_tokens=Decimal("0.10"),
            cost_per_thousand_output_tokens=Decimal("0.20"),
            latency_sla_budget_seconds=3.0,
            validated_mae=Decimal("0.45"),
            mae_validated_at=naive_dt,
        )
        # Should evaluate cleanly to True without TypeError: can't subtract offset-naive and offset-aware datetimes
        self.assertTrue(cfg.is_mae_valid(max_age_days=90))

    def test_circuit_breaker_thread_safety(self):
        """
        Test 8: Validates atomic state mutation and rolling window maintenance
        under high concurrent multi-threaded execution.
        """
        import concurrent.futures

        cb = CircuitBreaker(self.default_cb_config)

        def worker_task(i: int):
            if i % 3 == 0:
                cb.record_success()
            elif i % 3 == 1:
                cb.record_failure(FailureSignal.RATE_LIMITED_429)
            else:
                cb.allow_request()

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker_task, i) for i in range(100)]
            concurrent.futures.wait(futures)

        # Confirm calls_history does not exceed window size and lock protected history integrity
        with cb._lock:
            self.assertLessEqual(len(cb.calls_history), self.default_cb_config.rolling_window_size)


if __name__ == "__main__":
    unittest.main()
