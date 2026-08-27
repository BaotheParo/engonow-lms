"""
telemetry/metrics.py
====================
Prometheus Metrics Instrumentation for Python AI Workers and Calibration Pipelines.
Exposes bounded-cardinality counters, histograms, and gauges.
"""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# 1. AI Calling, Latency & Reliability Metrics
GEMINI_API_REQUEST_DURATION = Histogram(
    "gemini_api_request_duration_seconds",
    "Gemini API invocation latency in seconds",
    ["model", "subsystem"],
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0, 21.0, 34.0]
)

GEMINI_API_REQUEST_TOTAL = Counter(
    "gemini_api_request_total",
    "Total count of Gemini API requests",
    ["model", "subsystem", "status_code"]
)

GEMINI_SCHEMA_VALIDATION_ERRORS = Counter(
    "gemini_extraction_schema_validation_errors_total",
    "Count of structured output validation failures",
    ["subsystem", "error_type"]
)

GEMINI_TOKEN_USAGE = Counter(
    "gemini_token_usage_total",
    "Total tokens consumed by Gemini API",
    ["model", "token_type"]
)

# 2. Speaking Acoustic & ASR Metrics
ASR_TRANSCRIPTION_DURATION = Histogram(
    "asr_transcription_duration_seconds",
    "Audio speech-to-text processing latency",
    ["audio_duration_bucket"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0]
)

ASR_TRANSCRIPTION_CONFIDENCE = Histogram(
    "asr_transcription_confidence",
    "Confidence score of ASR transcription",
    buckets=[0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0]
)

# 3. Calibration & Statistical Process Control (SPC) Gauges
CUSUM_C_PLUS_GAUGE = Gauge(
    "calibration_cusum_c_plus",
    "Live CUSUM upper arm value tracking model degradation",
    ["subsystem", "criterion"]
)

CUSUM_C_MINUS_GAUGE = Gauge(
    "calibration_cusum_c_minus",
    "Live CUSUM lower arm value tracking contamination/caching bugs",
    ["subsystem", "criterion"]
)

CALIBRATION_MAE_ROLLING_GAUGE = Gauge(
    "calibration_mae_rolling",
    "Rolling-window MAE metric against human reference",
    ["subsystem", "criterion", "window"]
)

CALIBRATION_SAMPLE_FORWARDED = Counter(
    "calibration_sample_forwarded_total",
    "Total ground-truth samples forwarded to drift pipeline",
    ["subsystem", "sampling_reason"]
)

# Legacy aliases for backward compatibility
WRITING_EVALUATION_LATENCY_SECONDS = Histogram(
    "writing_evaluation_duration_seconds",
    "Legacy Writing evaluation duration",
    ["provider"]
)
WRITING_EVALUATION_REQUESTS_TOTAL = Counter(
    "writing_evaluation_requests_total",
    "Legacy Writing evaluation requests",
    ["provider", "status"]
)
WRITING_EVALUATION_ERRORS_TOTAL = Counter(
    "writing_evaluation_errors_total",
    "Legacy Writing evaluation errors",
    ["provider", "error_type"]
)
EVALUATION_LATENCY_SECONDS = Histogram(
    "evaluation_duration_seconds",
    "Legacy evaluation duration",
    ["provider"]
)
EVALUATION_REQUESTS_TOTAL = Counter(
    "evaluation_requests_total",
    "Legacy evaluation requests",
    ["provider", "status"]
)
DRIFT_ALERTS_TOTAL = Counter(
    "drift_alerts_total",
    "Legacy drift alerts total"
)
GENUINE_WORD_COVERAGE = Histogram(
    "genuine_word_coverage_ratio",
    "Legacy genuine word coverage ratio",
    ["provider"],
    buckets=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)
