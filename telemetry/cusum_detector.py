"""
telemetry/cusum_detector.py
===========================
Two-Sided Cumulative Sum (CUSUM) Drift Detection Algorithm for Real-Time Model Telemetry.
Tracks both model accuracy degradation (Upper Arm C+) and artificial over-accuracy / data contamination (Lower Arm C-).
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

@dataclass
class CusumState:
    subsystem: str
    criterion: str
    c_plus: float = 0.0
    c_minus: float = 0.0
    sample_count: int = 0
    last_updated_at: Optional[str] = None
    last_reset_at: Optional[str] = None

@dataclass
class CusumStepResult:
    new_state: CusumState
    d_i: float
    c_plus_triggered: bool
    c_minus_triggered: bool
    alert_severity: Optional[str] = None  # "CRITICAL", "WARNING", or None
    trigger_value: float = 0.0

class CusumDetector:
    """
    Two-Sided CUSUM Drift Detector.
    Tracks sequential drift from target MAE across AI scoring streams.
    """

    def __init__(self, target_mae: float = 0.50, k: float = 0.10, h: float = 2.50):
        """
        :param target_mae: Acceptable baseline MAE (default 0.50).
        :param k: Allowance / reference parameter (default 0.10).
        :param h: Decision boundary threshold (default 2.50).
        """
        self.target_mae = target_mae
        self.k = k
        self.h = h

    def step(self, current_state: CusumState, ai_score: float, reference_band: float) -> CusumStepResult:
        """
        Executes a single recursive CUSUM step given an AI score and Ground-Truth reference band.
        """
        signed_error = ai_score - reference_band
        d_i = round(abs(signed_error) - self.target_mae, 4)

        # Recursive updates
        c_plus_raw = round(current_state.c_plus + d_i - self.k, 4)
        new_c_plus = max(0.0, c_plus_raw)

        c_minus_raw = round(current_state.c_minus - d_i - self.k, 4)
        new_c_minus = max(0.0, c_minus_raw)

        sample_count = current_state.sample_count + 1
        now_iso = datetime.now(timezone.utc).isoformat()

        # Check threshold breach
        if new_c_plus >= self.h:
            # Upper arm breach -> Model degradation
            reset_state = CusumState(
                subsystem=current_state.subsystem,
                criterion=current_state.criterion,
                c_plus=0.0,
                c_minus=0.0,
                sample_count=sample_count,
                last_updated_at=now_iso,
                last_reset_at=now_iso
            )
            return CusumStepResult(
                new_state=reset_state,
                d_i=d_i,
                c_plus_triggered=True,
                c_minus_triggered=False,
                alert_severity="CRITICAL",
                trigger_value=new_c_plus
            )

        elif new_c_minus >= self.h:
            # Lower arm breach -> Contamination / caching bug / suspicious zero error
            reset_state = CusumState(
                subsystem=current_state.subsystem,
                criterion=current_state.criterion,
                c_plus=0.0,
                c_minus=0.0,
                sample_count=sample_count,
                last_updated_at=now_iso,
                last_reset_at=now_iso
            )
            return CusumStepResult(
                new_state=reset_state,
                d_i=d_i,
                c_plus_triggered=False,
                c_minus_triggered=True,
                alert_severity="WARNING",
                trigger_value=new_c_minus
            )

        else:
            updated_state = CusumState(
                subsystem=current_state.subsystem,
                criterion=current_state.criterion,
                c_plus=new_c_plus,
                c_minus=new_c_minus,
                sample_count=sample_count,
                last_updated_at=now_iso,
                last_reset_at=current_state.last_reset_at
            )
            return CusumStepResult(
                new_state=updated_state,
                d_i=d_i,
                c_plus_triggered=False,
                c_minus_triggered=False,
                alert_severity=None,
                trigger_value=0.0
            )
