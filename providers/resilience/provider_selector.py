"""
providers/resilience/provider_selector.py
=========================================
Multi-Provider Intelligent Selector and Dynamic Failover Router.
Scores eligible providers dynamically based on latency headroom and cost efficiency,
cascades across fallback candidates upon circuit breaker trips, and enforces
uncalibrated model governance.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import logging

from providers.resilience.circuit_breaker import CircuitBreaker, CircuitState, FailureSignal

logger = logging.getLogger("ProviderSelector")


@dataclass
class ProviderConfig:
    provider_id: str                          # e.g., "GEMINI_2_5_FLASH", "GROQ_LLAMA_3_3_70B", "AZURE_GPT_4O", "LOCAL_VLLM"
    priority: int                             # 1 = primary, 2 = secondary, etc.
    cost_per_thousand_input_tokens: Decimal
    cost_per_thousand_output_tokens: Decimal
    latency_sla_budget_seconds: float
    validated_mae: Optional[Decimal] = None   # From Gatekeeper run
    mae_validated_at: Optional[datetime] = None
    requires_human_review_fallback: bool = False

    def is_mae_valid(self, max_age_days: int = 90) -> bool:
        """
        Validates whether the provider possesses an active, unexpired Gatekeeper MAE benchmark.
        """
        if self.validated_mae is None or self.mae_validated_at is None:
            return False

        mae_time = self.mae_validated_at if self.mae_validated_at.tzinfo else self.mae_validated_at.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age = now - mae_time
        return age <= timedelta(days=max_age_days)


@dataclass
class SelectionResult:
    selected_provider_id: str
    evaluated_by: str                        # "AI_AUTO" or "AI_AUTO_UNCALIBRATED"
    requires_human_review: bool
    estimated_score: float
    candidate_cascade_order: List[str]


class IntelligentProviderSelector:
    """
    Intelligent routing engine selecting optimal LLM evaluation providers
    based on circuit breaker liveness, latency headroom, and token economics.
    """

    def __init__(
        self,
        providers: Dict[str, ProviderConfig],
        circuit_breakers: Dict[str, CircuitBreaker],
        latency_weight: float = 0.6,
        cost_weight: float = 0.4
    ):
        self.providers = providers
        self.circuit_breakers = circuit_breakers
        self.latency_weight = latency_weight
        self.cost_weight = cost_weight
        self.observed_p95_latencies: Dict[str, float] = {p: 1.0 for p in providers}

    def update_observed_latency(self, provider_id: str, p95_seconds: float) -> None:
        """
        Updates the moving P95 latency observation for a provider.
        """
        self.observed_p95_latencies[provider_id] = max(0.01, float(p95_seconds))

    def select_provider(self) -> SelectionResult:
        """
        Evaluates circuit breaker states, scores eligible candidates, and returns
        the highest-ranked provider along with the complete cascade order.

        Raises:
            RuntimeError("ALL_PROVIDERS_UNAVAILABLE") if all circuit breakers are OPEN
            or blocked by half-open ramp gating.
        """
        eligible: List[ProviderConfig] = []

        # 1. Hard Filter: check circuit breaker availability
        for p_id, p_cfg in self.providers.items():
            breaker = self.circuit_breakers.get(p_id)
            if breaker is not None and breaker.allow_request():
                eligible.append(p_cfg)

        if not eligible:
            logger.error("[SELECTOR EXHAUSTION] All configured LLM providers are unavailable (Circuit Breakers OPEN)")
            raise RuntimeError("ALL_PROVIDERS_UNAVAILABLE")

        # 2. Compute dynamic scores for eligible providers
        costs = [float(p.cost_per_thousand_input_tokens) for p in eligible]
        max_cost = max(costs) if costs else 0.0

        scored_candidates: List[Tuple[ProviderConfig, float]] = []
        for p in eligible:
            # Latency Headroom: clamp(1.0 - observed_p95 / sla_budget, 0.0, 1.0)
            obs_lat = self.observed_p95_latencies.get(p.provider_id, 1.0)
            budget = p.latency_sla_budget_seconds if p.latency_sla_budget_seconds > 0 else 1.0
            latency_headroom = max(0.0, min(1.0, 1.0 - (obs_lat / budget)))

            # Cost Efficiency: clamp(1.0 - cost / max_cost, 0.0, 1.0)
            cost_val = float(p.cost_per_thousand_input_tokens)
            if max_cost > 0.0:
                cost_efficiency = max(0.0, min(1.0, 1.0 - (cost_val / max_cost)))
            else:
                cost_efficiency = 1.0

            # Composite Score
            composite_score = round(
                (self.latency_weight * latency_headroom) + (self.cost_weight * cost_efficiency),
                4
            )
            scored_candidates.append((p, composite_score))

        # 3. Sort by priority ASCENDING (1 before 2), then score DESCENDING
        scored_candidates.sort(key=lambda item: (item[0].priority, -item[1]))

        cascade_order = [p.provider_id for (p, _) in scored_candidates]
        top_provider, top_score = scored_candidates[0]

        # 4. Enforce Gatekeeper Fallback Invariant
        is_calibrated = top_provider.is_mae_valid()
        if is_calibrated:
            evaluated_by = "AI_AUTO"
            requires_human_review = top_provider.requires_human_review_fallback
        else:
            evaluated_by = "AI_AUTO_UNCALIBRATED"
            requires_human_review = True
            logger.warning(
                "[UNCALIBRATED FALLBACK] Selected provider '%s' lacks valid Gatekeeper MAE. Flagged for human review.",
                top_provider.provider_id
            )

        return SelectionResult(
            selected_provider_id=top_provider.provider_id,
            evaluated_by=evaluated_by,
            requires_human_review=requires_human_review,
            estimated_score=top_score,
            candidate_cascade_order=cascade_order
        )
