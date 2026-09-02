"""
providers/gemini_speaking_provider.py
======================================
Production-grade Gemini 2.5 Flash evaluation provider for IELTS Speaking Subsystem.
Integrates acoustic measurement grounding, underlength guardrail enforcement,
short-circuit evaluation on acoustic exclusions, and deterministic Cambridge Decimal rounding.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional, Union

from acoustic.phonetic_models import FullAcousticAnalysisResult
from providers.base import BaseLLMProvider, ProviderCallError
from providers.config import _load_prompt_sync, load_prompt_file
from providers.rounding import calculate_overall_band
from providers.schemas_speaking_additions import (
    SpeakingEvaluationResult,
    SpeakingFeedbackDetail,
    SpeakingCriterionFeedback,
    SpeakingMetrics,
    SpeakingCriterion,
)

logger = logging.getLogger(__name__)


def _serialize_acoustic_diagnostics(acoustic_result: Any) -> str:
    """Converts FullAcousticAnalysisResult or dictionary into formatted JSON string for user prompt."""
    if hasattr(acoustic_result, "__dict__"):
        import dataclasses
        if dataclasses.is_dataclass(acoustic_result):
            data = dataclasses.asdict(acoustic_result)
        else:
            data = dict(acoustic_result.__dict__)
    elif isinstance(acoustic_result, dict):
        data = acoustic_result
    else:
        data = {"word_count": len(str(acoustic_result).split())}

    return json.dumps(data, indent=2, default=str)


def _format_speaking_prompt(
    template: str,
    exam_part: str,
    question: str,
    transcript: str,
    acoustic_json: str,
) -> str:
    """Safely formats the speaking user prompt template with exact placeholders."""
    return (
        template.replace("{{exam_part}}", exam_part)
        .replace("{{question_title}}", question)
        .replace("{{candidate_transcript}}", transcript)
        .replace("{{acoustic_diagnostics_json}}", acoustic_json)
    )


class GeminiSpeakingProvider(BaseLLMProvider[SpeakingEvaluationResult]):
    """
    IELTS Speaking evaluation provider utilizing Google Gemini 2.5 Flash.
    Enforces short-circuit routing on acoustic exclusions and authoritative Cambridge rounding.
    """

    def __init__(
        self,
        gemini_client: Any = None,
        circuit_breaker: Any = None,
        metrics_client: Any = None,
        model_name: str = "gemini-2.5-flash",
        system_prompt_path: str = "providers/prompts/speaking_system.txt",
        user_prompt_path: str = "providers/prompts/speaking_user.txt",
    ):
        super().__init__(
            provider_id="GEMINI_2_5_FLASH_SPEAKING",
            circuit_breaker=circuit_breaker,
            metrics_client=metrics_client,
        )
        self.gemini_client = gemini_client
        self.model_name = model_name
        self.system_prompt_path = system_prompt_path
        self.user_prompt_path = user_prompt_path

    async def evaluate_speaking(
        self,
        question: str,
        transcript: str,
        acoustic_result: FullAcousticAnalysisResult,
        exam_part: str = "PART2",
    ) -> SpeakingEvaluationResult:
        """
        Evaluates an IELTS Speaking attempt using Gemini 2.5 Flash and acoustic DSP diagnostics.

        Short-circuit guard: If acoustic_result.excluded_from_automated_scoring is True,
        bypasses the LLM call completely, returning a structured review payload immediately.
        """
        # 1. Short-Circuit Routing on Acoustic Exclusion
        if getattr(acoustic_result, "excluded_from_automated_scoring", False):
            reason = getattr(acoustic_result, "exclusion_reason", "Technical acoustic anomaly") or "Technical acoustic anomaly"
            logger.warning(
                "[GEMINI_2_5_FLASH_SPEAKING] Short-circuiting evaluation due to acoustic exclusion: %s",
                reason,
            )
            return self._build_excluded_result(
                acoustic_result=acoustic_result,
                reason=reason,
                transcript=transcript,
            )

        # 2. Check Circuit Breaker Gate
        self.check_circuit_breaker()

        start_time = time.perf_counter()
        try:
            # 3. Load Prompt Templates (Non-blocking)
            system_prompt = await load_prompt_file(self.system_prompt_path)
            user_prompt_template = await load_prompt_file(self.user_prompt_path)

            # 4. Format Prompts
            acoustic_json = _serialize_acoustic_diagnostics(acoustic_result)
            user_prompt = _format_speaking_prompt(
                template=user_prompt_template,
                exam_part=exam_part,
                question=question,
                transcript=transcript,
                acoustic_json=acoustic_json,
            )

            # 5. Call Model
            raw_response = await self._call_model(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

            # 6. Parse and Validate Schema
            clean_json = raw_response.strip()
            if clean_json.startswith("```json"):
                clean_json = clean_json[7:]
            elif clean_json.startswith("```"):
                clean_json = clean_json[3:]
            if clean_json.endswith("```"):
                clean_json = clean_json[:-3]
            clean_json = clean_json.strip()

            result = SpeakingEvaluationResult.model_validate_json(clean_json)

            # 7. Authoritative Deterministic Overwrite of Overall Band
            calculated_overall = calculate_overall_band(
                fc=result.fluencyCoherenceScore,
                lr=result.lexicalResourceScore,
                gra=result.grammaticalRangeScore,
                pr=result.pronunciationScore,
            )

            if result.overallBand is not None and calculated_overall is not None:
                if abs(result.overallBand - calculated_overall) > 1e-4:
                    logger.warning(
                        "[GEMINI_2_5_FLASH_SPEAKING] LLM reported overall_band=%.1f differs from "
                        "authoritative Cambridge calculation=%.1f. Overwriting.",
                        result.overallBand,
                        calculated_overall,
                    )
            result.overallBand = calculated_overall

            # Record circuit breaker success if configured
            if self.circuit_breaker is not None and hasattr(self.circuit_breaker, "record_success"):
                self.circuit_breaker.record_success()

            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "[GEMINI_2_5_FLASH_SPEAKING] Successfully evaluated speaking attempt in %.1fms (Overall Band: %s)",
                duration_ms,
                result.overallBand,
            )
            return result

        except ProviderCallError:
            raise
        except Exception as ex:
            if self.circuit_breaker is not None and hasattr(self.circuit_breaker, "record_failure"):
                self.circuit_breaker.record_failure("SERVICE_UNAVAILABLE_503")
            logger.error("[GEMINI_2_5_FLASH_SPEAKING] Evaluation failed: %s", ex, exc_info=True)
            raise ProviderCallError(f"[GEMINI_2_5_FLASH_SPEAKING] Evaluation error: {ex}") from ex

    async def _call_model(self, system_prompt: str, user_prompt: str) -> str:
        """
        Executes Google Gemini model invocation with application/json response and low temperature.
        """
        if self.gemini_client is None:
            import os
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=api_key)
                    self.gemini_client = genai.GenerativeModel(
                        model_name=self.model_name,
                        system_instruction=system_prompt,
                    )
                except Exception as ex:
                    logger.warning("[GEMINI_2_5_FLASH_SPEAKING] Auto-initialization of gemini_client failed: %s", ex)

        if self.gemini_client is None:
            raise ProviderCallError("[GEMINI_2_5_FLASH_SPEAKING] gemini_client is not configured.")

        # If client has generate_content_async (google.generativeai GenerativeModel)
        if hasattr(self.gemini_client, "generate_content_async"):
            response = await self.gemini_client.generate_content_async(
                contents=user_prompt,
                generation_config={"response_mime_type": "application/json", "temperature": 0.2},
            )
            return response.text if hasattr(response, "text") else str(response)

        # If client has aio.models.generate_content (google.genai client)
        if hasattr(self.gemini_client, "aio") and hasattr(self.gemini_client.aio, "models"):
            response = await self.gemini_client.aio.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config={
                    "system_instruction": system_prompt,
                    "response_mime_type": "application/json",
                    "temperature": 0.2,
                },
            )
            return response.text if hasattr(response, "text") else str(response)

        # If client has generate_content (sync or async)
        if hasattr(self.gemini_client, "generate_content"):
            func = self.gemini_client.generate_content
            if asyncio.iscoroutinefunction(func):
                response = await func(user_prompt)
            else:
                response = await asyncio.to_thread(func, user_prompt)
            return response.text if hasattr(response, "text") else str(response)

        if callable(self.gemini_client):
            if asyncio.iscoroutinefunction(self.gemini_client):
                response = await self.gemini_client(system_prompt=system_prompt, user_prompt=user_prompt)
            else:
                response = await asyncio.to_thread(self.gemini_client, system_prompt=system_prompt, user_prompt=user_prompt)
            return response.text if hasattr(response, "text") else str(response)

        raise ProviderCallError(
            f"[GEMINI_2_5_FLASH_SPEAKING] Unsupported gemini_client type: {type(self.gemini_client)}"
        )

    def _build_excluded_result(
        self,
        acoustic_result: FullAcousticAnalysisResult,
        reason: str,
        transcript: str,
    ) -> SpeakingEvaluationResult:
        """
        Builds a fault-tolerant SpeakingEvaluationResult when acoustic processing fails
        or is excluded from automated scoring, flagging the attempt for human review.
        """
        word_count = getattr(acoustic_result, "word_count", None) or len(transcript.split())
        speaking_rate = getattr(acoustic_result, "speaking_rate_wpm", None)
        articulation_rate = getattr(acoustic_result, "articulation_rate_wpm", None)
        phonation_ratio = getattr(acoustic_result, "phonation_ratio", None)

        speaking_metrics = SpeakingMetrics(
            total_words=word_count,
            speaking_rate_wpm=speaking_rate,
            articulation_rate_wpm=articulation_rate,
            phonation_ratio=phonation_ratio,
        )

        criteria = [
            SpeakingCriterionFeedback(
                criterion=SpeakingCriterion.FLUENCY_COHERENCE,
                score=None,
                summary=f"Evaluation excluded from automated scoring due to technical acoustic anomaly: {reason}",
                strengths=[],
                weaknesses=[],
                acoustic_grounding_note=f"Excluded: {reason}",
            ),
            SpeakingCriterionFeedback(
                criterion=SpeakingCriterion.LEXICAL_RESOURCE,
                score=None,
                summary="Evaluation held for human examiner review following acoustic technical anomaly.",
                strengths=[],
                weaknesses=[],
            ),
            SpeakingCriterionFeedback(
                criterion=SpeakingCriterion.GRAMMATICAL_RANGE_ACCURACY,
                score=None,
                summary="Evaluation held for human examiner review following acoustic technical anomaly.",
                strengths=[],
                weaknesses=[],
            ),
            SpeakingCriterionFeedback(
                criterion=SpeakingCriterion.PRONUNCIATION,
                score=None,
                summary=f"Evaluation excluded from automated scoring due to technical acoustic anomaly: {reason}",
                strengths=[],
                weaknesses=[],
                acoustic_grounding_note=f"Excluded: {reason}",
            ),
        ]

        feedback_detail = SpeakingFeedbackDetail(
            examiner_summary=f"Automated scoring excluded due to technical acoustic anomaly: {reason}. Attempt flagged for human examiner review.",
            speaking_metrics=speaking_metrics,
            criteria=criteria,
        )

        return SpeakingEvaluationResult(
            overall_band=None,
            fluency_coherence_score=None,
            lexical_resource_score=None,
            grammatical_range_score=None,
            pronunciation_score=None,
            feedback_detail=feedback_detail,
            evaluated_by="AI_AUTO",
            requires_human_review=True,
        )
