"""
telemetry/health_checker.py
===========================
Tiered Deep Health Check Evaluator for ENGONOW AI Worker.
Inspects PostgreSQL, Redis, Kafka, and in-memory LLM Circuit Breaker states
without executing live LLM scoring calls.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timezone
import logging

from providers.resilience.circuit_breaker import CircuitState

logger = logging.getLogger("HealthChecker")


async def get_deep_health_status(
    circuit_breakers: Optional[Dict[str, Any]] = None,
    redis_client: Optional[Any] = None,
    db_pool: Optional[Any] = None,
    kafka_client: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Computes the tiered system health status across core infrastructure and AI providers.

    Rules:
    - Status is UP if all components and primary AI provider are healthy.
    - Status is DEGRADED if the primary provider is OPEN but a valid working fallback exists.
    - Status is DOWN if all AI providers are OPEN or any core infrastructure component is unreachable.
    """
    components: Dict[str, Any] = {}

    # 1. PostgreSQL Health
    if db_pool is not None:
        try:
            if hasattr(db_pool, "is_connected") and not db_pool.is_connected():
                components["postgresql"] = "DOWN"
            elif hasattr(db_pool, "execute"):
                # Non-blocking ping
                await db_pool.execute("SELECT 1")
                components["postgresql"] = "UP"
            else:
                components["postgresql"] = "UP"
        except Exception as ex:
            logger.warning("[HEALTH CHECK] PostgreSQL ping failed: %s", ex)
            components["postgresql"] = "DOWN"
    else:
        components["postgresql"] = "UP"

    # 2. Redis Health
    if redis_client is not None:
        try:
            if hasattr(redis_client, "ping"):
                res = redis_client.ping()
                if hasattr(res, "__await__"):
                    await res
                components["redis"] = "UP"
            else:
                components["redis"] = "UP"
        except Exception as ex:
            logger.warning("[HEALTH CHECK] Redis ping failed: %s", ex)
            components["redis"] = "DOWN"
    else:
        components["redis"] = "UP"

    # 3. Kafka Health
    if kafka_client is not None:
        try:
            if hasattr(kafka_client, "is_healthy") and not kafka_client.is_healthy():
                components["kafka"] = "DOWN"
            else:
                components["kafka"] = "UP"
        except Exception as ex:
            logger.warning("[HEALTH CHECK] Kafka check failed: %s", ex)
            components["kafka"] = "DOWN"
    else:
        components["kafka"] = "UP"

    # 4. AI Provider Circuit Breaker States
    providers_summary: Dict[str, Any] = {}
    if circuit_breakers:
        all_down = True
        primary_healthy = True
        has_working_fallback = False

        for i, (name, cb) in enumerate(circuit_breakers.items()):
            state = cb.state if hasattr(cb, "state") else CircuitState.CLOSED

            if state == CircuitState.CLOSED:
                status_str = "UP"
                all_down = False
                if i > 0:
                    has_working_fallback = True
            elif state == CircuitState.HALF_OPEN:
                status_str = "DEGRADED"
                all_down = False
                if i > 0:
                    has_working_fallback = True
            else:  # OPEN
                status_str = "DOWN"
                if i == 0:
                    primary_healthy = False

            providers_summary[name] = status_str

        if all_down:
            providers_summary["overallStatus"] = "DOWN"
        elif not primary_healthy and has_working_fallback:
            providers_summary["overallStatus"] = "DEGRADED"
        elif not primary_healthy and not has_working_fallback:
            providers_summary["overallStatus"] = "DOWN"
        else:
            providers_summary["overallStatus"] = "UP"
    else:
        providers_summary = {"overallStatus": "UP"}

    components["aiProviders"] = providers_summary

    # 5. Derive System Overall Health
    overall_status = "UP"
    if (
        components.get("postgresql") == "DOWN"
        or components.get("redis") == "DOWN"
        or components.get("kafka") == "DOWN"
        or providers_summary.get("overallStatus") == "DOWN"
    ):
        overall_status = "DOWN"
    elif providers_summary.get("overallStatus") == "DEGRADED":
        overall_status = "DEGRADED"

    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": components,
    }
