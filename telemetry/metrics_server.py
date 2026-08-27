"""
telemetry/metrics_server.py
===========================
Lightweight Prometheus Exporter Server / Handler exposing all collected metrics at /metrics.
"""

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from typing import Any, Tuple

def get_prometheus_metrics() -> Tuple[bytes, str]:
    """
    Returns (metrics_payload_bytes, content_type_header).
    """
    return generate_latest(), CONTENT_TYPE_LATEST

async def handle_metrics_endpoint(request: Any = None) -> Any:
    """
    FastAPI / aiohttp / WSGI compatible metrics endpoint handler.
    """
    data, content_type = get_prometheus_metrics()
    return data, content_type
