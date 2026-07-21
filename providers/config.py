"""
providers/config.py
====================
Loads and validates provider configuration from environment variables.
Uses python-dotenv. If python-dotenv is not installed, run:
    pip install python-dotenv
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()   # Loads .env from the project root


@dataclass(frozen=True)
class ProviderConfig:
    """Immutable configuration snapshot. Built once at startup."""

    # Primary toggle
    provider_name: str              # "GROQ_LOCAL" or "AZURE"

    # GROQ_LOCAL track
    groq_api_key:   str
    gemini_api_key: str
    gemini_model:   str

    # AZURE track
    azure_speech_key:      str
    azure_speech_region:   str
    azure_speech_language: str

    # Shared scoring parameters
    word_confidence_threshold: float
    pause_annotation_min_sec:  float
    enable_acoustic_diagnostics: bool

    # Fallback scores
    fallback_score_pr:  int
    fallback_score_fc:  int
    fallback_score_gra: int
    fallback_score_lr:  int


def load_provider_config() -> ProviderConfig:
    """
    Builds ProviderConfig from environment variables.
    Validates that the primary toggle is a recognised value.
    Raises ValueError if SPEAKING_AI_PROVIDER is unrecognised.
    """
    provider = os.getenv("SPEAKING_AI_PROVIDER", "GROQ_LOCAL").strip().upper()

    if provider not in ("GROQ_LOCAL", "AZURE"):
        raise ValueError(
            f"Invalid SPEAKING_AI_PROVIDER='{provider}'. "
            f"Accepted values: GROQ_LOCAL | AZURE. "
            f"Check your .env file."
        )

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if not groq_key or groq_key == "your_groq_api_key_here":
        groq_key = os.getenv("WHISPER_API_KEY", "").strip()

    return ProviderConfig(
        provider_name            = provider,
        groq_api_key             = groq_key,
        gemini_api_key           = os.getenv("GEMINI_API_KEY", ""),
        gemini_model             = os.getenv("GEMINI_MODEL", "models/gemini-2.5-flash"),
        azure_speech_key         = os.getenv("AZURE_SPEECH_KEY", "NOT_CONFIGURED"),
        azure_speech_region      = os.getenv("AZURE_SPEECH_REGION", "southeastasia"),
        azure_speech_language    = os.getenv("AZURE_SPEECH_LANGUAGE", "en-US"),
        word_confidence_threshold= float(os.getenv("WORD_CONFIDENCE_THRESHOLD", "0.70")),
        pause_annotation_min_sec = float(os.getenv("PAUSE_ANNOTATION_MIN_SEC", "0.50")),
        enable_acoustic_diagnostics = os.getenv("ENABLE_ACOUSTIC_DIAGNOSTICS", "true").lower() == "true",
        fallback_score_pr        = int(os.getenv("FALLBACK_SCORE_PR",  "4")),
        fallback_score_fc        = int(os.getenv("FALLBACK_SCORE_FC",  "4")),
        fallback_score_gra       = int(os.getenv("FALLBACK_SCORE_GRA", "4")),
        fallback_score_lr        = int(os.getenv("FALLBACK_SCORE_LR",  "4")),
    )


#  Module-level singleton 
# Loaded once at import time. All providers share this instance.
CONFIG: ProviderConfig = load_provider_config()
