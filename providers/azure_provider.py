"""Azure Speech speaking evaluation provider.

The provider has a dependency-free mock mode for development and a live mode
using Azure Pronunciation Assessment for PR/FC plus Gemini for GRA/LR.
"""

import json
import asyncio
import logging
import os
import random
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import unquote, urlparse

import httpx

from providers.base import (
    AbstractSpeakingProvider,
    EvaluationStatus,
    UnifiedSpeakingResult,
)
from providers.config import ProviderConfig


logger = logging.getLogger("engonow.provider.azure")

try:
    import azure.cognitiveservices.speech as speechsdk

    _AZURE_SDK_AVAILABLE = True
except ImportError:
    speechsdk = None
    _AZURE_SDK_AVAILABLE = False


class AzureProvider(AbstractSpeakingProvider):
    """Paid track: Azure PR/FC and Gemini GRA/LR evaluation."""

    _MOCK_MODE_KEY = "NOT_CONFIGURED"

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self._is_mock = config.azure_speech_key.strip() == self._MOCK_MODE_KEY

        if self._is_mock:
            logger.warning(
                "[AZURE PROVIDER] MOCK MODE ACTIVE - AZURE_SPEECH_KEY is '%s'. "
                "Scores are synthetic placeholders. Set a real key to enable live evaluation.",
                self._MOCK_MODE_KEY,
            )
        elif not _AZURE_SDK_AVAILABLE:
            raise RuntimeError(
                "AZURE provider selected but azure-cognitiveservices-speech is not "
                "installed. Run: pip install azure-cognitiveservices-speech"
            )

    @property
    def provider_name(self) -> str:
        return "AZURE"

    async def evaluate(
        self,
        session_id: str,
        audio_url: Optional[str],
        gemini_api_key: str,
        questions_metadata: str = "",
        audio_bytes: Optional[bytes] = None,
        audio_filename: str = "audio.wav",
    ) -> UnifiedSpeakingResult:
        started_at = time.time()
        if self._is_mock:
            # Preserve realistic paid-service timing in integration and latency tests.
            await asyncio.sleep(random.uniform(2.0, 5.0))
            return self._build_mock_result(session_id, started_at)

        warnings = []
        try:
            if audio_bytes is None:
                if not audio_url:
                    raise ValueError("Either audio_url or audio_bytes must be provided")
                audio_bytes, audio_filename = await self._download_audio(audio_url)
            elif not audio_bytes:
                raise ValueError("Uploaded audio file is empty")
        except Exception as exc:
            logger.error("[AZURE] Audio download failed: %s", exc)
            return self._failed_result(session_id, f"Audio download failed: {exc}", started_at)

        pr_score = self._config.fallback_score_pr
        fc_score = self._config.fallback_score_fc
        transcript = ""
        genuine_word_coverage = 0.0
        azure_metadata = {}
        azure_failed = False
        try:
            (
                pr_score,
                fc_score,
                transcript,
                genuine_word_coverage,
                azure_metadata,
            ) = self._run_azure_pronunciation_assessment(audio_bytes, audio_filename)
        except Exception as exc:
            azure_failed = True
            logger.warning("[AZURE] Pronunciation assessment failed: %s", exc)
            warnings.append(f"AZURE_PR_FC_FAILED: {exc}")

        annotated_transcript = self._annotate_azure_transcript(
            transcript, azure_metadata.get("word_results", [])
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
                annotated_transcript, questions_metadata, gemini_api_key
            )
        except Exception as exc:
            gemini_failed = True
            logger.warning("[AZURE] Gemini GRA/LR failed: %s", exc)
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
                if azure_failed or gemini_failed
                else EvaluationStatus.SUCCESS
            ),
            genuine_word_coverage=max(0.0, min(1.0, genuine_word_coverage)),
            feedback_text=feedback_text,
            processing_time_ms=(time.time() - started_at) * 1000,
            provider_metadata={
                "azure": azure_metadata,
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

    def _run_azure_pronunciation_assessment(
        self, audio_bytes: bytes, filename: str
    ) -> Tuple[int, int, str, float, dict]:
        """Run a live Azure word-granularity pronunciation assessment."""
        if not _AZURE_SDK_AVAILABLE or speechsdk is None:
            raise RuntimeError("Azure Speech SDK is unavailable")
        if not audio_bytes:
            raise ValueError("Audio file is empty")

        suffix = Path(filename).suffix or ".wav"
        temporary_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
                temporary.write(audio_bytes)
                temporary_path = temporary.name

            speech_config = speechsdk.SpeechConfig(
                subscription=self._config.azure_speech_key,
                region=self._config.azure_speech_region,
            )
            speech_config.speech_recognition_language = (
                self._config.azure_speech_language
            )
            speech_config.output_format = speechsdk.OutputFormat.Detailed
            audio_config = speechsdk.audio.AudioConfig(filename=temporary_path)
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
                cancellation = ""
                if result.reason == speechsdk.ResultReason.Canceled:
                    details = speechsdk.CancellationDetails(result)
                    cancellation = f"; cancellation={details.reason}: {details.error_details}"
                raise RuntimeError(
                    f"Azure did not recognize speech (reason={result.reason}{cancellation})"
                )

            assessment = speechsdk.PronunciationAssessmentResult(result)
            accuracy = float(assessment.accuracy_score)
            fluency = float(assessment.fluency_score)
            pr_band = self._azure_accuracy_to_ielts_pr_band(accuracy)
            fc_band = self._azure_fluency_to_ielts_fc_band(fluency)

            detailed_json = result.properties.get(
                speechsdk.PropertyId.SpeechServiceResponse_JsonResult
            )
            word_results = self._extract_word_results(detailed_json)
            high_accuracy_count = sum(
                word["accuracy_score"] >= 70.0 for word in word_results
            )
            coverage = (
                high_accuracy_count / len(word_results) if word_results else 0.0
            )
            metadata = {
                "azure_accuracy_score": round(accuracy, 2),
                "azure_fluency_score": round(fluency, 2),
                "pr_band_before_gemini_check": pr_band,
                "fc_band_before_gemini_check": fc_band,
                "word_results": word_results,
            }
            return pr_band, fc_band, result.text, coverage, metadata
        finally:
            if temporary_path:
                try:
                    os.unlink(temporary_path)
                except OSError as exc:
                    logger.warning("[AZURE] Could not remove temporary audio file: %s", exc)

    @staticmethod
    def _extract_word_results(detailed_json: str) -> list:
        """Extract word assessment data from Azure's detailed JSON response."""
        if not detailed_json:
            return []
        try:
            payload = json.loads(detailed_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid Azure detailed result JSON: {exc}") from exc

        nbest = payload.get("NBest") or []
        words = nbest[0].get("Words", []) if nbest else []
        extracted = []
        for item in words:
            assessment = item.get("PronunciationAssessment") or {}
            extracted.append(
                {
                    "word": str(item.get("Word", "")),
                    "accuracy_score": round(float(assessment.get("AccuracyScore", 0.0)), 1),
                    "error_type": str(assessment.get("ErrorType", "None")),
                }
            )
        return extracted

    def _azure_accuracy_to_ielts_pr_band(self, azure_score: float) -> int:
        """Map Azure AccuracyScore to an initial, uncalibrated IELTS PR band."""
        thresholds = [
            (10.0, 1),
            (20.0, 2),
            (32.0, 3),
            (44.0, 4),
            (56.0, 5),
            (68.0, 6),
            (79.0, 7),
            (89.0, 8),
        ]
        for threshold, band in thresholds:
            if azure_score < threshold:
                return band
        return 9

    def _azure_fluency_to_ielts_fc_band(self, azure_score: float) -> int:
        """Map Azure FluencyScore to an initial, uncalibrated IELTS FC band."""
        thresholds = [
            (8.0, 1),
            (18.0, 2),
            (30.0, 3),
            (43.0, 4),
            (55.0, 5),
            (67.0, 6),
            (78.0, 7),
            (88.0, 8),
        ]
        for threshold, band in thresholds:
            if azure_score < threshold:
                return band
        return 9

    def _annotate_azure_transcript(self, transcript: str, word_results: list) -> str:
        """Add Azure error-type markers to the recognized word sequence."""
        if not word_results:
            return transcript
        tokens = []
        for item in word_results:
            word = str(item.get("word", "")).strip()
            error_type = str(item.get("error_type", "None"))
            if error_type.lower() not in {"none", "0", ""}:
                tokens.append(f"{word}[{error_type.upper()}]")
            else:
                tokens.append(word)
        return " ".join(token for token in tokens if token)

    async def _call_gemini(
        self,
        annotated_transcript: str,
        questions_metadata: str,
        gemini_api_key: str,
    ) -> Tuple[int, int, str, dict]:
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
        return (
            grammar_score,
            lexical_score,
            str(result.get("overallComment") or "No feedback generated."),
            {"evidences": result.get("evidences", [])},
        )

    def _build_mock_result(
        self, session_id: str, started_at: float
    ) -> UnifiedSpeakingResult:
        logger.warning(
            "[AZURE MOCK] Returning synthetic Band 6 scores for session '%s'. "
            "Set AZURE_SPEECH_KEY to activate live evaluation.",
            session_id,
        )
        result = UnifiedSpeakingResult(
            session_id=session_id,
            provider_used=f"{self.provider_name}_MOCK",
            pronunciation_score=6,
            fluency_score=6,
            grammar_score=6,
            lexical_score=6,
            status=EvaluationStatus.PARTIAL,
            genuine_word_coverage=0.75,
            feedback_text=(
                "[AZURE MOCK MODE] Real Azure Speech evaluation inactive. "
                "Configure AZURE_SPEECH_KEY to activate paid-tier scoring."
            ),
            processing_time_ms=(time.time() - started_at) * 1000,
            provider_metadata={
                "warnings": [
                    "AZURE_MOCK_MODE: AZURE_SPEECH_KEY=NOT_CONFIGURED. "
                    "All scores are synthetic placeholders."
                ]
            },
        )
        result.validate_scores()
        return result

    async def _download_audio(self, audio_url: str) -> Tuple[bytes, str]:
        parsed = urlparse(audio_url)
        if parsed.scheme.lower() in {"http", "https"}:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                response = await client.get(audio_url)
                response.raise_for_status()
            filename = Path(unquote(parsed.path)).name or "audio.wav"
            return response.content, filename

        path = Path(audio_url)
        return path.read_bytes(), path.name
