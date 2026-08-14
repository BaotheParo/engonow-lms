"""
providers/config.py
====================
Loads and validates provider configuration from environment variables.
Uses python-dotenv. If python-dotenv is not installed, run:
    pip install python-dotenv
"""

import asyncio
import os
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()   # Loads .env from the project root

_PROMPT_LOCK = threading.Lock()


@lru_cache(maxsize=32)
def _load_prompt_sync(file_path: str) -> str:
    """
    Internal synchronous loader for prompt files with caching and resilient encoding.
    """
    path = Path(file_path)
    if not path.is_absolute():
        project_root = Path(__file__).resolve().parent.parent
        resolved = (project_root / path).resolve()
        if not resolved.exists():
            resolved = path.resolve()
    else:
        resolved = path

    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(
            f"Prompt file not found at '{file_path}' (resolved: '{resolved}'). "
            "Please verify IELTS_WRITING_SYSTEM_PROMPT_PATH and IELTS_WRITING_USER_PROMPT_PATH environment variables."
        )

    return resolved.read_text(encoding="utf-8", errors="replace").strip()


async def load_prompt_file(file_path: str) -> str:
    """
    Non-blocking, cached loader for external prompt template files.
    Offloads synchronous file I/O to a worker thread via asyncio.to_thread.

    Args:
        file_path: Relative or absolute path to the prompt file.

    Returns:
        The text content of the prompt file.

    Raises:
        FileNotFoundError: If the file does not exist at the resolved path.
    """
    return await asyncio.to_thread(_load_prompt_sync, file_path)


def clear_prompt_cache() -> None:
    """Clears the prompt template cache to support zero-downtime hot reloads."""
    with _PROMPT_LOCK:
        _load_prompt_sync.cache_clear()


@dataclass(frozen=True)
class WritingProviderConfig:
    """Immutable configuration snapshot for IELTS Writing evaluation."""

    gemini_api_key: str
    ai_model_name: str
    system_prompt_path: str
    user_prompt_path: str


def load_writing_config() -> WritingProviderConfig:
    """Builds WritingProviderConfig from environment variables."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_name = os.getenv(
        "AI_MODEL_NAME", os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    ).strip()

    system_prompt_path = os.getenv(
        "IELTS_WRITING_SYSTEM_PROMPT_PATH", "providers/prompts/writing_system.txt"
    ).strip()
    user_prompt_path = os.getenv(
        "IELTS_WRITING_USER_PROMPT_PATH", "providers/prompts/writing_user.txt"
    ).strip()

    return WritingProviderConfig(
        gemini_api_key=api_key,
        ai_model_name=model_name,
        system_prompt_path=system_prompt_path,
        user_prompt_path=user_prompt_path,
    )


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


@dataclass(frozen=True)
class WorkerConfig:
    """Immutable event-worker configuration snapshot."""

    broker_type: str
    speaking_requests_topic: str
    speaking_results_topic: str
    concurrency_limit: int
    kafka_bootstrap_servers: str
    kafka_consumer_group: str


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


def load_worker_config() -> WorkerConfig:
    """Load and validate asynchronous worker settings."""
    broker_type = os.getenv("BROKER_TYPE", "LOCAL").strip().upper()
    if broker_type not in ("LOCAL", "KAFKA"):
        raise ValueError(
            f"Invalid BROKER_TYPE='{broker_type}'. "
            "Accepted values: LOCAL | KAFKA."
        )

    requests_topic = os.getenv(
        "SPEAKING_REQUESTS_TOPIC", "ielts-speaking-requests"
    ).strip()
    results_topic = os.getenv(
        "SPEAKING_RESULTS_TOPIC", "ielts-speaking-results"
    ).strip()
    if not requests_topic or not results_topic:
        raise ValueError("Speaking request and result topic names must not be empty.")

    concurrency_limit = int(os.getenv("WORKER_CONCURRENCY_LIMIT", "5"))
    if concurrency_limit < 1:
        raise ValueError("WORKER_CONCURRENCY_LIMIT must be at least 1.")

    return WorkerConfig(
        broker_type=broker_type,
        speaking_requests_topic=requests_topic,
        speaking_results_topic=results_topic,
        concurrency_limit=concurrency_limit,
        kafka_bootstrap_servers=os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
        ).strip(),
        kafka_consumer_group=os.getenv(
            "KAFKA_CONSUMER_GROUP", "engonow-speaking-ai-workers"
        ).strip(),
    )


#  Module-level singleton 
# Loaded once at import time. All providers share this instance.
CONFIG: ProviderConfig = load_provider_config()
WORKER_CONFIG: WorkerConfig = load_worker_config()
WRITING_CONFIG: WritingProviderConfig = load_writing_config()
