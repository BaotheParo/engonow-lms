"""GROQ_LOCAL speaking evaluation provider.

Combines Groq Whisper word timestamps, the local acoustic engine, and the
existing Gemini text evaluator into the common provider result contract.
"""

import logging
import mimetypes
import time
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import unquote, urlparse

import httpx

from acoustic_engine import is_nonlexical_filler, score_acoustic
from providers.base import (
    AbstractSpeakingProvider,
    EvaluationStatus,
    UnifiedSpeakingResult,
)
from providers.config import ProviderConfig


logger = logging.getLogger("engonow.provider.groq_local")


class GroqLocalProvider(AbstractSpeakingProvider):
    """Free track: Groq STT, local PR/FC, and Gemini GRA/LR."""

    WHISPER_MODEL = "whisper-large-v3"
    GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config

    @property
    def provider_name(self) -> str:
        return "GROQ_LOCAL"

    async def evaluate(
        self,
        session_id: str,
        audio_url: Optional[str],
        gemini_api_key: str,
        questions_metadata: str = "",
        audio_bytes: Optional[bytes] = None,
        audio_filename: str = "audio.mp3",
    ) -> UnifiedSpeakingResult:
        """Run the complete pipeline without propagating operational errors."""
        started_at = time.time()
        warnings = []

        try:
            if audio_bytes is None:
                if not audio_url:
                    raise ValueError("Either audio_url or audio_bytes must be provided")
                audio_bytes, audio_filename = await self._download_audio(audio_url)
            elif not audio_bytes:
                raise ValueError("Uploaded audio file is empty")
        except Exception as exc:
            logger.error(
                "[GROQ_LOCAL] Audio download failed for session '%s': %s",
                session_id,
                exc,
            )
            return self._failed_result(session_id, f"Audio download failed: {exc}", started_at)

        try:
            whisper_response = await self._call_groq_whisper(audio_bytes, audio_filename)
            logger.info(
                "[GROQ_LOCAL] Whisper STT complete. session='%s' words=%d",
                session_id,
                len(whisper_response.get("words", [])),
            )
        except Exception as exc:
            logger.error(
                "[GROQ_LOCAL] Whisper STT failed for session '%s': %s",
                session_id,
                exc,
            )
            return self._failed_result(session_id, f"Groq Whisper STT failed: {exc}", started_at)

        pr_score = self._config.fallback_score_pr
        fc_score = self._config.fallback_score_fc
        acoustic_metadata = {}
        acoustic_failed = False
        try:
            acoustic_result = score_acoustic(whisper_response)
            pr_score = acoustic_result.pr_score
            fc_score = acoustic_result.fc_score
            if self._config.enable_acoustic_diagnostics:
                acoustic_metadata = acoustic_result.diagnostics
            warnings.extend(acoustic_result.warnings)
            logger.info(
                "[GROQ_LOCAL] Acoustic Engine: PR=%d FC=%d session='%s'",
                pr_score,
                fc_score,
                session_id,
            )
        except Exception as exc:
            acoustic_failed = True
            logger.warning(
                "[GROQ_LOCAL] Acoustic engine failed for session '%s': %s; using fallbacks",
                session_id,
                exc,
            )
            warnings.append(f"ACOUSTIC_ENGINE_FAILED: {exc}")

        annotated_transcript, genuine_word_coverage = self._build_annotated_transcript(
            whisper_response
        )

        grammar_score = self._config.fallback_score_gra
        lexical_score = self._config.fallback_score_lr
        feedback_text = "Evaluation partially complete."
        gemini_metadata = {}
        gemini_failed = False
        try:
            (
                grammar_score,
                lexical_score,
                feedback_text,
                gemini_metadata,
            ) = await self._call_gemini(
                annotated_transcript=annotated_transcript,
                questions_metadata=questions_metadata,
                gemini_api_key=gemini_api_key,
            )
            logger.info(
                "[GROQ_LOCAL] Gemini GRA=%d LR=%d session='%s'",
                grammar_score,
                lexical_score,
                session_id,
            )
        except Exception as exc:
            gemini_failed = True
            logger.warning(
                "[GROQ_LOCAL] Gemini evaluation failed for session '%s': %s",
                session_id,
                exc,
            )
            warnings.append(f"GEMINI_GRA_LR_FAILED: {exc}")
            feedback_text = f"Grammar and lexical evaluation unavailable: {exc}"

        result = UnifiedSpeakingResult(
            session_id=session_id,
            provider_used=self.provider_name,
            pronunciation_score=self._clamp_band(pr_score),
            fluency_score=self._clamp_band(fc_score),
            grammar_score=self._clamp_band(grammar_score),
            lexical_score=self._clamp_band(lexical_score),
            status=(
                EvaluationStatus.PARTIAL
                if acoustic_failed or gemini_failed
                else EvaluationStatus.SUCCESS
            ),
            genuine_word_coverage=genuine_word_coverage,
            feedback_text=feedback_text,
            processing_time_ms=(time.time() - started_at) * 1000,
            provider_metadata={
                "acoustic": acoustic_metadata,
                "gemini": gemini_metadata,
                "warnings": warnings,
            },
        )
        result.validate_scores()
        return result

    def _failed_result(
        self, session_id: str, error: str, started_at: float
    ) -> UnifiedSpeakingResult:
        result = self._build_failed_result(
            session_id=session_id,
            error=error,
            fallback_pr=self._clamp_band(self._config.fallback_score_pr),
            fallback_fc=self._clamp_band(self._config.fallback_score_fc),
            fallback_gra=self._clamp_band(self._config.fallback_score_gra),
            fallback_lr=self._clamp_band(self._config.fallback_score_lr),
        )
        result.processing_time_ms = (time.time() - started_at) * 1000
        result.validate_scores()
        return result

    async def _download_audio(self, audio_url: str) -> Tuple[bytes, str]:
        """Return audio bytes and a usable filename from an HTTP URL or path."""
        parsed = urlparse(audio_url)
        if parsed.scheme.lower() in {"http", "https"}:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                response = await client.get(audio_url)
                response.raise_for_status()
            filename = Path(unquote(parsed.path)).name or "audio.mp3"
            return response.content, filename

        path = Path(audio_url)
        return path.read_bytes(), path.name

    async def _call_groq_whisper(self, audio_bytes: bytes, filename: str) -> dict:
        """Call Groq Whisper with verbose JSON and word/segment timestamps."""
        if not self._config.groq_api_key:
            raise ValueError("GROQ_API_KEY is not configured")
        if not audio_bytes:
            raise ValueError("Audio file is empty")

        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        data = {
            "model": self.WHISPER_MODEL,
            "response_format": "verbose_json",
            "timestamp_granularities[]": ["word", "segment"],
            "language": "en",
            "prompt": "IELTS Speaking Test. Examiner: Good morning. Student:",
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                self.GROQ_TRANSCRIBE_URL,
                headers={"Authorization": f"Bearer {self._config.groq_api_key}"},
                files={"file": (filename, audio_bytes, content_type)},
                data=data,
            )
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Groq returned a non-object transcription response")
        return payload

    def _build_annotated_transcript(
        self, whisper_response: dict
    ) -> Tuple[str, float]:
        """Annotate pauses, fillers, and low confidence; calculate genuine coverage."""
        words = whisper_response.get("words", [])
        if not isinstance(words, list) or not words:
            return "", 0.0

        threshold = self._config.word_confidence_threshold
        pause_min = self._config.pause_annotation_min_sec
        tokens = []
        high_confidence_count = 0
        previous_end = None

        for entry in words:
            if not isinstance(entry, dict):
                continue
            word = str(entry.get("word", "")).strip()
            start = float(entry.get("start", 0.0))
            end = float(entry.get("end", start))
            probability = float(entry.get("probability", 1.0))

            if previous_end is not None:
                gap = max(0.0, start - previous_end)
                if gap >= pause_min:
                    tokens.append(f"[PAUSE: {gap:.1f}s]")

            if is_nonlexical_filler(word):
                tokens.append(f"[FILLER: {word}]")
            elif probability < threshold:
                tokens.append(f"{word}[LOW_CONFIDENCE]")
            else:
                tokens.append(word)
                high_confidence_count += 1
            previous_end = max(start, end)

        valid_word_count = sum(isinstance(entry, dict) for entry in words)
        coverage = high_confidence_count / valid_word_count if valid_word_count else 0.0
        return " ".join(token for token in tokens if token), coverage

    async def _call_gemini(
        self,
        annotated_transcript: str,
        questions_metadata: str,
        gemini_api_key: str,
    ) -> Tuple[int, int, str, dict]:
        """Call the project's Gemini GRA/LR evaluator and validate its contract."""
        if not gemini_api_key:
            raise ValueError("Gemini API key is not configured")
        if not annotated_transcript.strip():
            raise ValueError("Annotated transcript is empty")

        from mock_ai_services import evaluate_speaking_gemini

        result = await evaluate_speaking_gemini(
            annotated_transcript=annotated_transcript,
            questions_metadata=questions_metadata,
            api_key=gemini_api_key,
        )
        if not isinstance(result, dict):
            raise ValueError("Gemini evaluator returned a non-object result")

        grammar_score = int(result.get("grammarScore", 0))
        lexical_score = int(result.get("lexicalScore", 0))
        if not 1 <= grammar_score <= 9 or not 1 <= lexical_score <= 9:
            detail = result.get("overallComment", "invalid or missing scores")
            raise ValueError(f"Gemini evaluator failed: {detail}")

        feedback_text = str(result.get("overallComment") or "No feedback generated.")
        metadata = {"evidences": result.get("evidences", [])}
        return grammar_score, lexical_score, feedback_text, metadata
