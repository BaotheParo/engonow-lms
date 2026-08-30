"""
providers/resilience/circuit_breaker.py
=======================================
Pure, dependency-free Circuit Breaker State Machine for multi-provider resilience.
Implements weighted failure accumulation, hard-trip quota bypass, and a supervised
synthetic canary ramp with exponential backoff.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import time
import random
import threading


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class FailureSignal(str, Enum):
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"          # Hard trip -> Bypasses window to OPEN
    RATE_LIMITED_429 = "RATE_LIMITED_429"        # Soft trip -> Weight = 1.0
    SERVICE_UNAVAILABLE_503 = "SERVICE_UNAVAILABLE_503"  # Soft trip -> Weight = 1.0
    TIMEOUT = "TIMEOUT"                          # Soft trip -> Weight = 1.0
    SCHEMA_VALIDATION_FAILURE = "SCHEMA_VALIDATION_FAILURE"  # Soft trip -> Weight = 0.5


SIGNAL_WEIGHTS: Dict[FailureSignal, float] = {
    FailureSignal.QUOTA_EXHAUSTED: 1.0,
    FailureSignal.RATE_LIMITED_429: 1.0,
    FailureSignal.SERVICE_UNAVAILABLE_503: 1.0,
    FailureSignal.TIMEOUT: 1.0,
    FailureSignal.SCHEMA_VALIDATION_FAILURE: 0.5,
}


@dataclass
class CircuitBreakerConfig:
    provider_id: str
    rolling_window_size: int = 20
    minimum_call_volume_threshold: int = 10
    failure_rate_threshold_to_open: float = 0.50
    initial_reset_timeout_seconds: float = 30.0
    max_reset_timeout_seconds: float = 300.0
    reset_timeout_backoff_multiplier: float = 2.0
    half_open_ramp_percentages: List[int] = field(default_factory=lambda: [10, 50, 100])
    half_open_ramp_step_duration_seconds: float = 120.0
    half_open_ramp_failure_tolerance: float = 0.10


class CircuitBreaker:
    """
    Production-grade Circuit Breaker with weighted signal evaluation and supervised
    canary ramp for LLM provider resilience.
    """

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self._lock = threading.Lock()
        self.state: CircuitState = CircuitState.CLOSED
        self.current_reset_timeout: float = config.initial_reset_timeout_seconds
        self.last_state_change_time: float = time.time()
        self.calls_history: List[Tuple[float, bool, float]] = []  # (timestamp, is_success, weight)
        self.half_open_step_index: int = 0
        self.half_open_step_start_time: float = 0.0
        self.half_open_step_calls: List[bool] = []
        self.is_canary_passed: bool = False

    def allow_request(self) -> bool:
        """
        Evaluates whether a real traffic request is allowed through the circuit breaker.
        Handles automatic time-based transitions from OPEN to HALF_OPEN and stages ramp gating.
        """
        with self._lock:
            now = time.time()

            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                elapsed = now - self.last_state_change_time
                if elapsed >= self.current_reset_timeout:
                    # Transition to HALF_OPEN: wait for synthetic canary probe
                    self.state = CircuitState.HALF_OPEN
                    self.last_state_change_time = now
                    self.is_canary_passed = False
                    self.half_open_step_index = 0
                    self.half_open_step_start_time = now
                    self.half_open_step_calls.clear()
                    # Real user requests must NOT probe half-open before synthetic canary
                    return False
                return False

            if self.state == CircuitState.HALF_OPEN:
                if not self.is_canary_passed:
                    # Real traffic blocked until synthetic canary probe passes
                    return False

                # Check if current ramp step duration has elapsed
                step_elapsed = now - self.half_open_step_start_time
                if step_elapsed >= self.config.half_open_ramp_step_duration_seconds:
                    self.half_open_step_index += 1
                    if self.half_open_step_index >= len(self.config.half_open_ramp_percentages):
                        # Successfully completed all ramp stages -> Reset to CLOSED
                        self._reset_to_closed()
                        return True
                    else:
                        self.half_open_step_start_time = now
                        self.half_open_step_calls.clear()

                # Gate traffic based on current ramp percentage
                ramp_pct = self.config.half_open_ramp_percentages[self.half_open_step_index]
                if ramp_pct >= 100:
                    return True
                return random.uniform(0.0, 100.0) < float(ramp_pct)

            return False

    def record_success(self) -> None:
        """
        Records a successful real-traffic execution.
        """
        with self._lock:
            now = time.time()
            if self.state == CircuitState.CLOSED:
                self.calls_history.append((now, True, 1.0))
                if len(self.calls_history) > self.config.rolling_window_size:
                    self.calls_history.pop(0)

            elif self.state == CircuitState.HALF_OPEN:
                self.half_open_step_calls.append(True)
                # Check for step advancement if step time expired
                step_elapsed = now - self.half_open_step_start_time
                if step_elapsed >= self.config.half_open_ramp_step_duration_seconds:
                    self.half_open_step_index += 1
                    if self.half_open_step_index >= len(self.config.half_open_ramp_percentages):
                        self._reset_to_closed()
                    else:
                        self.half_open_step_start_time = now
                        self.half_open_step_calls.clear()

    def record_failure(self, signal: FailureSignal) -> None:
        """
        Records a failure with signal-specific weight and evaluates tripping conditions.
        """
        with self._lock:
            now = time.time()

            # Hard Trip: QUOTA_EXHAUSTED immediately trips to OPEN, bypassing window
            if signal == FailureSignal.QUOTA_EXHAUSTED:
                self._trip_to_open(from_hard_trip=True)
                return

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_step_calls.append(False)
                fails = sum(1 for c in self.half_open_step_calls if not c)
                total = len(self.half_open_step_calls)
                failure_rate = fails / total if total > 0 else 0.0

                # Any critical failure or failure rate exceeding tolerance immediately trips to OPEN
                if failure_rate > self.config.half_open_ramp_failure_tolerance or signal in (
                    FailureSignal.SERVICE_UNAVAILABLE_503,
                    FailureSignal.TIMEOUT,
                    FailureSignal.RATE_LIMITED_429,
                ):
                    self._trip_to_open(from_hard_trip=False)
                return

            if self.state == CircuitState.CLOSED:
                weight = SIGNAL_WEIGHTS.get(signal, 1.0)
                self.calls_history.append((now, False, weight))
                if len(self.calls_history) > self.config.rolling_window_size:
                    self.calls_history.pop(0)

                # Check rolling failure rate once minimum volume threshold is reached
                if len(self.calls_history) >= self.config.minimum_call_volume_threshold:
                    weighted_failures = sum(w for (_, is_succ, w) in self.calls_history if not is_succ)
                    failure_rate = weighted_failures / len(self.calls_history)
                    if failure_rate >= self.config.failure_rate_threshold_to_open:
                        self._trip_to_open(from_hard_trip=False)

    def record_canary_result(self, is_success: bool) -> None:
        """
        Records the outcome of a supervised synthetic canary probe.
        Must be invoked when in HALF_OPEN to initiate the staged traffic ramp.
        """
        with self._lock:
            if self.state != CircuitState.HALF_OPEN:
                return

            if is_success:
                self.is_canary_passed = True
                self.half_open_step_index = 0
                self.half_open_step_start_time = time.time()
                self.half_open_step_calls.clear()
            else:
                # Canary probe failed -> immediately trip back to OPEN and back off reset timeout
                self._trip_to_open(from_hard_trip=False)

    def _trip_to_open(self, from_hard_trip: bool = False) -> None:
        """
        Transitions the circuit breaker to OPEN state and calculates reset timeout backoff.
        """
        if self.state == CircuitState.HALF_OPEN:
            self.current_reset_timeout = min(
                self.config.max_reset_timeout_seconds,
                self.current_reset_timeout * self.config.reset_timeout_backoff_multiplier,
            )
        else:
            self.current_reset_timeout = self.config.initial_reset_timeout_seconds

        self.state = CircuitState.OPEN
        self.last_state_change_time = time.time()
        self.is_canary_passed = False
        self.half_open_step_index = 0
        self.half_open_step_calls.clear()
        self.calls_history.clear()

    def _reset_to_closed(self) -> None:
        """
        Transitions the circuit breaker back to CLOSED state upon full recovery.
        """
        self.state = CircuitState.CLOSED
        self.last_state_change_time = time.time()
        self.current_reset_timeout = self.config.initial_reset_timeout_seconds
        self.is_canary_passed = False
        self.half_open_step_index = 0
        self.half_open_step_calls.clear()
        self.calls_history.clear()
