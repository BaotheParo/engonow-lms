import math
import statistics
import unittest

from acoustic_engine import (
    _count_fillers,
    _fc_raw_to_band,
    _normalize_word,
    compute_pronunciation_features,
    parse_whisper_output,
    score_acoustic,
)


def response(probabilities, *, logprobs=None):
    words = []
    for index, probability in enumerate(probabilities):
        entry = {
            "word": f" word{index}",
            "start": index * 0.4,
            "end": index * 0.4 + 0.25,
            "probability": probability,
        }
        if logprobs is not None:
            entry["logprob"] = logprobs[index]
        words.append(entry)
    return {
        "words": words,
        "segments": [{
            "id": 0,
            "start": 0.0,
            "end": max(1.0, len(words) * 0.4),
            "text": "test",
            "avg_logprob": -0.25,
        }],
    }


class ProbabilityFallbackTests(unittest.TestCase):
    def test_zero_none_and_sentinel_use_segment_fallback(self):
        parsed = parse_whisper_output(response([0.0, None, 0.001]))
        self.assertEqual(parsed.logprob_fallback_count, 3)
        self.assertTrue(all(word.logprob == -0.25 for word in parsed.words))

    def test_genuine_low_probabilities_are_preserved(self):
        values = [0.01, 0.02, 0.05, 0.1]
        parsed = parse_whisper_output(response(values))
        self.assertEqual(parsed.logprob_fallback_count, 0)
        for word, probability in zip(parsed.words, values):
            self.assertAlmostEqual(word.probability, probability)
            self.assertAlmostEqual(word.logprob, math.log(probability + 1e-9))

    def test_word_logprob_precedes_segment_fallback(self):
        parsed = parse_whisper_output(response([0.0], logprobs=[-1.2]))
        self.assertEqual(parsed.logprob_fallback_count, 0)
        self.assertEqual(parsed.words[0].logprob, -1.2)

    def test_high_fallback_rate_is_returned_in_warnings(self):
        result = score_acoustic(response([0.0, 0.0, 0.9, 0.9, 0.9]))
        self.assertTrue(
            any(warning.startswith("HIGH_FALLBACK_RATE: 40.0%") for warning in result.warnings)
        )

    def test_low_fallback_rate_does_not_warn(self):
        result = score_acoustic(response([0.0] + [0.9] * 9))
        self.assertFalse(
            any(warning.startswith("HIGH_FALLBACK_RATE:") for warning in result.warnings)
        )

    def test_fallback_values_do_not_skew_pr_statistics(self):
        genuine = [0.9, 0.7, 0.5, 0.3, 0.1]
        parsed = parse_whisper_output(response(genuine + [0.0] * 5))
        features = compute_pronunciation_features(parsed)
        genuine_logprobs = [math.log(value + 1e-9) for value in genuine]

        self.assertEqual(features.genuine_confidence_word_count, 5)
        self.assertEqual(features.genuine_confidence_coverage, 0.5)
        self.assertAlmostEqual(features.mean_cal_logprob, statistics.mean(genuine_logprobs))
        self.assertAlmostEqual(features.logprob_std, statistics.stdev(genuine_logprobs))
        self.assertAlmostEqual(features.p5_cal_logprob, min(genuine_logprobs))

    def test_insufficient_genuine_data_uses_segment_fallback(self):
        result = score_acoustic(response([0.9] * 4 + [0.0] * 6))
        self.assertEqual(result.pr_score, 7)
        self.assertEqual(result.pr_raw, -0.25)
        self.assertFalse(result.pronunciation.calibration_reliable)
        self.assertTrue(
            any(
                warning.startswith("INSUFFICIENT_GENUINE_PR_DATA:")
                for warning in result.warnings
            )
        )

    def test_segment_fallback_band_thresholds(self):
        cases = [
            (-0.17, 8),
            (-0.18, 7),
            (-0.27, 7),
            (-0.28, 6),
            (-0.37, 6),
            (-0.38, 5),
            (-0.49, 5),
            (-0.50, 4),
            (-0.64, 4),
            (-0.65, 3),
        ]
        for avg_logprob, expected_band in cases:
            with self.subTest(avg_logprob=avg_logprob):
                raw_response = response([0.0] * 5)
                raw_response["segments"][0]["avg_logprob"] = avg_logprob
                features = compute_pronunciation_features(
                    parse_whisper_output(raw_response)
                )
                self.assertEqual(features.pr_band, expected_band)
                self.assertEqual(features.mean_cal_logprob, avg_logprob)
                self.assertEqual(features.pr_raw, avg_logprob)

    def test_segment_fallback_defaults_to_minus_point_five(self):
        raw_response = response([0.0] * 5)
        raw_response["segments"] = []
        features = compute_pronunciation_features(parse_whisper_output(raw_response))
        self.assertEqual(features.pr_band, 4)
        self.assertEqual(features.mean_cal_logprob, -0.5)
        self.assertEqual(features.pr_raw, -0.5)


class NormalizationTests(unittest.TestCase):
    def test_normalization_is_for_comparison_only(self):
        raw = "  Think, "
        self.assertEqual(_normalize_word(raw), "think")
        parsed = parse_whisper_output({
            "words": [{"word": raw, "start": 0.0, "end": 0.3, "probability": 0.9}],
        })
        self.assertEqual(parsed.words[0].word, raw)
        self.assertEqual(parsed.raw_transcript, raw)

    def test_leading_space_filler_is_counted(self):
        parsed = parse_whisper_output({
            "words": [
                {"word": " um", "start": 0.0, "end": 0.2, "probability": 0.9},
                {"word": " test", "start": 0.3, "end": 0.5, "probability": 0.9},
            ],
        })
        self.assertEqual(_count_fillers(parsed.words), 1)

    def test_only_nonlexical_fillers_are_safe_for_text_annotation(self):
        from acoustic_engine import is_nonlexical_filler

        self.assertTrue(is_nonlexical_filler(" um, "))
        self.assertTrue(is_nonlexical_filler("hmm"))
        self.assertFalse(is_nonlexical_filler("like"))
        self.assertFalse(is_nonlexical_filler("you know"))
        self.assertFalse(is_nonlexical_filler("I mean"))


class FluencyBandTests(unittest.TestCase):
    def test_recalibrated_boundaries(self):
        expected = {
            0.09: 1, 0.10: 2, 0.20: 3, 0.25: 4, 0.35: 5,
            0.45: 6, 0.57: 7, 0.60: 7, 0.69: 7,
            0.70: 8, 0.84: 9,
        }
        for raw, band in expected.items():
            with self.subTest(raw=raw):
                self.assertEqual(_fc_raw_to_band(raw), band)


if __name__ == "__main__":
    unittest.main()
