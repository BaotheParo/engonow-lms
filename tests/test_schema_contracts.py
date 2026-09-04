"""
test_schema_contracts.py
========================
Automated validation test suite for canonical Kafka event schemas (Draft 2020-12).
Verifies that all domain payloads (Writing, Speaking, Envelopes) conform strictly
to contract specifications and reject malformed, out-of-bounds, or unauthorized payload drift.
"""

import json
import unittest
from pathlib import Path
from typing import Any, Dict

import jsonschema
from jsonschema.exceptions import ValidationError
from jsonschema.validators import Draft202012Validator


def load_schema(schema_filename: str) -> Dict[str, Any]:
    """Loads and returns a JSON schema from the schemas/ directory."""
    repo_root = Path(__file__).resolve().parent.parent if Path(__file__).resolve().parent.name == "tests" else Path(__file__).resolve().parent
    schema_path = repo_root / "schemas" / schema_filename
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    return json.loads(schema_path.read_text(encoding="utf-8"))


class TestEnvelopeSchema(unittest.TestCase):
    """Validation test suite for schemas/envelope.json."""

    @classmethod
    def setUpClass(cls):
        cls.schema = load_schema("envelope.json")
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema)

    def _sample_valid_envelope(self) -> Dict[str, Any]:
        return {
            "eventId": "a2effcb1-77d8-41a3-b6e1-73c4f60219c5",
            "idempotencyKey": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
            "eventType": "WRITING_EVALUATION_REQUESTED",
            "schemaVersion": "1.0",
            "occurredAt": "2026-08-19T07:30:00Z",
            "producedAt": "2026-08-19T07:30:01Z",
            "traceId": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            "correlationId": "corr-writ-9b1deb4d",
            "source": "engonow-lms-backend",
            "retryCount": 0,
            "payload": {
                "submissionId": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
                "studentId": "a2effcb1-77d8-41a3-b6e1-73c4f60219c5",
                "taskType": "TASK2",
                "taskPrompt": "Sample Prompt",
                "essayText": "Sample essay text.",
                "wordCount": 3,
            },
        }

    def test_valid_envelope_passes(self):
        envelope = self._sample_valid_envelope()
        self.validator.validate(envelope)

    def test_missing_required_field_fails(self):
        envelope = self._sample_valid_envelope()
        del envelope["traceId"]
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate(envelope)
        self.assertIn("'traceId' is a required property", str(ctx.exception))

    def test_negative_retry_count_fails(self):
        envelope = self._sample_valid_envelope()
        envelope["retryCount"] = -1
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate(envelope)
        self.assertIn("is less than the minimum of 0", str(ctx.exception))

    def test_invalid_event_type_enum_fails(self):
        envelope = self._sample_valid_envelope()
        envelope["eventType"] = "UNAUTHORIZED_EVENT_TYPE"
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate(envelope)
        self.assertIn("is not one of", str(ctx.exception))

    def test_additional_unauthorized_property_fails(self):
        envelope = self._sample_valid_envelope()
        envelope["injectedField"] = "malicious_payload"
        with self.assertRaises(ValidationError) as ctx:
            self.validator.validate(envelope)
        self.assertIn("Additional properties are not allowed", str(ctx.exception))


class TestWritingSchemas(unittest.TestCase):
    """Validation test suite for IELTS Writing event payload schemas."""

    @classmethod
    def setUpClass(cls):
        cls.req_schema = load_schema("writing_evaluation_requested.json")
        cls.comp_schema = load_schema("writing_evaluation_completed.json")
        cls.fail_schema = load_schema("writing_evaluation_failed.json")

    def test_valid_writing_evaluation_requested(self):
        payload = {
            "submissionId": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
            "studentId": "a2effcb1-77d8-41a3-b6e1-73c4f60219c5",
            "taskType": "TASK2",
            "taskPrompt": "Some people believe that community service should be compulsory.",
            "essayText": "In recent years, the debate over community service has intensified...",
            "wordCount": 275,
        }
        jsonschema.validate(instance=payload, schema=self.req_schema)

    def test_writing_requested_invalid_task_type_fails(self):
        payload = {
            "submissionId": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
            "studentId": "a2effcb1-77d8-41a3-b6e1-73c4f60219c5",
            "taskType": "INVALID_TASK_TYPE",
            "taskPrompt": "Valid prompt",
            "essayText": "Valid text",
            "wordCount": 100,
        }
        with self.assertRaises(ValidationError):
            jsonschema.validate(instance=payload, schema=self.req_schema)

    def test_valid_writing_evaluation_completed(self):
        payload = {
            "submissionId": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
            "taskAchievementScore": 7.0,
            "coherenceCohesionScore": 7.0,
            "lexicalResourceScore": 7.0,
            "grammaticalRangeScore": 7.0,
            "overallBand": 7.0,
            "feedbackDetail": {
                "examinerSummary": "A well-structured essay demonstrating Band 7.0 competence.",
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
                        "summary": "Clear stance maintained throughout.",
                        "strengths": ["Clear position"],
                        "weaknesses": ["Minor repetition"],
                        "bandGapAnalysis": "Extend supporting examples for Band 8.0.",
                    },
                    {
                        "criterion": "COHERENCE_COHESION",
                        "score": 7.0,
                        "summary": "Logical progression.",
                        "strengths": ["Discourse markers"],
                        "weaknesses": ["Repeated connectors"],
                    },
                    {
                        "criterion": "LEXICAL_RESOURCE",
                        "score": 7.0,
                        "summary": "Precise vocabulary.",
                        "strengths": ["Academic vocabulary"],
                        "weaknesses": ["Occasional collocation slip"],
                    },
                    {
                        "criterion": "GRAMMATICAL_RANGE_ACCURACY",
                        "score": 7.0,
                        "summary": "Mix of complex sentences.",
                        "strengths": ["Complex clauses"],
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
                        "explanation": "Subject-verb agreement error with gerund subject.",
                        "enhancedOptions": {
                            "band7Option": "telecommuting yields considerable advantages",
                            "band8Option": "remote working models offer distinct operational benefits",
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
                        "category": "COHERENCE_COHESION",
                        "tipText": "Vary transitional phrases.",
                        "targetBand": 8.0,
                    }
                ],
            },
        }
        jsonschema.validate(instance=payload, schema=self.comp_schema)

    def test_writing_completed_non_half_band_score_fails(self):
        payload = {
            "submissionId": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
            "taskAchievementScore": 7.33,  # Invalid: not multiple of 0.5
            "coherenceCohesionScore": 7.0,
            "lexicalResourceScore": 7.0,
            "grammaticalRangeScore": 7.0,
            "overallBand": 7.0,
            "feedbackDetail": {
                "examinerSummary": "Summary",
                "essayMetrics": {
                    "totalWords": 100,
                    "uniqueWords": 50,
                    "lexicalDiversityRatio": 0.5,
                    "averageSentenceLength": 10.0,
                    "complexSentencesRatio": 0.5,
                },
                "criteria": [],
                "corrections": [],
                "cohesiveDeviceAnalysis": {
                    "usedDevices": [],
                    "overusedOrRepetitive": [],
                    "suggestedTransitions": [],
                },
                "vocabularyUpgrades": [],
                "improvementTips": [],
            },
        }
        with self.assertRaises(ValidationError):
            jsonschema.validate(instance=payload, schema=self.comp_schema)

    def test_valid_writing_evaluation_failed(self):
        payload = {
            "submissionId": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
            "errorCode": "GEMINI_RESOURCE_EXHAUSTED",
            "errorMessage": "Upstream rate limit exceeded (429 ResourceExhausted).",
            "isRetriable": True,
            "failedAt": "2026-08-19T07:30:10Z",
        }
        jsonschema.validate(instance=payload, schema=self.fail_schema)


class TestSpeakingSchemas(unittest.TestCase):
    """Validation test suite for IELTS Speaking event payload schemas (Claim-Check)."""

    @classmethod
    def setUpClass(cls):
        cls.req_schema = load_schema("speaking_evaluation_requested.json")
        cls.comp_schema = load_schema("speaking_evaluation_completed.json")
        cls.fail_schema = load_schema("speaking_evaluation_failed.json")

    def test_valid_speaking_evaluation_requested_claim_check(self):
        payload = {
            "attemptId": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "studentId": "a2effcb1-77d8-41a3-b6e1-73c4f60219c5",
            "part": "PART_2",
            "audioRef": {
                "storageProvider": "MINIO",
                "bucket": "engonow-audio-recordings",
                "objectKey": "attempts/2026/08/f47ac10b-part2.wav",
                "checksumSha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "contentType": "audio/wav",
                "durationSeconds": 118.5,
            },
        }
        jsonschema.validate(instance=payload, schema=self.req_schema)

    def test_speaking_requested_rejects_inline_raw_audio_property(self):
        payload = {
            "attemptId": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "studentId": "a2effcb1-77d8-41a3-b6e1-73c4f60219c5",
            "part": "PART_2",
            "audioRef": {
                "storageProvider": "S3",
                "bucket": "audio-bucket",
                "objectKey": "key.wav",
                "checksumSha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "contentType": "audio/wav",
                "durationSeconds": 60.0,
            },
            "rawAudioBytesBase64": "UklGRiQAAABXQVZFZm10IBAAAAABAAEA...",  # Anti-pattern: forbidden
        }
        with self.assertRaises(ValidationError) as ctx:
            jsonschema.validate(instance=payload, schema=self.req_schema)
        self.assertIn("Additional properties are not allowed", str(ctx.exception))

    def test_speaking_requested_invalid_sha256_hash_fails(self):
        payload = {
            "attemptId": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "studentId": "a2effcb1-77d8-41a3-b6e1-73c4f60219c5",
            "part": "PART_1",
            "audioRef": {
                "storageProvider": "S3",
                "bucket": "bucket",
                "objectKey": "key.wav",
                "checksumSha256": "invalid_short_hash",  # Must be 64-character hex
                "contentType": "audio/wav",
                "durationSeconds": 45.0,
            },
        }
        with self.assertRaises(ValidationError):
            jsonschema.validate(instance=payload, schema=self.req_schema)

    def test_valid_speaking_evaluation_completed(self):
        payload = {
            "attemptId": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "fluencyCoherenceScore": 7.0,
            "lexicalResourceScore": 7.5,
            "grammaticalRangeScore": 7.0,
            "pronunciationScore": 7.0,
            "overallBand": 7.0,
            "feedbackDetail": {
                "transcript": "I would like to describe a memorable trip I took last summer...",
                "speechMetrics": {
                    "wpm": 142.5,
                    "pauseCount": 8,
                    "speechDurationSeconds": 118.5,
                    "fillerWordsCount": 3,
                    "repetitionCount": 2,
                },
                "phoneticDiagnostics": [
                    {
                        "word": "memorable",
                        "expectedIpa": "/ˈmem.ər.ə.bəl/",
                        "actualIpa": "/ˈmem.rə.bəl/",
                        "timestampMs": 2450,
                        "confidenceScore": 0.88,
                    }
                ],
                "criteria": [
                    {
                        "criterion": "FLUENCY_COHERENCE",
                        "score": 7.0,
                        "summary": "Speaks at length with minimal hesitation.",
                        "strengths": ["Natural tempo"],
                        "weaknesses": ["Occasional pause before complex ideas"],
                    },
                    {
                        "criterion": "LEXICAL_RESOURCE",
                        "score": 7.5,
                        "summary": "Wide range of idiomatic vocabulary.",
                        "strengths": ["Natural collocations"],
                        "weaknesses": ["Minor word-choice imprecision"],
                    },
                    {
                        "criterion": "GRAMMATICAL_RANGE_ACCURACY",
                        "score": 7.0,
                        "summary": "Good mix of complex structures.",
                        "strengths": ["Accurate compound clauses"],
                        "weaknesses": ["One tense slip"],
                    },
                    {
                        "criterion": "PRONUNCIATION",
                        "score": 7.0,
                        "summary": "Generally clear with good intonation.",
                        "strengths": ["Clear consonant clusters"],
                        "weaknesses": ["Minor syllable stress slip"],
                    },
                ],
                "improvementTips": [
                    {
                        "category": "FLUENCY_COHERENCE",
                        "tipText": "Use discourse markers to structure long turns.",
                        "targetBand": 8.0,
                    }
                ],
            },
        }
        jsonschema.validate(instance=payload, schema=self.comp_schema)

    def test_valid_speaking_evaluation_failed(self):
        payload = {
            "attemptId": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "errorCode": "AUDIO_DOWNLOAD_FAILED",
            "errorMessage": "Failed to fetch audio object from S3: 404 NoSuchKey.",
            "isRetriable": False,
            "failedAt": "2026-08-19T07:30:15Z",
        }
        jsonschema.validate(instance=payload, schema=self.fail_schema)


if __name__ == "__main__":
    unittest.main()
