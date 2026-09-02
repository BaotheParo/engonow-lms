"""
providers/factory.py
=====================
Provider Factory and Lifecycle Registry for IELTS Speaking & Writing AI Providers.
Manages provider instantiation, circuit breaker injection, metrics hooking, and
intelligent failover selector routing.
"""

import logging
from typing import Any, Dict, Optional, Union

from providers.base import AbstractSpeakingProvider, AbstractWritingProvider
from providers.gemini_speaking_provider import GeminiSpeakingProvider

logger = logging.getLogger("engonow.provider.factory")


class ProviderFactory:
    """
    Centralized factory and registry for all IELTS Speaking & Writing evaluation providers.
    Manages provider lifecycles, circuit breaker state machines, intelligent routing selectors,
    and telemetry metrics clients.
    """

    def __init__(
        self,
        gemini_client: Any = None,
        circuit_breaker_registry: Optional[Dict[str, Any]] = None,
        provider_selector: Any = None,
        metrics_client: Any = None,
        config: Any = None,
    ):
        self._gemini_client = gemini_client
        self._circuit_breaker_registry = circuit_breaker_registry or {}
        self._provider_selector = provider_selector
        self._metrics_client = metrics_client
        self._config = config
        self._speaking_providers: Dict[str, Any] = {}
        self._writing_providers: Dict[str, Any] = {}

        self._register_speaking_providers()
        self._register_writing_providers()

    def _register_speaking_providers(self) -> None:
        """Instantiates and registers supported speaking evaluation providers."""
        gemini_cb = self._circuit_breaker_registry.get("GEMINI_2_5_FLASH_SPEAKING")
        model_name = getattr(self._config, "gemini_model_name", "gemini-2.5-flash") or "gemini-2.5-flash"

        self._speaking_providers["GEMINI_2_5_FLASH_SPEAKING"] = GeminiSpeakingProvider(
            gemini_client=self._gemini_client,
            circuit_breaker=gemini_cb,
            metrics_client=self._metrics_client,
            model_name=model_name,
        )

    def _register_writing_providers(self) -> None:
        """Instantiates and registers supported writing evaluation providers."""
        try:
            from providers.gemini_writing_provider import GeminiWritingProvider
            from providers.config import WRITING_CONFIG
            self._writing_providers["GEMINI_2_5_FLASH_WRITING"] = GeminiWritingProvider(config=WRITING_CONFIG)
        except Exception as ex:
            logger.debug("[PROVIDER FACTORY] Writing provider lazy registration note: %s", ex)

    def register_speaking_provider(self, provider_id: str, provider: Any) -> None:
        """Manually registers an additional speaking provider instance (e.g. mock or fallback)."""
        self._speaking_providers[provider_id] = provider

    def get_speaking_provider(self, provider_id: Optional[str] = None) -> GeminiSpeakingProvider:
        """
        Retrieves a speaking evaluation provider instance:
        - If provider_id is explicitly passed, returns that specific provider.
        - If provider_id is None, delegates to provider_selector to pick the optimal healthy provider.
        - Raises ValueError if requested provider_id is not registered.
        """
        if provider_id is not None:
            if provider_id not in self._speaking_providers:
                raise ValueError(
                    f"[PROVIDER FACTORY] Speaking provider '{provider_id}' is not registered. "
                    f"Available providers: {list(self._speaking_providers.keys())}"
                )
            return self._speaking_providers[provider_id]

        # Dynamic selection via provider selector
        if self._provider_selector is not None:
            selected_id = None
            if hasattr(self._provider_selector, "select_provider"):
                try:
                    selection = self._provider_selector.select_provider()
                    selected_id = getattr(selection, "selected_provider_id", selection)
                except Exception as ex:
                    logger.warning("[PROVIDER FACTORY] Provider selector error: %s", ex)
            elif hasattr(self._provider_selector, "select"):
                try:
                    selection = self._provider_selector.select(candidates=list(self._speaking_providers.keys()))
                    selected_id = getattr(selection, "selected_provider_id", selection)
                except Exception as ex:
                    logger.warning("[PROVIDER FACTORY] Provider selector error: %s", ex)

            if selected_id and selected_id in self._speaking_providers:
                return self._speaking_providers[selected_id]

        # Default fallback to primary provider
        if "GEMINI_2_5_FLASH_SPEAKING" in self._speaking_providers:
            return self._speaking_providers["GEMINI_2_5_FLASH_SPEAKING"]

        if self._speaking_providers:
            return next(iter(self._speaking_providers.values()))

        raise ValueError("[PROVIDER FACTORY] No speaking providers are registered.")

    def get_writing_provider(self, provider_id: Optional[str] = None) -> Any:
        """Retrieves a writing evaluation provider instance."""
        if provider_id is not None:
            if provider_id not in self._writing_providers:
                raise ValueError(
                    f"[PROVIDER FACTORY] Writing provider '{provider_id}' is not registered. "
                    f"Available providers: {list(self._writing_providers.keys())}"
                )
            return self._writing_providers[provider_id]

        if "GEMINI_2_5_FLASH_WRITING" in self._writing_providers:
            return self._writing_providers["GEMINI_2_5_FLASH_WRITING"]

        if self._writing_providers:
            return next(iter(self._writing_providers.values()))

        from providers.gemini_writing_provider import GeminiWritingProvider
        from providers.config import WRITING_CONFIG
        return GeminiWritingProvider(config=WRITING_CONFIG)


# ------------------------------------------------------------------------------
# Backward-Compatible Module-Level Helper Functions
# ------------------------------------------------------------------------------

def get_speaking_provider(provider_id: Optional[str] = None) -> Any:
    """
    Returns the speaking provider instance.
    Maintains compatibility with legacy mock_ai_services and test suites.
    """
    from providers.config import CONFIG
    provider_name = provider_id or CONFIG.provider_name

    if provider_name in ("GEMINI_2_5_FLASH_SPEAKING", "GEMINI", "GEMINI_SPEAKING"):
        factory = ProviderFactory()
        return factory.get_speaking_provider("GEMINI_2_5_FLASH_SPEAKING")

    if provider_name == "GROQ_LOCAL":
        from providers.groq_local_provider import GroqLocalProvider
        return GroqLocalProvider(config=CONFIG)

    if provider_name == "AZURE":
        from providers.azure_provider import AzureProvider
        return AzureProvider(config=CONFIG)

    # If it's a registered provider in ProviderFactory
    factory = ProviderFactory()
    return factory.get_speaking_provider(provider_id)


def get_writing_provider(provider_id: Optional[str] = None) -> Any:
    """
    Returns the singleton or newly initialized GeminiWritingProvider instance.
    """
    from providers.gemini_writing_provider import GeminiWritingProvider
    from providers.config import WRITING_CONFIG
    return GeminiWritingProvider(config=WRITING_CONFIG)
