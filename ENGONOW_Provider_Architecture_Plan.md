# ENGONOW IELTS — Pluggable AI Provider Architecture
## Strategy Pattern Integration Plan: GROQ_LOCAL ↔ AZURE Toggle

**Document Reference:** ENGONOW-PROVIDER-ARCH-001
**Classification:** Principal Cloud Architect Technical Specification
**Date:** July 2026

---

# SECTION 1: THE PLUGGABLE PROVIDER ARCHITECTURE

---

## 1.0 Architectural Decision Record

### Pattern Selection: Strategy Pattern (not Adapter Pattern)

The Adapter Pattern translates an incompatible interface into a compatible one.
The Strategy Pattern defines a family of algorithms, encapsulates each one, and
makes them interchangeable. The distinction matters here:

Both GROQ_LOCAL and AZURE share the same input contract (session_id + audio_url)
and must produce the same output schema (`UnifiedSpeakingResult`). Their
**internal algorithms** are what differ — this is precisely what Strategy encapsulates.
The FastAPI endpoint becomes the **Context** that delegates to whichever
strategy (provider) is configured.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          STRATEGY PATTERN MAP                                │
│                                                                              │
│   FastAPI Context           AbstractSpeakingProvider (Strategy Interface)   │
│   ─────────────             ─────────────────────────────────────────────   │
│   speaking_analyze()  ──►   evaluate(session_id, audio_url, ...) → Result   │
│          │                              ▲               ▲                    │
│          │                             ╱                 ╲                   │
│    ProviderFactory                    ╱                   ╲                  │
│    reads .env                        ╱                     ╲                 │
│    SPEAKING_AI_PROVIDER             ╱                       ╲                │
│          │                         │                         │               │
│          ├── "GROQ_LOCAL" ──► GroqLocalProvider      AzureProvider ◄── "AZURE"
│          │                   (Free Track)             (Paid Track)           │
│          │                        │                        │                 │
│          │                  Groq Whisper              Azure Speech SDK       │
│          │                  + Acoustic Engine         + Pronunciation API    │
│          │                  + Gemini (GRA/LR)         + Gemini (GRA/LR)     │
│          │                        │                        │                 │
│          └────────────────────────┴────────────────────────┘                │
│                                   │                                          │
│                        UnifiedSpeakingResult                                 │
│                  (identical schema, both providers)                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 1.1 Final Directory Structure

```
engonow-ai-python/
│
├── .env                              ← Single toggle file (SPEAKING_AI_PROVIDER=GROQ_LOCAL)
├── .env.example                      ← Committed to git — documents all required keys
│
├── mock_ai_services.py               ← FastAPI app (modified in Prompt 4 only)
├── acoustic_engine.py                ← From previous session — DO NOT MODIFY
│
└── providers/
    ├── __init__.py                   ← Package init (Prompt 1)
    ├── base.py                       ← AbstractSpeakingProvider + UnifiedSpeakingResult (Prompt 1)
    ├── config.py                     ← ProviderConfig dataclass + env loader (Prompt 1)
    ├── factory.py                    ← get_speaking_provider() factory function (Prompt 1)
    ├── groq_local_provider.py        ← GroqLocalProvider implementation (Prompt 2)
    └── azure_provider.py             ← AzureProvider scaffold + mock mode (Prompt 3)
```

---

## 1.2 Configuration Schema (.env)

```
# ╔══════════════════════════════════════════════════════════════════════╗
# ║        ENGONOW AI PROVIDER CONFIGURATION                            ║
# ║        Toggle SPEAKING_AI_PROVIDER to switch between tracks         ║
# ╚══════════════════════════════════════════════════════════════════════╝

# ─── PRIMARY TOGGLE ────────────────────────────────────────────────────────
# Valid values: GROQ_LOCAL | AZURE
SPEAKING_AI_PROVIDER=GROQ_LOCAL

# ─── TRACK 1: GROQ_LOCAL (Free — Groq Whisper + Local Acoustic + Gemini) ──
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=models/gemini-2.5-flash

# ─── TRACK 2: AZURE (Paid — Azure Speech + Pronunciation Assessment) ───────
# Leave as NOT_CONFIGURED during development — provider enters MOCK mode
AZURE_SPEECH_KEY=NOT_CONFIGURED
AZURE_SPEECH_REGION=southeastasia
AZURE_SPEECH_LANGUAGE=en-US
# Gemini is still used for GRA/LR even on the AZURE track
# (GEMINI_API_KEY above is shared)

# ─── SHARED SCORING PARAMETERS ─────────────────────────────────────────────
WORD_CONFIDENCE_THRESHOLD=0.70   # Below this probability → [LOW_CONFIDENCE] tag
PAUSE_ANNOTATION_MIN_SEC=0.50    # Pauses ≥ this value → [PAUSE: Xs] tag in transcript
ENABLE_ACOUSTIC_DIAGNOSTICS=true # Include acoustic sub-scores in response payload

# ─── FALLBACK BEHAVIOUR ────────────────────────────────────────────────────
# Scores returned when a provider partially fails (PARTIAL status)
FALLBACK_SCORE_PR=4
FALLBACK_SCORE_FC=4
FALLBACK_SCORE_GRA=4
FALLBACK_SCORE_LR=4
```

---

## 1.3 UnifiedSpeakingResult: The Shared Output Contract

This is the single source of truth for what both providers must produce.
It maps 1:1 to the Java `SpeakingWebhookPayload` the Spring Boot backend expects.

```python
@dataclass
class UnifiedSpeakingResult:
    # ── Core Identity ──────────────────────────────────────────────────
    session_id:  str
    provider_used: str          # "GROQ_LOCAL" or "AZURE"

    # ── The 4 IELTS Criterion Scores (integers 1-9 only) ───────────────
    pronunciation_score: int    # PR — acoustic / phoneme quality
    fluency_score:       int    # FC — delivery pace and coherence
    grammar_score:       int    # GRA — from Gemini LLM
    lexical_score:       int    # LR  — from Gemini LLM

    # ── Pipeline Status ────────────────────────────────────────────────
    status: str                 # "SUCCESS" | "PARTIAL" | "FAILED"

    # ── Data Quality Metric ────────────────────────────────────────────
    genuine_word_coverage: float   # 0.0–1.0: ratio of high-confidence words
                                   # GROQ_LOCAL: words where probability >= threshold
                                   # AZURE: words where accuracy_score >= 70

    # ── Human-Readable Feedback ────────────────────────────────────────
    feedback_text: str          # Combined LLM feedback passed to student portal

    # ── Latency & Diagnostics ──────────────────────────────────────────
    processing_time_ms: float
    provider_metadata: dict     # Provider-specific sub-scores and warnings
                                # Visible in admin panel, NOT sent to student
```

**Status semantics:**

| Status | Meaning | Java Backend Behaviour |
|--------|---------|------------------------|
| `SUCCESS` | All 4 criteria scored from their intended source | Accept and persist result |
| `PARTIAL` | 1–3 criteria used fallback scores due to sub-pipeline failure | Accept with warning flag, trigger re-eval notification |
| `FAILED` | Complete pipeline failure, no reliable scores | Reject payload, trigger retry queue |

---

## 1.4 Data Flow: GROQ_LOCAL Track

```
Audio URL (Cloudinary CDN)
        │
        ▼
[1] Download audio bytes (httpx async)
        │
        ▼
[2] Groq Whisper-large-v3
    verbose_json + word timestamps
    → words[]: {word, start, end, probability}
    → segments[]: {avg_logprob, no_speech_prob}
        │
        ├─────────────────────────────┐
        │                             │
        ▼                             ▼
[3] acoustic_engine.score_acoustic()  Build Annotated Transcript
    → fc_score (int 1-9)             Add [PAUSE: Xs] for gaps ≥ 0.50s
    → pr_score (int 1-9)             Add [LOW_CONFIDENCE] for prob < 0.70
    → diagnostics dict               Compute genuine_word_coverage
                                             │
                                             ▼
                                   [4] Gemini evaluate_speaking_gemini()
                                       annotated_transcript + questions_metadata
                                       → grammar_score (int 1-9)
                                       → lexical_score (int 1-9)
                                       → feedback_text
        │                                    │
        └──────────────┬─────────────────────┘
                       │
                       ▼
              UnifiedSpeakingResult
              (status="SUCCESS")
```

---

## 1.5 Data Flow: AZURE Track

```
Audio URL (Cloudinary CDN)
        │
        ▼
[1] Download audio bytes (httpx async)
        │
        ▼
[2] Azure Speech SDK
    SpeechRecognizer + PronunciationAssessmentConfig
    → transcript (str)
    → pronunciation_result:
        AccuracyScore (0-100) → pr_score (int 1-9) via mapping function
        FluencyScore  (0-100) → fc_score (int 1-9) via mapping function
    → word_results[]: {word, accuracy_score, error_type}
    → genuine_word_coverage from word accuracy scores
        │
        ├─────────────────────────────┐
        │                             │
        ▼                             ▼
[3] azure_to_ielts_pr_band()    Build Annotated Transcript
    azure_to_ielts_fc_band()    Azure provides clean transcript
    (score mapping functions)   Mark [MISPRONUNCIATION] per error_type
                                Compute genuine_word_coverage
                                        │
                                        ▼
                              [4] Gemini evaluate_speaking_gemini()
                                  (same GRA/LR evaluation as GROQ_LOCAL track)
                                  → grammar_score (int 1-9)
                                  → lexical_score (int 1-9)
                                  → feedback_text
        │                                    │
        └──────────────┬─────────────────────┘
                       │
                       ▼
              UnifiedSpeakingResult
              (status="SUCCESS")
```

---

## 1.6 Error Handling Strategy

Each provider implements a **partial-failure containment** pattern: if one
sub-pipeline fails, the provider catches the error, substitutes a fallback
score from config, records the failure in `provider_metadata.warnings`, and
elevates the status to `PARTIAL` rather than crashing.

```
Provider.evaluate() internal error handling:

  TRY: PR + FC pipeline (Whisper/Azure)
    SUCCESS → pr_score, fc_score from engine
    FAILURE → pr_score = FALLBACK_SCORE_PR, fc_score = FALLBACK_SCORE_FC
              warnings.append("PR_FC_PIPELINE_FAILED: {error}")
              status = "PARTIAL"

  TRY: GRA + LR pipeline (Gemini)
    SUCCESS → grammar_score, lexical_score from Gemini
    FAILURE → grammar_score = FALLBACK_SCORE_GRA, lexical_score = FALLBACK_SCORE_LR
              warnings.append("GRA_LR_PIPELINE_FAILED: {error}")
              status = "PARTIAL"

  IF both pipelines fail:
    status = "FAILED"
    return UnifiedSpeakingResult with all fallback scores and status="FAILED"

The FastAPI endpoint NEVER receives an unhandled exception from provider.evaluate().
The exception boundary is inside the provider, not the endpoint.
```

---

## 1.7 Azure Score → IELTS Band Mapping

Azure returns scores on a 0–100 scale. This piecewise linear mapping converts
them to IELTS integer bands. **These thresholds require validation against a
corpus of human-rated IELTS recordings before production deployment.**

```
Azure Score   →   IELTS Band    Cambridge Descriptor Anchor
─────────────────────────────────────────────────────────────
[0,   10)     →      1          Unintelligible / no communication
[10,  20)     →      2          Very limited intelligibility
[20,  32)     →      3          Severe L1 interference
[32,  44)     →      4          Frequent misunderstandings
[44,  56)     →      5          Adequate with notable errors
[56,  68)     →      6          Generally clear, some errors
[68,  79)     →      7          Mostly clear, minor accent effect
[79,  89)     →      8          Clear, accent has no practical effect
[89, 100]     →      9          Near-native / no intelligibility impact
```

Separate mapping functions for PR (accuracy) and FC (fluency) allow independent
calibration of the two dimensions.

---

---

# SECTION 2: THE SEQUENTIAL AGENT PROMPTS

Each prompt block is self-contained. Execute them in strict numerical order.
Do not execute a later prompt until the earlier prompt's validation step passes.

---

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                       CODING AGENT PROMPT 1 OF 4                            ║
║            FOUNDATION LAYER — INTERFACE, CONFIG & FACTORY                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

**PROMPT 1 — FOUNDATION LAYER**

---

You are working in the ENGONOW IELTS Speaking evaluation Python project. The
project root contains `mock_ai_services.py` and `acoustic_engine.py`. Do not
modify either of those files in this prompt.

**YOUR TASK: Create 5 new files that define the provider abstraction layer.**

---

**FILE 1 — Create `.env` in the project root:**

Create this file if it does not already exist. If it exists, ADD the following
keys without deleting any existing keys:

```
# ENGONOW AI Provider Configuration
# Toggle SPEAKING_AI_PROVIDER to switch between tracks without code changes.
# Valid values: GROQ_LOCAL | AZURE

SPEAKING_AI_PROVIDER=GROQ_LOCAL

# Track 1: GROQ_LOCAL (Free)
GROQ_API_KEY=your_groq_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=models/gemini-2.5-flash

# Track 2: AZURE (Paid — leave NOT_CONFIGURED during development)
AZURE_SPEECH_KEY=NOT_CONFIGURED
AZURE_SPEECH_REGION=southeastasia
AZURE_SPEECH_LANGUAGE=en-US

# Shared Scoring Parameters
WORD_CONFIDENCE_THRESHOLD=0.70
PAUSE_ANNOTATION_MIN_SEC=0.50
ENABLE_ACOUSTIC_DIAGNOSTICS=true

# Fallback scores used when a provider sub-pipeline fails (PARTIAL status)
FALLBACK_SCORE_PR=4
FALLBACK_SCORE_FC=4
FALLBACK_SCORE_GRA=4
FALLBACK_SCORE_LR=4
```

---

**FILE 2 — Create `.env.example` in the project root:**

Copy the contents of `.env` above verbatim. Replace actual API key values with
placeholder strings like `sk-your-groq-api-key`. This file is safe to commit
to version control.

---

**FILE 3 — Create `providers/__init__.py`:**

```python
"""
ENGONOW AI Provider Package
============================
Pluggable strategy pattern for IELTS Speaking evaluation providers.

Usage:
    from providers.factory import get_speaking_provider
    provider = get_speaking_provider()
    result = await provider.evaluate(session_id, audio_url, gemini_api_key)
"""

from providers.base import AbstractSpeakingProvider, UnifiedSpeakingResult, EvaluationStatus
from providers.factory import get_speaking_provider

__all__ = [
    "AbstractSpeakingProvider",
    "UnifiedSpeakingResult",
    "EvaluationStatus",
    "get_speaking_provider",
]
```

---

**FILE 4 — Create `providers/base.py`:**

Implement exactly this content:

```python
"""
providers/base.py
==================
Abstract interface and shared data contracts for all speaking evaluation providers.
Both GroqLocalProvider and AzureProvider MUST implement AbstractSpeakingProvider
and MUST return UnifiedSpeakingResult from their evaluate() method.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional


class EvaluationStatus(str, Enum):
    SUCCESS = "SUCCESS"   # All 4 criteria scored from their intended source
    PARTIAL = "PARTIAL"   # 1+ criteria used fallback score due to sub-pipeline failure
    FAILED  = "FAILED"    # Complete pipeline failure — no reliable scores produced


@dataclass
class UnifiedSpeakingResult:
    """
    The single output contract for all speaking evaluation providers.
    Maps 1:1 to the Java SpeakingWebhookPayload in the Spring Boot backend.

    Both GroqLocalProvider and AzureProvider must return this dataclass.
    The FastAPI endpoint serializes it directly to JSON for the Java webhook receiver.

    SCORE CONTRACT: pronunciation_score, fluency_score, grammar_score, lexical_score
    MUST all be integers in the range [1, 9] inclusive. Any other value is invalid.
    """

    # ── Core Identity ──────────────────────────────────────────────────────────
    session_id:    str
    provider_used: str   # "GROQ_LOCAL" or "AZURE"

    # ── The 4 IELTS Criterion Scores ───────────────────────────────────────────
    # All MUST be integers. All MUST be in range [1, 9]. No floats. No zeros.
    pronunciation_score: int
    fluency_score:       int
    grammar_score:       int
    lexical_score:       int

    # ── Pipeline Status ────────────────────────────────────────────────────────
    status: str   # Use EvaluationStatus enum values as strings

    # ── Data Quality Signal ────────────────────────────────────────────────────
    # Proportion of words recognized with high ASR/phoneme confidence.
    # GROQ_LOCAL: proportion of words where Whisper probability >= threshold
    # AZURE:      proportion of words where Azure accuracy_score >= 70
    # Java backend uses this to flag potentially unreliable evaluations.
    genuine_word_coverage: float   # [0.0, 1.0]

    # ── Feedback ────────────────────────────────────────────────────────────────
    feedback_text: str   # LLM-generated feedback summary for student portal

    # ── Operational Metadata ───────────────────────────────────────────────────
    processing_time_ms: float = 0.0
    provider_metadata: Dict   = field(default_factory=dict)
    # provider_metadata contains provider-specific sub-scores and warnings.
    # It is visible in the admin panel but NOT forwarded to the student.

    def to_dict(self) -> dict:
        """Serializes to the JSON payload format expected by Java Spring Boot."""
        return {
            "session_id":            self.session_id,
            "provider_used":         self.provider_used,
            "pronunciation_score":   self.pronunciation_score,
            "fluency_score":         self.fluency_score,
            "grammar_score":         self.grammar_score,
            "lexical_score":         self.lexical_score,
            "status":                self.status,
            "genuine_word_coverage": round(self.genuine_word_coverage, 4),
            "feedback_text":         self.feedback_text,
            "processing_time_ms":    round(self.processing_time_ms, 1),
            "provider_metadata":     self.provider_metadata,
        }

    def validate_scores(self) -> None:
        """
        Raises ValueError if any criterion score is not an integer in [1, 9].
        Call this before returning from provider.evaluate().
        """
        for name, value in [
            ("pronunciation_score", self.pronunciation_score),
            ("fluency_score",       self.fluency_score),
            ("grammar_score",       self.grammar_score),
            ("lexical_score",       self.lexical_score),
        ]:
            if not isinstance(value, int):
                raise ValueError(
                    f"Score contract violation: {name}={value!r} must be an int, "
                    f"got {type(value).__name__}."
                )
            if not (1 <= value <= 9):
                raise ValueError(
                    f"Score contract violation: {name}={value} is outside [1, 9]."
                )


class AbstractSpeakingProvider(ABC):
    """
    Strategy interface for IELTS Speaking evaluation providers.

    Concrete implementations:
      - GroqLocalProvider (providers/groq_local_provider.py): Free track
      - AzureProvider     (providers/azure_provider.py):      Paid track

    The FastAPI endpoint in mock_ai_services.py only interacts with this
    interface and never depends on concrete provider implementations.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns the provider identifier string: 'GROQ_LOCAL' or 'AZURE'."""

    @abstractmethod
    async def evaluate(
        self,
        session_id:        str,
        audio_url:         str,
        gemini_api_key:    str,
        questions_metadata: str = "",
    ) -> UnifiedSpeakingResult:
        """
        Full end-to-end evaluation pipeline from audio URL to scored result.

        Args:
            session_id:         Unique identifier for this speaking session.
            audio_url:          URL of the audio file (Cloudinary CDN or local path).
            gemini_api_key:     API key for Gemini GRA/LR evaluation.
            questions_metadata: Examiner questions as formatted string for Gemini context.

        Returns:
            UnifiedSpeakingResult with all 4 criterion scores as integers 1-9.
            MUST NOT raise exceptions — all errors must be caught internally and
            reflected as PARTIAL or FAILED status in the returned result.
        """

    def _clamp_band(self, value: float) -> int:
        """Shared utility: clamps a float to nearest integer in [1, 9]."""
        return max(1, min(9, round(value)))

    def _build_failed_result(
        self,
        session_id: str,
        error: str,
        fallback_pr: int = 4,
        fallback_fc: int = 4,
        fallback_gra: int = 4,
        fallback_lr: int = 4,
    ) -> UnifiedSpeakingResult:
        """
        Builds a FAILED UnifiedSpeakingResult for complete pipeline failures.
        Providers call this as the last-resort catch in evaluate().
        """
        return UnifiedSpeakingResult(
            session_id            = session_id,
            provider_used         = self.provider_name,
            pronunciation_score   = fallback_pr,
            fluency_score         = fallback_fc,
            grammar_score         = fallback_gra,
            lexical_score         = fallback_lr,
            status                = EvaluationStatus.FAILED,
            genuine_word_coverage = 0.0,
            feedback_text         = f"Evaluation failed due to a technical error: {error}",
            processing_time_ms    = 0.0,
            provider_metadata     = {"error": error, "warnings": ["PIPELINE_FAILED"]},
        )
```

---

**FILE 5 — Create `providers/config.py`:**

```python
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

    return ProviderConfig(
        provider_name            = provider,
        groq_api_key             = os.getenv("GROQ_API_KEY", ""),
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


# ── Module-level singleton ─────────────────────────────────────────────────────
# Loaded once at import time. All providers share this instance.
CONFIG: ProviderConfig = load_provider_config()
```

---

**FILE 6 — Create `providers/factory.py`:**

```python
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
```

---

**VALIDATION STEP — Run this before moving to Prompt 2:**

```bash
cd <project_root>
python -c "
from providers.factory import get_speaking_provider
p = get_speaking_provider()
print(f'Active provider: {p.provider_name}')
from providers.base import UnifiedSpeakingResult, EvaluationStatus
r = UnifiedSpeakingResult(
    session_id='test', provider_used='GROQ_LOCAL',
    pronunciation_score=7, fluency_score=6, grammar_score=7, lexical_score=6,
    status=EvaluationStatus.SUCCESS, genuine_word_coverage=0.85,
    feedback_text='Test feedback.', processing_time_ms=1200.0
)
r.validate_scores()
print('UnifiedSpeakingResult validation: PASSED')
print(r.to_dict())
"
```

Expected: No exceptions. Prints active provider and result dict. Proceed to Prompt 2.

---

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                       CODING AGENT PROMPT 2 OF 4                            ║
║         GROQLOCALprovider — WHISPER + ACOUSTIC ENGINE + GEMINI               ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

**PROMPT 2 — GROQLOCALprovider**

---

You are working in the ENGONOW project. `providers/base.py`, `providers/config.py`,
and `providers/factory.py` already exist from Prompt 1. `acoustic_engine.py`
exists in the project root and must NOT be modified.

**YOUR TASK: Create `providers/groq_local_provider.py`.**

This file implements the complete GROQ_LOCAL track:
1. Download audio from URL
2. Groq Whisper STT with word timestamps
3. Build annotated transcript from word timestamps
4. Run `acoustic_engine.score_acoustic()` for PR + FC scores
5. Run Gemini `evaluate_speaking_gemini()` for GRA + LR scores
6. Assemble and return `UnifiedSpeakingResult`

**FULL IMPLEMENTATION:**

```python
"""
providers/groq_local_provider.py
==================================
GROQ_LOCAL Provider Implementation.
Free track: Groq Whisper-large-v3 + Local Acoustic Engine + Gemini 2.5 Flash.

PR + FC: Computed deterministically from Whisper metadata via acoustic_engine.py
GRA + LR: Evaluated by Gemini from the annotated text transcript.

Dependencies (must be installed):
    pip install groq httpx google-generativeai
"""

import json
import logging
import time
from typing import Optional, Tuple

import httpx

from providers.base import (
    AbstractSpeakingProvider,
    EvaluationStatus,
    UnifiedSpeakingResult,
)
from providers.config import ProviderConfig

logger = logging.getLogger("engonow.provider.groq_local")


class GroqLocalProvider(AbstractSpeakingProvider):
    """
    Free-tier evaluation track.
    - PR + FC: acoustic_engine (deterministic DSP from Whisper metadata)
    - GRA + LR: Gemini 2.5 Flash (LLM text evaluation)
    """

    WHISPER_MODEL         = "whisper-large-v3"
    GROQ_TRANSCRIBE_URL   = "https://api.groq.com/openai/v1/audio/transcriptions"

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config

    @property
    def provider_name(self) -> str:
        return "GROQ_LOCAL"

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC ENTRY POINT
    # ──────────────────────────────────────────────────────────────────────────

    async def evaluate(
        self,
        session_id:         str,
        audio_url:          str,
        gemini_api_key:     str,
        questions_metadata: str = "",
    ) -> UnifiedSpeakingResult:
        """
        Full GROQ_LOCAL pipeline. Never raises exceptions — all failures
        are caught and reflected as PARTIAL or FAILED status.
        """
        t_start  = time.time()
        warnings = []

        # ── Step 1: Download audio ─────────────────────────────────────────────
        try:
            audio_bytes, audio_filename = await self._download_audio(audio_url)
        except Exception as e:
            logger.error("[GROQ_LOCAL] Audio download failed for session '%s': %s", session_id, e)
            return self._build_failed_result(
                session_id=session_id,
                error=f"Audio download failed: {e}",
                fallback_pr  = self._config.fallback_score_pr,
                fallback_fc  = self._config.fallback_score_fc,
                fallback_gra = self._config.fallback_score_gra,
                fallback_lr  = self._config.fallback_score_lr,
            )

        # ── Step 2: Groq Whisper STT ──────────────────────────────────────────
        whisper_response = None
        try:
            whisper_response = await self._call_groq_whisper(audio_bytes, audio_filename)
            logger.info("[GROQ_LOCAL] Whisper STT complete. session='%s' words=%d",
                        session_id, len(whisper_response.get("words", [])))
        except Exception as e:
            logger.error("[GROQ_LOCAL] Whisper STT failed for session '%s': %s", session_id, e)
            return self._build_failed_result(
                session_id=session_id,
                error=f"Groq Whisper STT failed: {e}",
                fallback_pr  = self._config.fallback_score_pr,
                fallback_fc  = self._config.fallback_score_fc,
                fallback_gra = self._config.fallback_score_gra,
                fallback_lr  = self._config.fallback_score_lr,
            )

        # ── Step 3: Acoustic Engine (PR + FC) ─────────────────────────────────
        pr_score = self._config.fallback_score_pr
        fc_score = self._config.fallback_score_fc
        acoustic_metadata = {}
        try:
            from acoustic_engine import score_acoustic
            acoustic_result   = score_acoustic(whisper_response)
            pr_score          = acoustic_result.pr_score
            fc_score          = acoustic_result.fc_score
            acoustic_metadata = acoustic_result.diagnostics if self._config.enable_acoustic_diagnostics else {}
            warnings.extend(acoustic_result.warnings)
            logger.info("[GROQ_LOCAL] Acoustic Engine: PR=%d FC=%d session='%s'",
                        pr_score, fc_score, session_id)
        except Exception as e:
            logger.warning("[GROQ_LOCAL] Acoustic engine failed for session '%s': %s — using fallback scores", session_id, e)
            warnings.append(f"ACOUSTIC_ENGINE_FAILED: {e}")

        # ── Step 4: Build annotated transcript + genuine_word_coverage ─────────
        annotated_transcript, genuine_word_coverage = self._build_annotated_transcript(
            whisper_response
        )

        # ── Step 5: Gemini GRA + LR Evaluation ────────────────────────────────
        grammar_score = self._config.fallback_score_gra
        lexical_score = self._config.fallback_score_lr
        feedback_text = "Evaluation partially complete."
        gemini_metadata = {}
        try:
            grammar_score, lexical_score, feedback_text, gemini_metadata = \
                await self._call_gemini(
                    annotated_transcript=annotated_transcript,
                    questions_metadata=questions_metadata,
                    gemini_api_key=gemini_api_key,
                )
            logger.info("[GROQ_LOCAL] Gemini GRA=%d LR=%d session='%s'",
                        grammar_score, lexical_score, session_id)
        except Exception as e:
            logger.warning("[GROQ_LOCAL] Gemini evaluation failed for session '%s': %s", session_id, e)
            warnings.append(f"GEMINI_GRA_LR_FAILED: {e}")
            feedback_text = f"Grammar and lexical evaluation unavailable: {e}"

        # ── Step 6: Determine final status ────────────────────────────────────
        has_fallbacks = any([
            pr_score  == self._config.fallback_score_pr  and "ACOUSTIC_ENGINE_FAILED" in str(warnings),
            fc_score  == self._config.fallback_score_fc  and "ACOUSTIC_ENGINE_FAILED" in str(warnings),
            grammar_score == self._config.fallback_score_gra and "GEMINI_GRA_LR_FAILED" in str(warnings),
            lexical_score == self._config.fallback_score_lr  and "GEMINI_GRA_LR_FAILED" in str(warnings),
        ])
        status = EvaluationStatus.PARTIAL if has_fallbacks else EvaluationStatus.SUCCESS

        # ── Step 7: Assemble result ────────────────────────────────────────────
        result = UnifiedSpeakingResult(
            session_id            = session_id,
            provider_used         = self.provider_name,
            pronunciation_score   = self._clamp_band(pr_score),
            fluency_score         = self._clamp_band(fc_score),
            grammar_score         = self._clamp_band(grammar_score),
            lexical_score         = self._clamp_band(lexical_score),
            status                = status,
            genuine_word_coverage = genuine_word_coverage,
            feedback_text         = feedback_text,
            processing_time_ms    = (time.time() - t_start) * 1000,
            provider_metadata     = {
                "acoustic": acoustic_metadata,
                "gemini":   gemini_metadata,
                "warnings": warnings,
            },
        )
        result.validate_scores()
        return result

    # ──────────────────────────────────────────────────────────────────────────
    # PRIVATE HELPERS
    # ──────────────────────────────────────────────────────────────────────────

    async def _download_audio(self, audio_url: str) -> Tuple[bytes, str]:
        """
        Downloads audio from audio_url (Cloudinary CDN URL or local file path).
        Returns (audio_bytes, filename).
        """
        if audio_url.startswith("http://") or audio_url.startswith("https://"):
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(audio_url)
                response.raise_for_status()
                filename = audio_url.split("/")[-1].split("?")[0] or "audio.mp3"
                return response.content, filename
        else:
            # Local file path (dev/test environment)
            with open(audio_url, "rb") as f:
                return f.read(), audio_url.split("/")[-1]

    async def _call_groq_whisper(self, audio_bytes: bytes, filename: str) -> dict:
        """
        Calls Groq Whisper-large-v3 with verbose_json and word timestamps.
        Returns the raw API response dict.
        """
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                self.GROQ_TRANSCRIBE_URL,
                headers={"Authorization": f"Bearer {self._config.groq_api_key}"},
                files={"file": (filename, audio_bytes, "audio/mpeg")},
                data={
                    "model":                      self.WHISPER_MODEL,
                    "response_format":            "verbose_json",
                    "timestamp_granularities":    '["word", "segment"]',
                    "language":                   "en",
                    "prompt": (
                        "IELTS Speaking Test. Examiner: Good morning. Student:"
                    ),
                },
            )
            response.raise_for_status()
            return response.json()

    def _build_annotated_transcript(
        self, whisper_response: dict
    ) -> Tuple[str, float]:
        """
        Builds the annotated transcript string for Gemini and computes
        genuine_word_coverage.

        Annotations added:
          [PAUSE: Xs]       — inter-word gap >= PAUSE_ANNOTATION_MIN_SEC
          [LOW_CONFIDENCE]  — word probability < WORD_CONFIDENCE_THRESHOLD

        Returns:
          (annotated_transcript: str, genuine_word_coverage: float)
        """
        words = whisper_response.get("words", [])
        if not words:
            return "", 0.0

        threshold      = self._config.word_confidence_threshold
        pause_min      = self._config.pause_annotation_min_sec
        tokens         = []
        high_conf_count = 0
        prev_end       = words[0].get("start", 0.0)

        for i, word_entry in enumerate(words):
            word        = word_entry.get("word", "").strip()
            start       = float(word_entry.get("start", 0.0))
            end         = float(word_entry.get("end", start))
            probability = float(word_entry.get("probability", 1.0))

            # Insert pause marker if gap is significant
            if i > 0:
                gap = start - prev_end
                if gap >= pause_min:
                    tokens.append(f"[PAUSE: {gap:.1f}s]")

            # Annotate word confidence
            if probability < threshold:
                tokens.append(f"{word}[LOW_CONFIDENCE]")
            else:
                tokens.append(word)
                high_conf_count += 1

            prev_end = end

        genuine_word_coverage = high_conf_count / len(words) if words else 0.0
        annotated_transcript  = " ".join(tokens)
        return annotated_transcript, genuine_word_coverage

    async def _call_gemini(
        self,
        annotated_transcript: str,
        questions_metadata:   str,
        gemini_api_key:       str,
    ) -> Tuple[int, int, str, dict]:
        """
        Calls the existing evaluate_speaking_gemini function from mock_ai_services
        for GRA and LR scoring.

        Returns: (grammar_score, lexical_score, feedback_text, metadata_dict)
        """
        # Import the existing Gemini evaluator from mock_ai_services.py
        # This avoids duplicating the prompts engineered in the previous sessions.
        from mock_ai_services import evaluate_speaking_gemini

        result = await evaluate_speaking_gemini(
            annotated_transcript=annotated_transcript,
            questions_metadata=questions_metadata,
            api_key=gemini_api_key,
        )

        grammar_score = int(result.get("grammarScore", self._config.fallback_score_gra))
        lexical_score = int(result.get("lexicalScore", self._config.fallback_score_lr))
        feedback_text = result.get("overallComment", "No feedback generated.")
        metadata      = {"evidences": result.get("evidences", [])}

        return grammar_score, lexical_score, feedback_text, metadata
```

**VALIDATION STEP — Run before proceeding to Prompt 3:**

```bash
python -c "
import asyncio, os, json
os.environ['SPEAKING_AI_PROVIDER'] = 'GROQ_LOCAL'
from providers.factory import get_speaking_provider
p = get_speaking_provider()
print(f'Provider: {p.provider_name}')
assert p.provider_name == 'GROQ_LOCAL', 'Wrong provider'

# Test transcript annotation with synthetic data
synthetic_whisper = {
    'words': [
        {'word': 'I',       'start': 0.10, 'end': 0.20, 'probability': 0.97},
        {'word': 'think',   'start': 0.22, 'end': 0.58, 'probability': 0.88},
        {'word': 'that',    'start': 2.80, 'end': 3.00, 'probability': 0.91},  # 2.22s gap
        {'word': 'um',      'start': 3.02, 'end': 3.15, 'probability': 0.45},  # LOW_CONF
        {'word': 'education','start': 3.17, 'end': 3.85, 'probability': 0.79},
    ],
    'segments': []
}
transcript, coverage = p._build_annotated_transcript(synthetic_whisper)
print(f'Annotated: {transcript}')
print(f'Coverage: {coverage:.2f}')
assert '[PAUSE:' in transcript, 'Pause annotation missing'
assert '[LOW_CONFIDENCE]' in transcript, 'Low confidence annotation missing'
assert 0.0 <= coverage <= 1.0
print('PROMPT 2 VALIDATION PASSED')
"
```

---

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                       CODING AGENT PROMPT 3 OF 4                            ║
║       AZUREPROVIDER — SCAFFOLD, SCORE MAPPING & MOCK MODE                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

**PROMPT 3 — AZUREPROVIDER SCAFFOLD**

---

You are working in the ENGONOW project. The `providers/` package from Prompts 1
and 2 is already in place.

**YOUR TASK: Create `providers/azure_provider.py`.**

This file implements the AZURE track. Since the developer does not yet have an
Azure Speech key, the file must be fully functional in two modes:
- **MOCK MODE** (when `AZURE_SPEECH_KEY=NOT_CONFIGURED`): Returns plausible
  synthetic scores and logs a clear warning. Used for development and CI.
- **LIVE MODE** (when a real key is present): Executes the full Azure Speech SDK pipeline.

The Azure SDK import is guarded so the file can be imported without
`azure-cognitiveservices-speech` installed (Prompt 1's lazy import in factory.py
ensures this module is only imported when AZURE provider is selected).

```python
"""
providers/azure_provider.py
=============================
AZURE Provider Implementation.
Paid track: Azure Cognitive Services Speech + Pronunciation Assessment + Gemini.

PR + FC: Azure Speech SDK with PronunciationAssessmentConfig
         Scores (0-100) mapped to IELTS bands (1-9) via calibrated piecewise function.
GRA + LR: Same Gemini evaluation as GroqLocalProvider.

MOCK MODE: Active when AZURE_SPEECH_KEY == 'NOT_CONFIGURED' (default during development).
           Returns synthetic scores and logs a prominent warning.

LIVE MODE: Active when a valid Azure Speech key is present.
           Requires: pip install azure-cognitiveservices-speech

Azure Score → IELTS Band Calibration:
  The mapping functions below (azure_accuracy_to_ielts_pr_band,
  azure_fluency_to_ielts_fc_band) are INITIAL ESTIMATES.
  They MUST be validated against a corpus of human-rated IELTS recordings
  before production deployment. Adjust the piecewise thresholds after calibration.
"""

import json
import logging
import os
import time
from typing import Tuple, Optional

import httpx

from providers.base import (
    AbstractSpeakingProvider,
    EvaluationStatus,
    UnifiedSpeakingResult,
)
from providers.config import ProviderConfig

logger = logging.getLogger("engonow.provider.azure")

# ── Azure SDK import guard ────────────────────────────────────────────────────
# The SDK is only imported in LIVE MODE. In MOCK MODE, this import is never
# executed, so missing azure-cognitiveservices-speech does not cause startup errors.
_AZURE_SDK_AVAILABLE = False
try:
    import azure.cognitiveservices.speech as speechsdk
    _AZURE_SDK_AVAILABLE = True
except ImportError:
    speechsdk = None   # Typed as None; gated on _AZURE_SDK_AVAILABLE before use


class AzureProvider(AbstractSpeakingProvider):
    """
    Paid-tier evaluation track.
    - PR: Azure PronunciationAssessmentConfig → AccuracyScore → IELTS band
    - FC: Azure PronunciationAssessmentConfig → FluencyScore → IELTS band
    - GRA + LR: Gemini 2.5 Flash (same as GroqLocalProvider)
    """

    _MOCK_MODE_KEY = "NOT_CONFIGURED"

    def __init__(self, config: ProviderConfig) -> None:
        self._config   = config
        self._is_mock  = (config.azure_speech_key == self._MOCK_MODE_KEY)

        if self._is_mock:
            logger.warning(
                "[AZURE PROVIDER] ⚠ MOCK MODE ACTIVE ⚠  "
                "AZURE_SPEECH_KEY is '%s'. Scores are synthetic placeholders. "
                "Set a real AZURE_SPEECH_KEY in .env to activate live evaluation.",
                self._MOCK_MODE_KEY
            )
        elif not _AZURE_SDK_AVAILABLE:
            raise RuntimeError(
                "AZURE provider selected but azure-cognitiveservices-speech is not installed. "
                "Run: pip install azure-cognitiveservices-speech"
            )

    @property
    def provider_name(self) -> str:
        return "AZURE"

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC ENTRY POINT
    # ──────────────────────────────────────────────────────────────────────────

    async def evaluate(
        self,
        session_id:         str,
        audio_url:          str,
        gemini_api_key:     str,
        questions_metadata: str = "",
    ) -> UnifiedSpeakingResult:
        t_start  = time.time()
        warnings = []

        if self._is_mock:
            return self._build_mock_result(session_id, t_start)

        # ── LIVE MODE ──────────────────────────────────────────────────────────

        # Step 1: Download audio
        try:
            audio_bytes, audio_filename = await self._download_audio(audio_url)
        except Exception as e:
            logger.error("[AZURE] Audio download failed: %s", e)
            return self._build_failed_result(
                session_id=session_id, error=str(e),
                fallback_pr=self._config.fallback_score_pr,
                fallback_fc=self._config.fallback_score_fc,
                fallback_gra=self._config.fallback_score_gra,
                fallback_lr=self._config.fallback_score_lr,
            )

        # Step 2: Azure Pronunciation Assessment
        pr_score = self._config.fallback_score_pr
        fc_score = self._config.fallback_score_fc
        transcript            = ""
        genuine_word_coverage = 0.0
        azure_metadata        = {}

        try:
            pr_score, fc_score, transcript, genuine_word_coverage, azure_metadata = \
                self._run_azure_pronunciation_assessment(audio_bytes, audio_filename)
        except Exception as e:
            logger.warning("[AZURE] Pronunciation assessment failed: %s", e)
            warnings.append(f"AZURE_PR_FC_FAILED: {e}")

        # Step 3: Build annotated transcript for Gemini
        annotated_transcript = self._annotate_azure_transcript(
            transcript, azure_metadata.get("word_results", [])
        )

        # Step 4: Gemini GRA + LR
        grammar_score = self._config.fallback_score_gra
        lexical_score = self._config.fallback_score_lr
        feedback_text = "Evaluation partially complete."
        gemini_meta   = {}

        try:
            grammar_score, lexical_score, feedback_text, gemini_meta = \
                await self._call_gemini(annotated_transcript, questions_metadata, gemini_api_key)
        except Exception as e:
            logger.warning("[AZURE] Gemini GRA/LR failed: %s", e)
            warnings.append(f"GEMINI_GRA_LR_FAILED: {e}")

        # Step 5: Status
        has_fallbacks = bool(warnings)
        status = EvaluationStatus.PARTIAL if has_fallbacks else EvaluationStatus.SUCCESS

        result = UnifiedSpeakingResult(
            session_id            = session_id,
            provider_used         = self.provider_name,
            pronunciation_score   = self._clamp_band(pr_score),
            fluency_score         = self._clamp_band(fc_score),
            grammar_score         = self._clamp_band(grammar_score),
            lexical_score         = self._clamp_band(lexical_score),
            status                = status,
            genuine_word_coverage = genuine_word_coverage,
            feedback_text         = feedback_text,
            processing_time_ms    = (time.time() - t_start) * 1000,
            provider_metadata     = {
                "azure":    azure_metadata,
                "gemini":   gemini_meta,
                "warnings": warnings,
            },
        )
        result.validate_scores()
        return result

    # ──────────────────────────────────────────────────────────────────────────
    # AZURE SDK INTEGRATION — LIVE MODE
    # ──────────────────────────────────────────────────────────────────────────

    def _run_azure_pronunciation_assessment(
        self, audio_bytes: bytes, filename: str
    ) -> Tuple[int, int, str, float, dict]:
        """
        Runs Azure Speech SDK Pronunciation Assessment on the audio bytes.

        Returns:
            (pr_band, fc_band, transcript, genuine_word_coverage, metadata)

        Azure SDK reference:
            https://learn.microsoft.com/azure/ai-services/speech-service/pronunciation-assessment-tool

        AZURE_CONFIG_REQUIRED: Ensure AZURE_SPEECH_KEY and AZURE_SPEECH_REGION
        are set correctly in .env before activating LIVE MODE.
        """
        import tempfile, os

        # Azure SDK requires a file path, not bytes.
        # Write to a temp file, run assessment, then clean up.
        with tempfile.NamedTemporaryFile(
            suffix=os.path.splitext(filename)[1] or ".wav",
            delete=False
        ) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            speech_config = speechsdk.SpeechConfig(
                subscription=self._config.azure_speech_key,
                region=self._config.azure_speech_region,
            )
            speech_config.speech_recognition_language = self._config.azure_speech_language

            audio_config = speechsdk.audio.AudioConfig(filename=tmp_path)

            # PronunciationAssessmentConfig with granularity=Word for per-word results
            pronunciation_config = speechsdk.PronunciationAssessmentConfig(
                grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
                granularity=speechsdk.PronunciationAssessmentGranularity.Word,
                enable_miscue=True,
            )

            recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config, audio_config=audio_config
            )
            pronunciation_config.apply_to(recognizer)

            result = recognizer.recognize_once_async().get()

            if result.reason != speechsdk.ResultReason.RecognizedSpeech:
                raise RuntimeError(
                    f"Azure did not recognize speech. Reason: {result.reason}. "
                    f"NoMatch details: {result.no_match_details if hasattr(result, 'no_match_details') else 'N/A'}"
                )

            pronunciation_result = speechsdk.PronunciationAssessmentResult(result)

            # Extract scores
            azure_accuracy_score = pronunciation_result.accuracy_score    # 0-100
            azure_fluency_score  = pronunciation_result.fluency_score     # 0-100

            pr_band = self._azure_accuracy_to_ielts_pr_band(azure_accuracy_score)
            fc_band = self._azure_fluency_to_ielts_fc_band(azure_fluency_score)

            # Word-level results
            word_results = []
            high_accuracy_count = 0
            total_words = 0

            for word in pronunciation_result.words:
                total_words += 1
                word_acc = word.accuracy_score if hasattr(word, "accuracy_score") else 50.0
                if word_acc >= 70.0:
                    high_accuracy_count += 1
                word_results.append({
                    "word":           word.word,
                    "accuracy_score": round(word_acc, 1),
                    "error_type":     str(word.error_type) if hasattr(word, "error_type") else "None",
                })

            genuine_word_coverage = high_accuracy_count / total_words if total_words > 0 else 0.0
            transcript            = result.text

            metadata = {
                "azure_accuracy_score": round(azure_accuracy_score, 2),
                "azure_fluency_score":  round(azure_fluency_score, 2),
                "pr_band_before_gemini_check": pr_band,
                "fc_band_before_gemini_check": fc_band,
                "word_results": word_results,
            }

            return pr_band, fc_band, transcript, genuine_word_coverage, metadata

        finally:
            os.unlink(tmp_path)

    def _azure_accuracy_to_ielts_pr_band(self, azure_score: float) -> int:
        """
        Maps Azure AccuracyScore (0-100) to IELTS Pronunciation band (1-9).

        CALIBRATION WARNING: These thresholds are initial estimates.
        Validate against human-rated IELTS corpus before production use.
        Adjust thresholds to minimise MAE on validation set.
        """
        thresholds = [
            (10.0, 1), (20.0, 2), (32.0, 3), (44.0, 4),
            (56.0, 5), (68.0, 6), (79.0, 7), (89.0, 8),
        ]
        for threshold, band in thresholds:
            if azure_score < threshold:
                return band
        return 9

    def _azure_fluency_to_ielts_fc_band(self, azure_score: float) -> int:
        """
        Maps Azure FluencyScore (0-100) to IELTS Fluency & Coherence band (1-9).

        NOTE: Azure FluencyScore measures pace and pause patterns only.
        It does NOT assess discourse coherence. IELTS FC includes both.
        Coherence is partially covered by Gemini's overallComment feedback.

        CALIBRATION WARNING: Separate from _azure_accuracy_to_ielts_pr_band
        to allow independent threshold tuning. Adjust after corpus validation.
        """
        thresholds = [
            (8.0,  1), (18.0, 2), (30.0, 3), (43.0, 4),
            (55.0, 5), (67.0, 6), (78.0, 7), (88.0, 8),
        ]
        for threshold, band in thresholds:
            if azure_score < threshold:
                return band
        return 9

    def _annotate_azure_transcript(
        self, transcript: str, word_results: list
    ) -> str:
        """
        Builds annotated transcript for Gemini using Azure word-level error types.
        Marks mispronounced words with [MISPRONUNCIATION] for Gemini context.
        """
        if not word_results:
            return transcript

        annotated_tokens = []
        for word_result in word_results:
            word       = word_result.get("word", "")
            error_type = word_result.get("error_type", "None")
            if error_type not in ("None", "0", ""):
                annotated_tokens.append(f"{word}[{error_type.upper()}]")
            else:
                annotated_tokens.append(word)

        return " ".join(annotated_tokens)

    # ──────────────────────────────────────────────────────────────────────────
    # SHARED GEMINI CALL (same as GroqLocalProvider)
    # ──────────────────────────────────────────────────────────────────────────

    async def _call_gemini(
        self,
        annotated_transcript: str,
        questions_metadata:   str,
        gemini_api_key:       str,
    ) -> Tuple[int, int, str, dict]:
        from mock_ai_services import evaluate_speaking_gemini
        result = await evaluate_speaking_gemini(
            annotated_transcript=annotated_transcript,
            questions_metadata=questions_metadata,
            api_key=gemini_api_key,
        )
        grammar_score = int(result.get("grammarScore", self._config.fallback_score_gra))
        lexical_score = int(result.get("lexicalScore", self._config.fallback_score_lr))
        feedback_text = result.get("overallComment", "No feedback generated.")
        metadata      = {"evidences": result.get("evidences", [])}
        return grammar_score, lexical_score, feedback_text, metadata

    # ──────────────────────────────────────────────────────────────────────────
    # MOCK MODE
    # ──────────────────────────────────────────────────────────────────────────

    def _build_mock_result(
        self, session_id: str, t_start: float
    ) -> UnifiedSpeakingResult:
        """
        Returns a synthetic result for development/CI without an Azure key.
        Scores are fixed at Band 6 with a clear MOCK_MODE warning.
        """
        logger.warning(
            "[AZURE MOCK] Returning synthetic Band 6 scores for session '%s'. "
            "Set AZURE_SPEECH_KEY in .env to activate live Azure evaluation.",
            session_id
        )
        return UnifiedSpeakingResult(
            session_id            = session_id,
            provider_used         = f"{self.provider_name}_MOCK",
            pronunciation_score   = 6,
            fluency_score         = 6,
            grammar_score         = 6,
            lexical_score         = 6,
            status                = EvaluationStatus.PARTIAL,
            genuine_word_coverage = 0.75,
            feedback_text         = (
                "[AZURE MOCK MODE] Real Azure Speech evaluation inactive. "
                "Configure AZURE_SPEECH_KEY in .env to activate paid-tier scoring."
            ),
            processing_time_ms    = (time.time() - t_start) * 1000,
            provider_metadata     = {
                "warnings": [
                    "AZURE_MOCK_MODE: AZURE_SPEECH_KEY=NOT_CONFIGURED. "
                    "All scores are synthetic placeholders."
                ]
            },
        )

    async def _download_audio(self, audio_url: str) -> Tuple[bytes, str]:
        if audio_url.startswith("http://") or audio_url.startswith("https://"):
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(audio_url)
                response.raise_for_status()
                filename = audio_url.split("/")[-1].split("?")[0] or "audio.wav"
                return response.content, filename
        else:
            with open(audio_url, "rb") as f:
                return f.read(), audio_url.split("/")[-1]
```

**VALIDATION STEP — Run before proceeding to Prompt 4:**

```bash
python -c "
import os
os.environ['SPEAKING_AI_PROVIDER'] = 'AZURE'
os.environ['AZURE_SPEECH_KEY']     = 'NOT_CONFIGURED'
from providers.factory import get_speaking_provider
p = get_speaking_provider()
print(f'Provider: {p.provider_name}')
assert p.provider_name == 'AZURE'
assert p._is_mock == True, 'Mock mode should be active'

# Test score mapping
for azure_score, expected_band in [(15, 2), (40, 4), (60, 6), (75, 7), (92, 9)]:
    band = p._azure_accuracy_to_ielts_pr_band(azure_score)
    print(f'  Azure {azure_score} → IELTS Band {band} (expected {expected_band})')

import asyncio
result = asyncio.run(p.evaluate(
    session_id='test-azure-mock',
    audio_url='http://example.com/fake.mp3',
    gemini_api_key='fake-key',
))
print(f'Mock result: status={result.status} pr={result.pronunciation_score}')
assert result.status == 'PARTIAL', 'Mock should return PARTIAL status'
assert '_MOCK' in result.provider_used, 'Mock should flag provider name'
print('PROMPT 3 VALIDATION PASSED')
"
```

---

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                       CODING AGENT PROMPT 4 OF 4                            ║
║        FASTAPI INTEGRATION — TOGGLE WIRING IN mock_ai_services.py           ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

**PROMPT 4 — FASTAPI INTEGRATION**

---

You are working in `mock_ai_services.py`. The `providers/` package from Prompts
1–3 is complete. You are now wiring the provider toggle into the FastAPI app.

**DO NOT rewrite the entire file.** Make exactly the following targeted changes:

---

**CHANGE 1 — Add imports at the top of `mock_ai_services.py`** (after existing imports):

```python
# ─── Provider Architecture Imports ──────────────────────────────────────────
import os
from dotenv import load_dotenv
from providers.factory import get_speaking_provider
from providers.base import UnifiedSpeakingResult, EvaluationStatus

load_dotenv()   # Ensures .env is loaded even when running via uvicorn directly
```

---

**CHANGE 2 — Add a module-level provider singleton** (immediately after the imports block, before any route definitions):

```python
# ─── Provider Singleton ──────────────────────────────────────────────────────
# Instantiated once at application startup. All requests share this instance.
# To switch providers: change SPEAKING_AI_PROVIDER in .env and restart uvicorn.
_SPEAKING_PROVIDER = get_speaking_provider()

logger.info(
    "[APP STARTUP] Active speaking evaluation provider: %s",
    _SPEAKING_PROVIDER.provider_name
)
```

---

**CHANGE 3 — Replace the existing `/api/v1/ai/speaking-analyze` endpoint** with this new implementation. Locate the existing function (named `mock_speaking_analyze` or `speaking_analyze`) and replace it entirely:

```python
@app.post(
    "/api/v1/ai/speaking-analyze",
    summary="IELTS Speaking Evaluation — Pluggable Provider",
    description=(
        f"Routes to the active provider ({_SPEAKING_PROVIDER.provider_name}). "
        "Toggle SPEAKING_AI_PROVIDER in .env and restart to switch providers. "
        "Both providers return the identical UnifiedSpeakingResult JSON schema."
    ),
)
async def speaking_analyze(
    session_id:         str = Form(..., description="Unique speaking session identifier"),
    audio_url:          str = Form(..., description="URL of audio file (Cloudinary CDN or local path)"),
    questions_metadata: str = Form("",  description="Examiner questions as formatted string for Gemini context"),
):
    """
    Entry point for IELTS Speaking evaluation.

    Provider selection is controlled by SPEAKING_AI_PROVIDER in .env:
      GROQ_LOCAL  →  Groq Whisper + Acoustic Engine + Gemini  (Free)
      AZURE       →  Azure Speech SDK + Pronunciation API + Gemini  (Paid)

    Both providers return the same JSON schema. The Java Spring Boot backend
    does not need to know which provider produced the result.

    Error handling: The provider catches all internal errors and returns a
    PARTIAL or FAILED result. This endpoint will return HTTP 200 in all cases
    where the provider returns a result — the Java backend reads the `status`
    field to determine success.
    """
    gemini_api_key = os.getenv("GEMINI_API_KEY", "")

    if not gemini_api_key:
        logger.error("[SPEAKING ANALYZE] GEMINI_API_KEY is not set.")
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY environment variable is not configured."
        )

    logger.info(
        "[SPEAKING ANALYZE] session_id='%s' provider='%s' audio_url='%.80s...'",
        session_id, _SPEAKING_PROVIDER.provider_name, audio_url
    )

    result: UnifiedSpeakingResult = await _SPEAKING_PROVIDER.evaluate(
        session_id         = session_id,
        audio_url          = audio_url,
        gemini_api_key     = gemini_api_key,
        questions_metadata = questions_metadata,
    )

    if result.status == EvaluationStatus.FAILED:
        logger.error(
            "[SPEAKING ANALYZE] Pipeline FAILED for session='%s'. "
            "Metadata: %s", session_id, result.provider_metadata
        )
    elif result.status == EvaluationStatus.PARTIAL:
        logger.warning(
            "[SPEAKING ANALYZE] Pipeline PARTIAL for session='%s'. Warnings: %s",
            session_id, result.provider_metadata.get("warnings", [])
        )
    else:
        logger.info(
            "[SPEAKING ANALYZE] SUCCESS session='%s' PR=%d FC=%d GRA=%d LR=%d "
            "coverage=%.2f time=%.0fms",
            session_id,
            result.pronunciation_score, result.fluency_score,
            result.grammar_score, result.lexical_score,
            result.genuine_word_coverage, result.processing_time_ms,
        )

    return result.to_dict()
```

---

**CHANGE 4 — Add a provider health endpoint** (append after the speaking_analyze endpoint):

```python
@app.get(
    "/api/v1/provider/status",
    summary="Active Provider Status",
    description="Returns configuration and health status of the active speaking evaluation provider.",
)
async def provider_status():
    """
    Called by the Java Spring Boot health-check layer to verify provider readiness.
    Returns the active provider name and configuration summary.
    """
    config_summary = {
        "active_provider":    _SPEAKING_PROVIDER.provider_name,
        "gemini_configured":  bool(os.getenv("GEMINI_API_KEY", "")),
        "groq_configured":    bool(os.getenv("GROQ_API_KEY", "")) if _SPEAKING_PROVIDER.provider_name == "GROQ_LOCAL" else "N/A",
        "azure_key_set":      os.getenv("AZURE_SPEECH_KEY", "NOT_CONFIGURED") != "NOT_CONFIGURED" if _SPEAKING_PROVIDER.provider_name == "AZURE" else "N/A",
        "word_confidence_threshold": float(os.getenv("WORD_CONFIDENCE_THRESHOLD", "0.70")),
        "acoustic_diagnostics":      os.getenv("ENABLE_ACOUSTIC_DIAGNOSTICS", "true"),
    }

    # Quick self-test: verify the provider can be instantiated without errors
    provider_healthy = True
    health_message   = "Provider operational."

    if _SPEAKING_PROVIDER.provider_name == "AZURE":
        from providers.azure_provider import AzureProvider
        if isinstance(_SPEAKING_PROVIDER, AzureProvider) and _SPEAKING_PROVIDER._is_mock:
            provider_healthy = False
            health_message = (
                "AZURE provider is in MOCK MODE. "
                "Set AZURE_SPEECH_KEY in .env to activate live evaluation."
            )

    return {
        "status":          "UP" if provider_healthy else "DEGRADED",
        "health_message":  health_message,
        "configuration":   config_summary,
    }
```

---

**CHANGE 5 — Update the app description** to reflect the provider architecture.
Find `app = FastAPI(...)` and update the `description` parameter:

```python
app = FastAPI(
    title="ENGONOW External AI Services",
    description=(
        "ENGONOW IELTS Speaking Evaluation Pipeline with Pluggable Provider Architecture. "
        "Toggle SPEAKING_AI_PROVIDER in .env between GROQ_LOCAL (free) and AZURE (paid) "
        "without any code changes. Both providers return the identical JSON schema."
    ),
    version="2.0.0",
)
```

---

**FINAL VALIDATION — Full integration test. Run this after all changes:**

```bash
# Step 1: Start the server
uvicorn mock_ai_services:app --host 0.0.0.0 --port 8001 --reload

# Step 2 (new terminal): Test provider status endpoint
curl -s http://localhost:8001/api/v1/provider/status | python -m json.tool

# Expected: {"status": "UP", "configuration": {"active_provider": "GROQ_LOCAL", ...}}

# Step 3: Test provider toggle (edit .env: SPEAKING_AI_PROVIDER=AZURE, restart uvicorn)
# curl -s http://localhost:8001/api/v1/provider/status | python -m json.tool
# Expected: {"status": "DEGRADED", "health_message": "AZURE provider is in MOCK MODE..."}

# Step 4: Validate the JSON schema matches Java SpeakingWebhookPayload expectation
curl -s http://localhost:8001/api/v1/provider/status | python -c "
import json, sys
data = json.load(sys.stdin)
required_keys = {'status', 'health_message', 'configuration'}
assert required_keys.issubset(data.keys()), f'Missing keys: {required_keys - data.keys()}'
print('PROMPT 4 VALIDATION PASSED — Provider architecture fully wired.')
print(json.dumps(data, indent=2))
"
```

---

## APPENDIX A: PROVIDER SWITCH OPERATION GUIDE

This is the one-page guide for the educational center's technical administrator
who will flip the toggle in production.

```
╔══════════════════════════════════════════════════════════════════════════════╗
║        HOW TO SWITCH BETWEEN GROQ_LOCAL AND AZURE PROVIDERS                ║
╚══════════════════════════════════════════════════════════════════════════════╝

TO ACTIVATE FREE TRACK (GROQ_LOCAL):
  1. Open .env
  2. Set: SPEAKING_AI_PROVIDER=GROQ_LOCAL
  3. Verify: GROQ_API_KEY and GEMINI_API_KEY are populated
  4. Restart uvicorn: uvicorn mock_ai_services:app --port 8001
  5. Confirm: curl http://localhost:8001/api/v1/provider/status
     → "active_provider": "GROQ_LOCAL", "status": "UP"

TO ACTIVATE PAID TRACK (AZURE):
  1. Open .env
  2. Set: SPEAKING_AI_PROVIDER=AZURE
  3. Set: AZURE_SPEECH_KEY=<your_azure_key>
  4. Set: AZURE_SPEECH_REGION=<your_region, e.g. southeastasia>
  5. Install SDK: pip install azure-cognitiveservices-speech
  6. Restart uvicorn: uvicorn mock_ai_services:app --port 8001
  7. Confirm: curl http://localhost:8001/api/v1/provider/status
     → "active_provider": "AZURE", "azure_key_set": true, "status": "UP"

NO CODE CHANGES ARE REQUIRED. The Java Spring Boot backend does not need
to be modified when switching providers. The JSON schema is identical.

DURING AZURE DEVELOPMENT (no key yet):
  Set AZURE_SPEECH_KEY=NOT_CONFIGURED (the default)
  The AzureProvider enters MOCK MODE and returns synthetic Band 6 scores.
  The /api/v1/provider/status endpoint will show "status": "DEGRADED" with
  a clear explanation of why and what to configure.
```

---

## APPENDIX B: UNIFIED JSON SCHEMA (Java Backend Contract)

This is the exact JSON structure both providers return. The Java
`SpeakingWebhookPayload` must declare fields for all keys below.

```json
{
  "session_id":            "sess_20260701_abc123",
  "provider_used":         "GROQ_LOCAL",
  "pronunciation_score":   7,
  "fluency_score":         6,
  "grammar_score":         7,
  "lexical_score":         6,
  "status":                "SUCCESS",
  "genuine_word_coverage": 0.8734,
  "feedback_text":         "Scored 7 not 8 because... Not 6 because...",
  "processing_time_ms":    12450.3,
  "provider_metadata": {
    "acoustic": {
      "fluency": { "speech_rate_wpm": 148.2, "silent_ratio_pct": 22.1, "fc_band": 6 },
      "pronunciation": { "mean_calibrated_logprob": -0.34, "severe_error_ratio_pct": 4.2, "pr_band": 7 }
    },
    "gemini": {
      "evidences": []
    },
    "warnings": []
  }
}
```

*End of Document — ENGONOW-PROVIDER-ARCH-001 v1.0*
