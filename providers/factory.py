"""
providers/factory.py
=====================
Provider factory function. Returns the correct AbstractSpeakingProvider
implementation based on the SPEAKING_AI_PROVIDER environment variable.

Usage (in mock_ai_services.py):
    from providers.factory import get_speaking_provider
    _provider = get_speaking_provider()  # instantiated once at app startup
"""

import logging
from providers.base import AbstractSpeakingProvider
from providers.config import CONFIG

logger = logging.getLogger("engonow.provider.factory")


def get_speaking_provider() -> AbstractSpeakingProvider:
    """
    Returns the provider instance for the currently configured SPEAKING_AI_PROVIDER.

    Providers are imported lazily inside this function to avoid importing Azure SDK
    modules (which may not be installed) when SPEAKING_AI_PROVIDER=GROQ_LOCAL.
    """
    provider_name = CONFIG.provider_name
    logger.info("[PROVIDER FACTORY] Initialising provider: %s", provider_name)

    if provider_name == "GROQ_LOCAL":
        from providers.groq_local_provider import GroqLocalProvider
        return GroqLocalProvider(config=CONFIG)

    if provider_name == "AZURE":
        from providers.azure_provider import AzureProvider
        return AzureProvider(config=CONFIG)

    # This line is unreachable if load_provider_config() validated correctly,
    # but defensive guard for direct factory calls:
    raise ValueError(
        f"[PROVIDER FACTORY] Unknown provider '{provider_name}'. "
        f"Valid: GROQ_LOCAL | AZURE"
    )
