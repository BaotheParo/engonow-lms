"""Lightweight statistical drift detection for streaming telemetry."""

from __future__ import annotations

import math


class CUSUMDriftDetector:
    """Detect persistent downward shifts from an expected process mean.

    The detector operates on standardized observations and retains only the
    lower one-sided CUSUM. Positive shifts therefore reset accumulated
    evidence instead of raising an alert.
    """

    __slots__ = (
        "target_mean",
        "std_dev",
        "slack_k",
        "threshold_h",
        "s_low",
    )

    def __init__(
        self,
        target_mean: float,
        std_dev: float,
        slack_k: float = 0.5,
        threshold_h: float = 5.0,
    ) -> None:
        if not math.isfinite(target_mean):
            raise ValueError("target_mean must be finite")
        if not math.isfinite(std_dev) or std_dev <= 0.0:
            raise ValueError("std_dev must be a finite value greater than zero")
        if not math.isfinite(slack_k) or slack_k < 0.0:
            raise ValueError("slack_k must be a finite non-negative value")
        if not math.isfinite(threshold_h) or threshold_h <= 0.0:
            raise ValueError(
                "threshold_h must be a finite value greater than zero"
            )

        self.target_mean = float(target_mean)
        self.std_dev = float(std_dev)
        self.slack_k = float(slack_k)
        self.threshold_h = float(threshold_h)
        self.s_low = 0.0

    def update(self, value: float) -> bool:
        """Incorporate an observation and report a downward drift signal."""
        if not math.isfinite(value):
            raise ValueError("value must be finite")

        z = (value - self.target_mean) / self.std_dev
        self.s_low = max(0.0, self.s_low - z - self.slack_k)
        return self.s_low > self.threshold_h

    def reset(self) -> None:
        """Clear accumulated evidence after an alert or baseline change."""
        self.s_low = 0.0


__all__ = ["CUSUMDriftDetector"]
