"""
providers/gemini_writing_provider.py
====================================
Production-grade Gemini 2.5 Flash evaluation provider for IELTS Writing Subsystem.
Decouples prompt engineering from application code by dynamically loading,
caching, and executing external system/user prompt templates with strict
Pydantic v2 schema validation, exponential retry resiliency, and deterministic substitution.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional

import backoff
import google.generativeai as genai
from google.api_core.exceptions import (
    DeadlineExceeded,
    GoogleAPICallError,
    InternalServerError,
    ResourceExhausted,
    ServiceUnavailable,
)
from pydantic import ValidationError

from providers.base import (
    AbstractWritingProvider,
    MalformedAIResponseError,
    WritingEvaluationError,
)
from providers.config import (
    WRITING_CONFIG,
    WritingProviderConfig,
    _load_prompt_sync,
    load_prompt_file,
)
from providers.schemas import WritingFeedbackDetail
from telemetry.metrics import (
    WRITING_EVALUATION_ERRORS_TOTAL,
    WRITING_EVALUATION_LATENCY_SECONDS,
    WRITING_EVALUATION_REQUESTS_TOTAL,
)

logger = logging.getLogger(__name__)


def _secure_format_prompt(
    template: str, task_type: str, task_prompt: str, essay_text: str
) -> str:
    """
    Direct, deterministic parameter substitution engine that replaces known placeholders
    reliably without triggering KeyError or brace-injection attacks from stray curly braces
    in template files or student essay texts.
    """
    safe_type = task_type or "TASK_2"
    safe_prompt = task_prompt.strip()
    safe_essay = essay_text.strip()
    return (
        template.replace("{task_type}", safe_type)
        .replace("{task_prompt}", safe_prompt)
        .replace("{essay_text}", safe_essay)
    )


class GeminiWritingProvider(AbstractWritingProvider):
    """
    Evaluates IELTS Writing submissions (Task 1 & Task 2) using Google Gemini
    models with strict JSON structured outputs, Pydantic validation, and external prompt caching.
    """

    def __init__(self, config: Optional[Any] = None) -> None:
        if config is not None:
            if isinstance(config, WritingProviderConfig):
                self.config = config
            else:
                key = getattr(config, "api_key", None) or getattr(config, "gemini_api_key", "")
                model = getattr(config, "model_name", None) or getattr(config, "ai_model_name", None) or getattr(config, "gemini_model", "gemini-2.5-flash")
                self.config = WritingProviderConfig(
                    gemini_api_key=key,
                    ai_model_name=model,
                    system_prompt_path=getattr(config, "system_prompt_path", "providers/prompts/writing_system.txt"),
                    user_prompt_path=getattr(config, "user_prompt_path", "providers/prompts/writing_user.txt"),
                )
        else:
            self.config = WRITING_CONFIG

        self._provider_name = "GEMINI_WRITING"

        if not self.config.gemini_api_key:
            logger.warning(
                "[GEMINI WRITING PROVIDER] GEMINI_API_KEY is not set or empty in environment."
            )

        genai.configure(api_key=self.config.gemini_api_key)

        # Load system prompt template at initialization
        logger.info(
            "[GEMINI WRITING PROVIDER] Loading system prompt template from: %s",
            self.config.system_prompt_path,
        )
        self.system_prompt = _load_prompt_sync(self.config.system_prompt_path)

        model_name = self.config.ai_model_name
        if not model_name.startswith("models/") and not model_name.startswith("gemini-"):
            model_name = f"models/{model_name}"

        self.model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.0,
            },
            system_instruction=self.system_prompt,
        )
        logger.info(
            "[GEMINI WRITING PROVIDER] Initialized with model=%s",
            model_name,
        )

    @property
    def provider_name(self) -> str:
        """Identifier for telemetry and logging."""
        return self._provider_name

    @backoff.on_exception(
        backoff.expo,
        (
            ResourceExhausted,
            DeadlineExceeded,
            InternalServerError,
            ServiceUnavailable,
        ),
        max_tries=3,
        jitter=backoff.full_jitter,
        logger=logger,
    )
    async def _invoke_gemini_async(self, prompt: str) -> Any:
        """
        Executes asynchronous call to Gemini with exponential backoff and jitter for transient errors.
        """
        return await self.model.generate_content_async(prompt)

    async def evaluate_essay(
        self,
        task_type: str,
        task_prompt: str,
        essay_text: str,
    ) -> Dict[str, Any]:
        """
        Evaluates an IELTS Writing essay asynchronously using Gemini 2.5 Flash.

        Args:
            task_type: 'TASK_1' or 'TASK_2'.
            task_prompt: Original IELTS prompt / topic text.
            essay_text: Student's submitted essay text.

        Returns:
            Dictionary validated against WritingFeedbackDetail schema.

        Raises:
            WritingEvaluationError: On input validation, API execution, or network failures.
            MalformedAIResponseError: When model response is invalid JSON or fails Pydantic schema validation.
        """
        if not task_prompt or not task_prompt.strip():
            raise WritingEvaluationError("task_prompt must not be empty.")
        if not essay_text or not essay_text.strip():
            raise WritingEvaluationError("essay_text must not be empty.")

        # 1. Non-blocking User Prompt Template Loading
        try:
            user_prompt_template = await load_prompt_file(self.config.user_prompt_path)
        except Exception as e:
            logger.critical(
                "[GEMINI WRITING PROVIDER] Failed to load user prompt template from '%s': %s",
                self.config.user_prompt_path,
                e,
            )
            WRITING_EVALUATION_ERRORS_TOTAL.labels(
                provider=self.provider_name, error_type="PROMPT_LOAD_ERROR"
            ).inc()
            raise WritingEvaluationError(
                f"Failed to load user prompt template: {e}"
            ) from e

        # 2. Deterministic Parameter Substitution
        user_prompt = _secure_format_prompt(
            template=user_prompt_template,
            task_type=task_type,
            task_prompt=task_prompt,
            essay_text=essay_text,
        )

        # 3. Asynchronous Model Invocation with Backoff Retries
        start_time = time.perf_counter()
        logger.info(
            "[GEMINI WRITING PROVIDER] Sending evaluation request for task_type=%s, words=%d",
            task_type,
            len(essay_text.split()),
        )

        try:
            response = await self._invoke_gemini_async(user_prompt)
            duration = time.perf_counter() - start_time
            WRITING_EVALUATION_LATENCY_SECONDS.labels(
                provider=self.provider_name
            ).observe(duration)
            logger.info(
                "[GEMINI WRITING PROVIDER] Received response in %.2fs", duration
            )
        except GoogleAPICallError as api_err:
            duration = time.perf_counter() - start_time
            logger.error(
                "[GEMINI WRITING PROVIDER] Google API Call error after %.2fs: %s",
                duration,
                api_err,
                exc_info=True,
            )
            WRITING_EVALUATION_ERRORS_TOTAL.labels(
                provider=self.provider_name, error_type=type(api_err).__name__
            ).inc()
            WRITING_EVALUATION_REQUESTS_TOTAL.labels(
                provider=self.provider_name, status="API_ERROR"
            ).inc()
            raise WritingEvaluationError(
                f"Gemini API call failed: {api_err}"
            ) from api_err
        except Exception as gen_err:
            duration = time.perf_counter() - start_time
            logger.error(
                "[GEMINI WRITING PROVIDER] Unexpected invocation error after %.2fs: %s",
                duration,
                gen_err,
                exc_info=True,
            )
            WRITING_EVALUATION_ERRORS_TOTAL.labels(
                provider=self.provider_name, error_type="UNEXPECTED_ERROR"
            ).inc()
            WRITING_EVALUATION_REQUESTS_TOTAL.labels(
                provider=self.provider_name, status="ERROR"
            ).inc()
            raise WritingEvaluationError(
                f"Gemini evaluation failed: {gen_err}"
            ) from gen_err

        # 4. Parse JSON & Validate against Pydantic Schema
        raw_text = getattr(response, "text", "") or ""
        if not raw_text.strip():
            logger.warning(
                "[GEMINI WRITING PROVIDER] Empty response returned by model."
            )
            WRITING_EVALUATION_ERRORS_TOTAL.labels(
                provider=self.provider_name, error_type="EMPTY_RESPONSE"
            ).inc()
            WRITING_EVALUATION_REQUESTS_TOTAL.labels(
                provider=self.provider_name, status="EMPTY_RESPONSE"
            ).inc()
            raise MalformedAIResponseError("Gemini model returned an empty response.")

        try:
            parsed_json = json.loads(raw_text)
        except json.JSONDecodeError as decode_err:
            logger.critical(
                "[GEMINI WRITING PROVIDER] Malformed JSON response: %s | Raw snippet: %s",
                decode_err,
                raw_text[:300],
            )
            WRITING_EVALUATION_ERRORS_TOTAL.labels(
                provider=self.provider_name, error_type="MALFORMED_JSON"
            ).inc()
            WRITING_EVALUATION_REQUESTS_TOTAL.labels(
                provider=self.provider_name, status="MALFORMED_JSON"
            ).inc()
            raise MalformedAIResponseError(
                f"Failed to parse structured JSON from Gemini response: {decode_err}"
            ) from decode_err

        try:
            validated_result = WritingFeedbackDetail.model_validate(parsed_json)
            WRITING_EVALUATION_REQUESTS_TOTAL.labels(
                provider=self.provider_name, status="SUCCESS"
            ).inc()
            return validated_result.model_dump()
        except ValidationError as val_err:
            logger.critical(
                "[GEMINI WRITING PROVIDER] Pydantic validation failure: %s | Raw snippet: %s",
                val_err,
                raw_text[:300],
            )
            WRITING_EVALUATION_ERRORS_TOTAL.labels(
                provider=self.provider_name, error_type="SCHEMA_VALIDATION_ERROR"
            ).inc()
            WRITING_EVALUATION_REQUESTS_TOTAL.labels(
                provider=self.provider_name, status="MALFORMED_JSON"
            ).inc()
            raise MalformedAIResponseError(
                f"Gemini response does not conform to WritingFeedbackDetail schema: {val_err}"
            ) from val_err

    async def evaluate(
        self,
        prompt: Optional[str] = None,
        essay: Optional[str] = None,
        task_type: str = "TASK2",
        task_prompt: Optional[str] = None,
        essay_text: Optional[str] = None,
    ) -> Any:
        """
        Unified, high-level evaluation interface returning aggregated criterion scores
        and structured feedback details.
        """
        final_prompt = prompt or task_prompt or ""
        final_essay = essay or essay_text or ""
        norm_task_type = "TASK2" if "2" in str(task_type).upper() else "TASK1"

        feedback_dict = await self.evaluate_essay(
            task_type=norm_task_type,
            task_prompt=final_prompt,
            essay_text=final_essay,
        )

        # Extract criteria scores
        scores = {}
        criteria_list = feedback_dict.get("criteria", [])
        for crit in criteria_list:
            c_name = str(crit.get("criterion", "")).upper()
            c_score = float(crit.get("score", 0.0))
            if "RESPONSE" in c_name or "ACHIEVEMENT" in c_name or c_name in ("TR", "TA"):
                scores["TR"] = c_score
            elif "COHERENCE" in c_name or c_name == "CC":
                scores["CC"] = c_score
            elif "LEXICAL" in c_name or c_name == "LR":
                scores["LR"] = c_score
            elif "GRAMMATICAL" in c_name or c_name == "GRA":
                scores["GRA"] = c_score

        tr = scores.get("TR", 0.0)
        cc = scores.get("CC", 0.0)
        lr = scores.get("LR", 0.0)
        gra = scores.get("GRA", 0.0)

        # Cambridge IELTS Rounding
        raw_avg = (tr + cc + lr + gra) / 4.0 if (tr + cc + lr + gra) > 0 else 0.0
        floor_val = int(raw_avg)
        rem = raw_avg - floor_val
        if rem < 0.25:
            overall = float(floor_val)
        elif rem < 0.75:
            overall = float(floor_val) + 0.5
        else:
            overall = float(floor_val) + 1.0

        class WritingEvaluationResponse:
            def __init__(self, overall_band: float, tr: float, cc: float, lr: float, gra: float, feedback: Dict[str, Any]):
                self.overall_band = overall_band
                self.task_achievement_score = tr
                self.coherence_cohesion_score = cc
                self.lexical_resource_score = lr
                self.grammatical_range_score = gra
                self.feedback_detail = feedback

            def __repr__(self) -> str:
                return (
                    f"<WritingEvaluationResponse overall={self.overall_band} "
                    f"TR={self.task_achievement_score} CC={self.coherence_cohesion_score} "
                    f"LR={self.lexical_resource_score} GRA={self.grammatical_range_score}>"
                )

        return WritingEvaluationResponse(
            overall_band=overall,
            tr=tr,
            cc=cc,
            lr=lr,
            gra=gra,
            feedback=feedback_dict,
        )
