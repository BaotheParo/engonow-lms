"""
telemetry/metrics_server.py
===========================
Lightweight Prometheus Exporter Server / Handler exposing all collected metrics at /metrics.
Supports multi-process metrics aggregation via PROMETHEUS_MULTIPROC_DIR.
"""

import os
from prometheus_client import CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST, multiprocess
from typing import Any, Tuple


def get_prometheus_metrics() -> Tuple[bytes, str]:
    """
    Returns (metrics_payload_bytes, content_type_header).
    Aggregates metrics from all worker processes if PROMETHEUS_MULTIPROC_DIR is configured.
    """
    if "PROMETHEUS_MULTIPROC_DIR" in os.environ and os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry), CONTENT_TYPE_LATEST
    else:
        return generate_latest(), CONTENT_TYPE_LATEST


async def handle_metrics_endpoint(request: Any = None) -> Any:
    """
    FastAPI / aiohttp / WSGI compatible metrics endpoint handler.
    """
    data, content_type = get_prometheus_metrics()
    return data, content_type
