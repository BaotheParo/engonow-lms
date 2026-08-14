"""
test_gemini_writing_provider.py
===============================
Unit tests for GeminiWritingProvider, prompt loading, caching, and resilient error handling.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from providers.base import (
    AbstractWritingProvider,
    MalformedAIResponseError,
    WritingEvaluationError,
)
from providers.config import (
    WritingProviderConfig,
    _load_prompt_sync,
    clear_prompt_cache,
    load_prompt_file,
)
from providers.gemini_writing_provider import GeminiWritingProvider, _secure_format_prompt
from providers.schemas import (
    CorrectionErrorType,
    ErrorSeverity,
    TaskType,
    WritingCriterion,
)
from telemetry.metrics import (
    WRITING_EVALUATION_ERRORS_TOTAL,
    WRITING_EVALUATION_REQUESTS_TOTAL,
)


class TestPromptLoader(unittest.IsolatedAsyncioTestCase):
    """Tests for cached, thread-safe external prompt file loading."""

    def setUp(self):
        clear_prompt_cache()

    def tearDown(self):
        clear_prompt_cache()

    async def test_loads_existing_prompt_file(self):
        system_prompt = await load_prompt_file("providers/prompts/writing_system.txt")
        self.assertIn("You are an IELTS Writing Task 2 examiner AI", system_prompt)

        user_prompt = await load_prompt_file("providers/prompts/writing_user.txt")
        self.assertIn("{task_type}", user_prompt)
        self.assertIn("{essay_text}", user_prompt)

    async def test_raises_file_not_found_for_missing_prompt(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            await load_prompt_file("providers/prompts/non_existent_prompt.txt")
        self.assertIn("non_existent_prompt.txt", str(ctx.exception))

    async def test_cache_hits_without_re_reading_file(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as tf:
            tf.write("Initial prompt content")
            temp_path = tf.name

        try:
            content1 = await load_prompt_file(temp_path)
            self.assertEqual(content1, "Initial prompt content")

            # Modify file on disk
            Path(temp_path).write_text("Modified prompt content", encoding="utf-8")

            # Should return cached content
            content2 = await load_prompt_file(temp_path)
            self.assertEqual(content2, "Initial prompt content")

            # Clear cache and reload
            clear_prompt_cache()
            content3 = await load_prompt_file(temp_path)
            self.assertEqual(content3, "Modified prompt content")
        finally:
            os.remove(temp_path)


class TestPromptFormatting(unittest.TestCase):
    """Tests for secure template variable substitution and brace escaping."""

    def test_handles_unescaped_braces_in_student_essay(self):
        template = "Prompt: {task_prompt}\nEssay: {essay_text}\nType: {task_type}"
        dangerous_essay = "This essay contains {curly_braces} and {unexpected_keys: 123}."
        formatted = _secure_format_prompt(
            template=template,
            task_type="TASK2",
            task_prompt="Discuss advantages and {disadvantages}.",
            essay_text=dangerous_essay,
        )
        self.assertIn("This essay contains {curly_braces}", formatted)
        self.assertIn("Discuss advantages and {disadvantages}.", formatted)


class TestGeminiWritingProvider(unittest.IsolatedAsyncioTestCase):
    """Unit tests for GeminiWritingProvider evaluation flow."""

    def setUp(self):
        clear_prompt_cache()
        self.config = WritingProviderConfig(
            gemini_api_key="test-api-key",
            ai_model_name="gemini-2.5-flash",
            system_prompt_path="providers/prompts/writing_system.txt",
            user_prompt_path="providers/prompts/writing_user.txt",
        )

    def _sample_valid_pydantic_payload(self) -> dict:
        return {
            "examinerSummary": "A well-developed essay reaching Band 7.0 with clear argumentation.",
            "essayMetrics": {
                "totalWords": 285,
                "uniqueWords": 142,
                "lexicalDiversityRatio": 0.498,
                "averageSentenceLength": 19.0,
                "complexSentencesRatio": 0.65,
            },
            "criteria": [
                {
                    "criterion": "TASK_RESPONSE",
                    "score": 7.0,
                    "summary": "All prompt components addressed with clear stance.",
                    "strengths": ["Clear position"],
                    "weaknesses": ["Slightly repetitive in paragraph 3"],
                    "bandGapAnalysis": "Extend supporting examples for Band 8.0.",
                },
                {
                    "criterion": "COHERENCE_COHESION",
                    "score": 7.0,
                    "summary": "Logical progression across paragraphs.",
                    "strengths": ["Good discourse markers"],
                    "weaknesses": ["Minor overuse of 'Furthermore'"],
                },
                {
                    "criterion": "LEXICAL_RESOURCE",
                    "score": 7.0,
                    "summary": "Precise vocabulary with minor collocation slips.",
                    "strengths": ["Academic lexicon"],
                    "weaknesses": ["Occasional unnatural pairing"],
                },
                {
                    "criterion": "GRAMMATICAL_RANGE_ACCURACY",
                    "score": 7.0,
                    "summary": "Good mix of complex clauses with high accuracy.",
                    "strengths": ["Compound and complex structures"],
                    "weaknesses": ["One punctuation slip"],
                },
            ],
            "corrections": [
                {
                    "startIndex": 45,
                    "endIndex": 85,
                    "originalSentence": "working from home bring more benefits",
                    "correctedSentence": "working from home brings more benefits",
                    "errorType": "GRAMMAR",
                    "severity": "MAJOR",
                    "explanation": "Gerund subject requires singular verb 'brings'.",
                    "enhancedOptions": {
                        "band7Option": "telecommuting yields considerable advantages",
                        "band8Option": "remote working models offer distinct operational and personal benefits",
                    },
                }
            ],
            "cohesiveDeviceAnalysis": {
                "usedDevices": ["In conclusion", "On the other hand", "Furthermore"],
                "overusedOrRepetitive": ["Furthermore"],
                "suggestedTransitions": ["Additionally", "Moreover"],
            },
            "vocabularyUpgrades": [
                {
                    "originalWord": "good",
                    "contextInEssay": "a good idea for workers",
                    "academicAlternatives": ["advantageous", "beneficial", "viable"],
                    "recommendedCollocations": ["prove advantageous", "highly beneficial"],
                }
            ],
            "improvementTips": [
                {
                    "category": "CC",
                    "tipText": "Vary transitional phrases to avoid mechanical cohesion.",
                    "targetBand": 8.0,
                }
            ],
        }

    @patch("google.generativeai.GenerativeModel")
    @patch("google.generativeai.configure")
    def test_initialization(self, mock_configure, mock_model_class):
        provider = GeminiWritingProvider(config=self.config)
        self.assertEqual(provider.provider_name, "GEMINI_WRITING")
        mock_configure.assert_called_once_with(api_key="test-api-key")
        mock_model_class.assert_called_once()

    @patch("google.generativeai.GenerativeModel")
    @patch("google.generativeai.configure")
    async def test_successful_evaluation(self, mock_configure, mock_model_class):
        mock_model_instance = MagicMock()
        mock_model_class.return_value = mock_model_instance

        sample_response_data = self._sample_valid_pydantic_payload()
        mock_response = MagicMock()
        mock_response.text = json.dumps(sample_response_data)
        mock_model_instance.generate_content_async = AsyncMock(return_value=mock_response)

        provider = GeminiWritingProvider(config=self.config)
        result = await provider.evaluate_essay(
            task_type="TASK2",
            task_prompt="Discuss the advantages and disadvantages of remote work {in detail}.",
            essay_text="In recent years, remote work {has} gained substantial popularity across the globe...",
        )

        self.assertIsInstance(result, dict)
        self.assertEqual(result["essayMetrics"]["totalWords"], 285)
        self.assertEqual(len(result["criteria"]), 4)
        self.assertEqual(result["criteria"][0]["score"], 7.0)
        self.assertEqual(result["criteria"][0]["criterion"], "TASK_RESPONSE")
        self.assertEqual(len(result["corrections"]), 1)
        self.assertEqual(result["corrections"][0]["errorType"], "GRAMMAR")
        self.assertEqual(result["corrections"][0]["severity"], "MAJOR")

    @patch("google.generativeai.GenerativeModel")
    @patch("google.generativeai.configure")
    async def test_input_validation_errors(self, mock_configure, mock_model_class):
        provider = GeminiWritingProvider(config=self.config)

        with self.assertRaises(WritingEvaluationError):
            await provider.evaluate_essay(task_type="TASK2", task_prompt="", essay_text="Valid essay")

        with self.assertRaises(WritingEvaluationError):
            await provider.evaluate_essay(task_type="TASK2", task_prompt="Valid prompt", essay_text="   ")

    @patch("google.generativeai.GenerativeModel")
    @patch("google.generativeai.configure")
    async def test_malformed_json_handling(self, mock_configure, mock_model_class):
        mock_model_instance = MagicMock()
        mock_model_class.return_value = mock_model_instance

        mock_response = MagicMock()
        mock_response.text = "This is not valid JSON output {invalid: 123"
        mock_model_instance.generate_content_async = AsyncMock(return_value=mock_response)

        provider = GeminiWritingProvider(config=self.config)

        with self.assertRaises(MalformedAIResponseError) as ctx:
            await provider.evaluate_essay(
                task_type="TASK2",
                task_prompt="Sample prompt",
                essay_text="Sample essay content...",
            )

        self.assertIn("Failed to parse structured JSON", str(ctx.exception))

    @patch("google.generativeai.GenerativeModel")
    @patch("google.generativeai.configure")
    async def test_schema_validation_failure_handling(self, mock_configure, mock_model_class):
        mock_model_instance = MagicMock()
        mock_model_class.return_value = mock_model_instance

        # Missing required fields like essayMetrics and criteria
        invalid_schema_json = {"examinerSummary": "Incomplete payload"}
        mock_response = MagicMock()
        mock_response.text = json.dumps(invalid_schema_json)
        mock_model_instance.generate_content_async = AsyncMock(return_value=mock_response)

        provider = GeminiWritingProvider(config=self.config)

        with self.assertRaises(MalformedAIResponseError) as ctx:
            await provider.evaluate_essay(
                task_type="TASK2",
                task_prompt="Sample prompt",
                essay_text="Sample essay content...",
            )

        self.assertIn("does not conform to WritingFeedbackDetail schema", str(ctx.exception))

    @patch("google.generativeai.GenerativeModel")
    @patch("google.generativeai.configure")
    async def test_empty_response_handling(self, mock_configure, mock_model_class):
        mock_model_instance = MagicMock()
        mock_model_class.return_value = mock_model_instance

        mock_response = MagicMock()
        mock_response.text = ""
        mock_model_instance.generate_content_async = AsyncMock(return_value=mock_response)

        provider = GeminiWritingProvider(config=self.config)

        with self.assertRaises(MalformedAIResponseError):
            await provider.evaluate_essay(
                task_type="TASK2",
                task_prompt="Sample prompt",
                essay_text="Sample essay content...",
            )

    @patch("google.generativeai.GenerativeModel")
    @patch("google.generativeai.configure")
    async def test_api_network_failure_handling(self, mock_configure, mock_model_class):
        mock_model_instance = MagicMock()
        mock_model_class.return_value = mock_model_instance
        mock_model_instance.generate_content_async = AsyncMock(side_effect=RuntimeError("Connection timeout to Gemini"))

        provider = GeminiWritingProvider(config=self.config)

        with self.assertRaises(WritingEvaluationError) as ctx:
            await provider.evaluate_essay(
                task_type="TASK2",
                task_prompt="Sample prompt",
                essay_text="Sample essay content...",
            )

        self.assertIn("Gemini evaluation failed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
