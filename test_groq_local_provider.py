import unittest

from providers.config import ProviderConfig
from providers.groq_local_provider import GroqLocalProvider


def provider():
    return GroqLocalProvider(
        ProviderConfig(
            provider_name="GROQ_LOCAL",
            groq_api_key="",
            gemini_api_key="",
            gemini_model="",
            azure_speech_key="",
            azure_speech_region="",
            azure_speech_language="en-US",
            word_confidence_threshold=0.7,
            pause_annotation_min_sec=0.5,
            enable_acoustic_diagnostics=False,
            fallback_score_pr=4,
            fallback_score_fc=4,
            fallback_score_gra=4,
            fallback_score_lr=4,
        )
    )


class AnnotatedTranscriptTests(unittest.TestCase):
    def test_fillers_are_annotated_before_confidence(self):
        transcript, coverage = provider()._build_annotated_transcript({
            "words": [
                {"word": "Um,", "start": 0.0, "end": 0.2, "probability": 0.2},
                {"word": "answer", "start": 0.3, "end": 0.7, "probability": 0.9},
                {"word": "unclear", "start": 1.3, "end": 1.6, "probability": 0.4},
            ]
        })

        self.assertEqual(
            transcript,
            "[FILLER: Um,] answer [PAUSE: 0.6s] unclear[LOW_CONFIDENCE]",
        )
        self.assertAlmostEqual(coverage, 1 / 3)

    def test_high_confidence_filler_is_not_counted_as_genuine_coverage(self):
        transcript, coverage = provider()._build_annotated_transcript({
            "words": [
                {"word": "uh", "start": 0.0, "end": 0.2, "probability": 0.99},
                {"word": "yes", "start": 0.3, "end": 0.5, "probability": 0.99},
            ]
        })

        self.assertEqual(transcript, "[FILLER: uh] yes")
        self.assertEqual(coverage, 0.5)


if __name__ == "__main__":
    unittest.main()
