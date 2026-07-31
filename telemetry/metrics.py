"""Prometheus metric definitions for speaking evaluations."""

from prometheus_client import Counter, Gauge, Histogram


EVALUATION_REQUESTS_TOTAL = Counter(
    "engonow_speaking_evaluations_total",
    "Total number of evaluation requests processed",
    ["provider", "status"],
)

EVALUATION_LATENCY_SECONDS = Histogram(
    "engonow_speaking_evaluation_latency_seconds",
    "Latency of the AI evaluation process",
    ["provider"],
    buckets=(1.0, 2.5, 5.0, 7.5, 10.0, 15.0, 20.0, 30.0, 60.0),
)

GENUINE_WORD_COVERAGE = Histogram(
    "engonow_speaking_genuine_word_coverage",
    "Ratio of words with genuine confidence scores",
    ["provider"],
    buckets=(0.1, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

DRIFT_ALERTS_TOTAL = Counter(
    "engonow_speaking_drift_alerts_total",
    "Total number of statistical drift alerts triggered",
)

__all__ = [
    "DRIFT_ALERTS_TOTAL",
    "EVALUATION_LATENCY_SECONDS",
    "EVALUATION_REQUESTS_TOTAL",
    "GENUINE_WORD_COVERAGE",
]
