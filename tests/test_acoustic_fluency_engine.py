"""
tests/test_acoustic_fluency_engine.py
=====================================
Unit test suite verifying the acoustic fluency engine, pause classification thresholds,
two-layer disfluency detection/reconciliation, and audio continuity/dropout gating.
"""

import unittest
import numpy as np

from acoustic.models import WordTimestamp, PauseAnalysis, FluencyResult
from acoustic.continuity_gate import AudioContinuityGate
from acoustic.fluency_engine import FluencyEngine


class TestAcousticFluencyEngine(unittest.TestCase):

    def setUp(self):
        self.sample_rate = 16000
        self.continuity_gate = AudioContinuityGate(
            artifact_duration_threshold_ratio=0.15,
            transition_window_seconds=0.005,
            zero_energy_rms_threshold=1e-5
        )
        self.engine = FluencyEngine(continuity_gate=self.continuity_gate)

    def test_fluency_formulas_mathematical_precision(self):
        """
        Test 1: Verifies mathematical precision of fluency formulas.
        Hand-crafted 100-word stream across 60.0s total duration with 15.0s total pause duration.
        Expected:
        - speaking_rate_wpm == 100.0
        - phonation_time_seconds == 45.0
        - articulation_rate_wpm == 133.33
        - phonation_ratio == 0.75
        """
        # Create 100 words with 0.45s duration each (45.0s speech total)
        # 15 pauses of 1.0s each (15.0s pause total) distributed across stream
        word_timestamps = []
        curr_time = 0.0
        for i in range(100):
            w_start = curr_time
            w_end = w_start + 0.45
            word_timestamps.append(WordTimestamp(word=f"word{i}", start=round(w_start, 3), end=round(w_end, 3)))
            curr_time = w_end
            if i < 15:
                # Add 1.0s natural pause
                curr_time += 1.0

        total_duration = 60.0
        # Ambient room tone (non-zero noise floor so pauses are natural)
        audio = np.random.normal(0, 0.01, int(total_duration * self.sample_rate)).astype(np.float32)

        result = self.engine.analyze_fluency(
            audio_data=audio,
            sample_rate=self.sample_rate,
            word_timestamps=word_timestamps,
            total_duration_seconds=total_duration
        )

        self.assertEqual(result.word_count, 100)
        self.assertEqual(result.speaking_rate_wpm, 100.0)
        self.assertEqual(result.phonation_time_seconds, 45.0)
        self.assertEqual(result.articulation_rate_wpm, 133.33)
        self.assertEqual(result.phonation_ratio, 0.75)
        self.assertFalse(result.excluded_from_automated_scoring)

    def test_pause_classification_thresholds(self):
        """
        Test 2: Verifies pause classification grid:
        - Gap 0.15s -> Ignored (< 0.25s)
        - Gap 0.50s -> Counted in silent_micro_pause_count (0.25s - 0.75s)
        - Gap 1.20s -> Counted in silent_cognitive_pause_count (> 0.75s)
        - Word 'um' -> Counted in filled_pause_count and filled_pause_counts_by_type['um']
        """
        # Ambient noise background
        total_duration = 6.0
        audio = np.random.normal(0, 0.01, int(total_duration * self.sample_rate)).astype(np.float32)

        word_timestamps = [
            WordTimestamp(word="hello", start=0.00, end=0.50),
            # Gap 1: 0.65 - 0.50 = 0.15s (Ignored)
            WordTimestamp(word="there", start=0.65, end=1.15),
            # Gap 2: 1.65 - 1.15 = 0.50s (Micro-pause)
            WordTimestamp(word="world", start=1.65, end=2.15),
            # Gap 3: 3.35 - 2.15 = 1.20s (Cognitive pause)
            WordTimestamp(word="um", start=3.35, end=3.85),  # Filled pause
            # Gap 4: 4.00 - 3.85 = 0.15s (Ignored)
            WordTimestamp(word="yes", start=4.00, end=4.50),
        ]

        result = self.engine.analyze_fluency(
            audio_data=audio,
            sample_rate=self.sample_rate,
            word_timestamps=word_timestamps,
            total_duration_seconds=total_duration
        )

        pa = result.pause_analysis
        self.assertEqual(pa.silent_micro_pause_count, 1)
        self.assertEqual(pa.silent_cognitive_pause_count, 1)
        self.assertAlmostEqual(pa.average_cognitive_pause_duration_seconds, 1.20, places=2)
        self.assertEqual(pa.filled_pause_count, 1)
        self.assertEqual(pa.filled_pause_counts_by_type.get("um"), 1)
        self.assertEqual(pa.possible_technical_artifact_count, 0)

    def test_continuity_gate_detects_network_dropouts(self):
        """
        Test 3: Simulates a 1.5s instantaneous zero-energy packet drop.
        Assert flagged as POSSIBLE_TECHNICAL_ARTIFACT and excluded from silent_cognitive_pause_count.
        """
        total_duration = 5.0
        t = np.linspace(0, total_duration, int(total_duration * self.sample_rate), endpoint=False)
        audio = (0.2 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)

        # Inject instantaneous digital zero for 1.5s (from 1.0s to 2.5s)
        zero_start_idx = int(1.0 * self.sample_rate)
        zero_end_idx = int(2.5 * self.sample_rate)
        audio[zero_start_idx:zero_end_idx] = 0.0

        word_timestamps = [
            WordTimestamp(word="speaking", start=0.0, end=1.0),
            # 1.5s gap from 1.0s to 2.5s (Digital dropout)
            WordTimestamp(word="fluency", start=2.5, end=3.5),
        ]

        result = self.engine.analyze_fluency(
            audio_data=audio,
            sample_rate=self.sample_rate,
            word_timestamps=word_timestamps,
            total_duration_seconds=total_duration
        )

        pa = result.pause_analysis
        # Dropout must be identified as artifact and NOT penalized as a cognitive pause
        self.assertEqual(pa.possible_technical_artifact_count, 1)
        self.assertEqual(pa.silent_cognitive_pause_count, 0)

    def test_fifteen_percent_artifact_exclusion_rule(self):
        """
        Test 4: Total duration 30.0s with 6.0s of network dropouts (20% > 15%).
        Asserts excluded_from_automated_scoring == True and exclusion_reason contains percentage.
        """
        total_duration = 30.0
        audio = (0.1 * np.sin(2 * np.pi * 300 * np.linspace(0, total_duration, int(total_duration * self.sample_rate)))).astype(np.float32)

        # Inject two 3.0s dropouts (total 6.0s = 20.0%)
        # Dropout 1: 5.0s - 8.0s (3.0s)
        audio[int(5.0 * self.sample_rate) : int(8.0 * self.sample_rate)] = 0.0
        # Dropout 2: 15.0s - 18.0s (3.0s)
        audio[int(15.0 * self.sample_rate) : int(18.0 * self.sample_rate)] = 0.0

        word_timestamps = [
            WordTimestamp(word="sentence", start=1.0, end=5.0),
            # Gap 1 (Dropout): 5.0 - 8.0 (3.0s)
            WordTimestamp(word="middle", start=8.0, end=15.0),
            # Gap 2 (Dropout): 15.0 - 18.0 (3.0s)
            WordTimestamp(word="ending", start=18.0, end=25.0),
        ]

        result = self.engine.analyze_fluency(
            audio_data=audio,
            sample_rate=self.sample_rate,
            word_timestamps=word_timestamps,
            total_duration_seconds=total_duration
        )

        self.assertTrue(result.excluded_from_automated_scoring)
        self.assertIsNotNone(result.exclusion_reason)
        self.assertIn("20.0%", result.exclusion_reason)

    def test_reconciliation_of_transcript_and_acoustic_fillers(self):
        """
        Test 5: Verifies union reconciliation of Layer 1 (transcript) and Layer 2 (acoustic).
        Transcript captures 'like', but misses an 'uh' in gap 0.5s - 1.1s.
        Acoustic detector spots the 'uh' -> Total filled_pause_count == 2.
        """
        total_duration = 4.0
        t = np.linspace(0, total_duration, int(total_duration * self.sample_rate), endpoint=False)
        audio = np.random.normal(0, 0.005, len(t)).astype(np.float32)

        # Add stationary vocalic murmur ("uh" at 150 Hz) during gap 0.5s - 1.0s
        filler_start = int(0.50 * self.sample_rate)
        filler_end = int(1.00 * self.sample_rate)
        audio[filler_start:filler_end] += (0.05 * np.sin(2 * np.pi * 150 * t[filler_start:filler_end])).astype(np.float32)

        word_timestamps = [
            WordTimestamp(word="i", start=0.0, end=0.5),
            # Gap from 0.5s to 1.1s: contains un-transcribed acoustic "uh"
            WordTimestamp(word="think", start=1.1, end=1.6),
            # Layer 1 transcript filler
            WordTimestamp(word="like", start=1.7, end=2.1),
            WordTimestamp(word="that", start=2.2, end=2.6),
        ]

        result = self.engine.analyze_fluency(
            audio_data=audio,
            sample_rate=self.sample_rate,
            word_timestamps=word_timestamps,
            total_duration_seconds=total_duration
        )

        pa = result.pause_analysis
        self.assertEqual(pa.filled_pause_count, 2)
        self.assertEqual(pa.filled_pause_counts_by_type.get("like"), 1)
        self.assertEqual(pa.filled_pause_counts_by_type.get("uh"), 1)

    def test_multi_word_filler_you_know(self):
        """
        Test 6: Verifies multi-word filler 'you know' is treated as a single filled pause.
        """
        word_timestamps = [
            WordTimestamp(word="well", start=0.0, end=0.4),       # Filled pause 'well'
            WordTimestamp(word="you", start=0.5, end=0.7),        # Start of 'you know'
            WordTimestamp(word="know", start=0.75, end=1.0),      # End of 'you know'
            WordTimestamp(word="it", start=1.2, end=1.4),
            WordTimestamp(word="is", start=1.45, end=1.65),
            WordTimestamp(word="good", start=1.7, end=2.0),
        ]
        audio = np.random.normal(0, 0.01, int(3.0 * self.sample_rate)).astype(np.float32)

        result = self.engine.analyze_fluency(
            audio_data=audio,
            sample_rate=self.sample_rate,
            word_timestamps=word_timestamps,
            total_duration_seconds=3.0
        )

        pa = result.pause_analysis
        self.assertEqual(pa.filled_pause_count, 2)
        self.assertEqual(pa.filled_pause_counts_by_type.get("well"), 1)
        self.assertEqual(pa.filled_pause_counts_by_type.get("you know"), 1)

    def test_raw_int16_pcm_bytes_input(self):
        """
        Test 7: Verifies FluencyEngine operates seamlessly on raw 16-bit PCM bytes.
        """
        audio_float = (0.2 * np.sin(2 * np.pi * 200 * np.linspace(0, 2.0, int(2.0 * self.sample_rate)))).astype(np.float32)
        pcm_bytes = (audio_float * 32767).astype(np.int16).tobytes()

        word_timestamps = [
            WordTimestamp(word="hello", start=0.0, end=0.8),
            WordTimestamp(word="world", start=1.0, end=1.8),
        ]

        result = self.engine.analyze_fluency(
            audio_data=pcm_bytes,
            sample_rate=self.sample_rate,
            word_timestamps=word_timestamps,
            total_duration_seconds=2.0
        )

        self.assertEqual(result.word_count, 2)
        self.assertEqual(result.speaking_rate_wpm, 60.0)
        self.assertFalse(result.excluded_from_automated_scoring)

    def test_edge_case_zero_words_detected(self):
        """
        Test 8: Edge case where recording contains only silence/noise and no words are detected (word_count == 0).
        Verifies function returns WPM = 0.0 and phonation_ratio = 0.0 without ZeroDivisionError.
        """
        audio = np.random.normal(0, 0.005, int(10.0 * self.sample_rate)).astype(np.float32)
        word_timestamps = []  # No words detected

        result = self.engine.analyze_fluency(
            audio_data=audio,
            sample_rate=self.sample_rate,
            word_timestamps=word_timestamps,
            total_duration_seconds=10.0
        )

        self.assertEqual(result.word_count, 0)
        self.assertEqual(result.speaking_rate_wpm, 0.0)
        self.assertEqual(result.articulation_rate_wpm, 0.0)
        self.assertEqual(result.phonation_ratio, 0.0)
        self.assertEqual(result.phonation_time_seconds, 0.0)
        self.assertEqual(result.total_duration_seconds, 10.0)
        self.assertFalse(result.excluded_from_automated_scoring)

    def test_wav_container_ingestion_and_resampling(self):
        """
        Test 9: Verifies decoding and resampling of WAV container with non-16kHz stereo audio.
        """
        import io
        import scipy.io.wavfile as wavfile

        # Generate 2 seconds of 44.1kHz stereo audio
        orig_rate = 44100
        t = np.linspace(0, 2.0, int(2.0 * orig_rate), endpoint=False)
        left = (0.2 * np.sin(2 * np.pi * 220 * t) * 32767).astype(np.int16)
        right = (0.2 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
        stereo = np.column_stack([left, right])

        bio = io.BytesIO()
        wavfile.write(bio, orig_rate, stereo)
        wav_bytes = bio.getvalue()

        word_timestamps = [
            WordTimestamp(word="testing", start=0.1, end=0.9),
            WordTimestamp(word="audio", start=1.1, end=1.9),
        ]

        result = self.engine.analyze_fluency(
            audio_data=wav_bytes,
            sample_rate=orig_rate,
            word_timestamps=word_timestamps,
            total_duration_seconds=2.0
        )

        self.assertEqual(result.word_count, 2)
        self.assertEqual(result.speaking_rate_wpm, 60.0)
        self.assertFalse(result.excluded_from_automated_scoring)


if __name__ == "__main__":
    unittest.main()
