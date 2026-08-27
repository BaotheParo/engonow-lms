"""
tests/test_prometheus_metrics.py
================================
Unit tests for Python Prometheus metrics instrumentation and exporter endpoint.
"""

import unittest
from telemetry.metrics import (
    GEMINI_API_REQUEST_DURATION,
    GEMINI_API_REQUEST_TOTAL,
    GEMINI_SCHEMA_VALIDATION_ERRORS,
    GEMINI_TOKEN_USAGE,
    CUSUM_C_PLUS_GAUGE,
    CUSUM_C_MINUS_GAUGE,
    CALIBRATION_MAE_ROLLING_GAUGE,
    CALIBRATION_SAMPLE_FORWARDED
)
from telemetry.metrics_server import get_prometheus_metrics

class TestPrometheusMetrics(unittest.TestCase):

    def test_gemini_request_metrics_recording(self):
        GEMINI_API_REQUEST_DURATION.labels(model="gemini-2.5-flash", subsystem="WRITING").observe(1.45)
        GEMINI_API_REQUEST_TOTAL.labels(model="gemini-2.5-flash", subsystem="WRITING", status_code="200").inc()
        GEMINI_TOKEN_USAGE.labels(model="gemini-2.5-flash", token_type="PROMPT").inc(450)

        data, content_type = get_prometheus_metrics()
        text = data.decode("utf-8")

        self.assertIn("gemini_api_request_duration_seconds_bucket", text)
        self.assertIn("gemini_api_request_total", text)
        self.assertIn("gemini_token_usage_total", text)

    def test_schema_validation_errors_metric(self):
        GEMINI_SCHEMA_VALIDATION_ERRORS.labels(subsystem="WRITING", error_type="json_parse").inc()
        GEMINI_SCHEMA_VALIDATION_ERRORS.labels(subsystem="WRITING", error_type="missing_field").inc(2)

        data, _ = get_prometheus_metrics()
        text = data.decode("utf-8")

        self.assertIn("gemini_extraction_schema_validation_errors_total", text)
        self.assertIn('error_type="json_parse"', text)
        self.assertIn('error_type="missing_field"', text)

    def test_spc_cusum_gauges(self):
        CUSUM_C_PLUS_GAUGE.labels(subsystem="WRITING", criterion="TASK_RESPONSE").set(1.85)
        CUSUM_C_MINUS_GAUGE.labels(subsystem="WRITING", criterion="TASK_RESPONSE").set(0.0)
        CALIBRATION_MAE_ROLLING_GAUGE.labels(subsystem="WRITING", criterion="TASK_RESPONSE", window="7d").set(0.38)
        CALIBRATION_SAMPLE_FORWARDED.labels(subsystem="WRITING", sampling_reason="SPOT_CHECK").inc()

        data, _ = get_prometheus_metrics()
        text = data.decode("utf-8")

        self.assertIn("calibration_cusum_c_plus", text)
        self.assertIn("calibration_cusum_c_minus", text)
        self.assertIn("calibration_mae_rolling", text)
        self.assertIn("calibration_sample_forwarded_total", text)

if __name__ == "__main__":
    unittest.main()
