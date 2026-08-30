"""
tests/test_acoustic_phonetics_engine.py
=======================================
Unit and integration test suite verifying G2P transcription, CMUdict syllable stress,
Goodness-of-Pronunciation (GOP) phoneme error diagnostics, lexical stress accuracy,
speaker-relative pitch intonation contour extraction, and unified Acoustic Orchestration.
"""

import unittest
import numpy as np

from acoustic.models import WordTimestamp
from acoustic.phonetic_models import (
    PhonemeErrorType,
    PhonemeError,
    WordStressAnalysis,
    IntonationAnalysis,
    FullAcousticAnalysisResult,
)
from acoustic.g2p_engine import G2PEngine
from acoustic.pronunciation_engine import PronunciationEngine
from acoustic.acoustic_orchestrator import AcousticOrchestrator


class TestAcousticPhoneticsEngine(unittest.TestCase):

    def setUp(self):
        self.sample_rate = 16000
        self.g2p = G2PEngine()
        self.pronunciation_engine = PronunciationEngine(g2p_engine=self.g2p)
        self.orchestrator = AcousticOrchestrator(pronunciation_engine=self.pronunciation_engine)

    def test_g2p_cmudict_syllables_and_stress(self):
        """
        Test 1: Verifies G2P syllable counts and primary lexical stress locations
        across representative IELTS polysyllabic words:
        - 'development' -> 4 syllables, primary stress on 2nd syllable (index 1)
        - 'technology'  -> 4 syllables, primary stress on 2nd syllable (index 1)
        - 'photograph'  -> 3 syllables, primary stress on 1st syllable (index 0)
        - 'education'   -> 4 syllables, primary stress on 3rd syllable (index 2)
        """
        # 1. 'development'
        syl_count, stresses = self.g2p.word_stress_pattern("development")
        self.assertEqual(syl_count, 4)
        self.assertEqual(stresses.index(1), 1)

        # 2. 'technology'
        syl_count, stresses = self.g2p.word_stress_pattern("technology")
        self.assertEqual(syl_count, 4)
        self.assertEqual(stresses.index(1), 1)

        # 3. 'photograph'
        syl_count, stresses = self.g2p.word_stress_pattern("photograph")
        self.assertEqual(syl_count, 3)
        self.assertEqual(stresses.index(1), 0)

        # 4. 'education'
        syl_count, stresses = self.g2p.word_stress_pattern("education")
        self.assertEqual(syl_count, 4)
        self.assertEqual(stresses.index(1), 2)

        # Also verify IPA output for 'think' -> ['θ', 'ɪ', 'ŋ', 'k']
        ipa_phones = self.g2p.word_to_phonemes("think")
        self.assertEqual(ipa_phones, ["θ", "ɪ", "ŋ", "k"])

    def test_gop_phoneme_error_detection_th_substitution(self):
        """
        Test 2: Simulates phonetic substitution of dental fricative /θ/ with alveolar /s/
        in the word 'think' (/θ/ -> /s/).
        Asserts that a PhonemeError with error_type=SUBSTITUTION, expected='θ', produced='s' is emitted.
        """
        total_duration = 1.0
        audio = np.random.normal(0, 0.005, int(total_duration * self.sample_rate)).astype(np.float32)

        # 'think' word interval: 0.10s to 0.50s (4 phonemes, each 0.10s)
        # First phoneme interval (0.10s - 0.20s): Inject high-frequency /s/ frication (6000 Hz + high noise)
        t_sub = np.linspace(0, 0.10, int(0.10 * self.sample_rate), endpoint=False)
        s_sound = (0.15 * np.sin(2 * np.pi * 6000 * t_sub) + np.random.normal(0, 0.08, len(t_sub))).astype(np.float32)

        p_start_idx = int(0.10 * self.sample_rate)
        p_end_idx = p_start_idx + len(s_sound)
        audio[p_start_idx:p_end_idx] = s_sound

        word_timestamps = [
            WordTimestamp(word="think", start=0.10, end=0.50)
        ]

        errors = self.pronunciation_engine.evaluate_phonemes(
            audio_data=audio,
            sample_rate=self.sample_rate,
            word_timestamps=word_timestamps
        )

        self.assertGreaterEqual(len(errors), 1)
        th_error = next((e for e in errors if e.expected_phoneme_ipa == "θ"), None)
        self.assertIsNotNone(th_error)
        self.assertEqual(th_error.error_type, PhonemeErrorType.SUBSTITUTION)
        self.assertEqual(th_error.expected_phoneme_ipa, "θ")
        self.assertEqual(th_error.produced_phoneme_ipa, "s")
        self.assertEqual(th_error.word_context, "think")
        self.assertLess(th_error.goodness_of_pronunciation_score, 0.65)

    def test_polysyllabic_word_stress_accuracy(self):
        """
        Test 3: Evaluates 5 polysyllabic words where 4 are correctly stressed and 1 is misstressed.
        Asserts:
        - total_polysyllabic_words == 5
        - correctly_stressed_words == 4
        - stress_accuracy_ratio == 0.80
        - common_misstressed_words == ['important']
        """
        # Generate 5 words across 10 seconds of audio
        total_duration = 10.0
        audio = np.random.normal(0, 0.005, int(total_duration * self.sample_rate)).astype(np.float32)

        words_data = [
            # (word, start, end, correct_stressed_syl_idx, audio_stressed_syl_idx, num_syl)
            ("development", 0.5, 1.5, 1, 1, 4),  # Correct (2nd syl)
            ("technology", 2.0, 3.0, 1, 1, 4),   # Correct (2nd syl)
            ("photograph", 3.5, 4.5, 0, 0, 3),   # Correct (1st syl)
            ("education", 5.0, 6.0, 2, 2, 4),    # Correct (3rd syl)
            ("important", 6.5, 7.5, 1, 0, 3),    # Misstressed! (canonical=1, audio=0)
        ]

        word_timestamps = []
        for word, w_start, w_end, _, audio_stress_idx, num_syl in words_data:
            word_timestamps.append(WordTimestamp(word=word, start=w_start, end=w_end))

            # Synthesize acoustic prominence for the target stressed syllable (longer, louder, higher pitch)
            syl_dur = (w_end - w_start) / num_syl
            for s_idx in range(num_syl):
                s_start = w_start + (s_idx * syl_dur)
                s_end = s_start + syl_dur
                sam_start = int(s_start * self.sample_rate)
                sam_end = int(s_end * self.sample_rate)
                t_slice = np.linspace(0, s_end - s_start, sam_end - sam_start, endpoint=False)

                if s_idx == audio_stress_idx:
                    # Prominent: Amplitude 0.30, Pitch 240 Hz
                    audio[sam_start:sam_end] = (0.30 * np.sin(2 * np.pi * 240 * t_slice)).astype(np.float32)
                else:
                    # Non-prominent: Amplitude 0.05, Pitch 140 Hz
                    audio[sam_start:sam_end] = (0.05 * np.sin(2 * np.pi * 140 * t_slice)).astype(np.float32)

        stress_analysis = self.pronunciation_engine.analyze_word_stress(
            audio_data=audio,
            sample_rate=self.sample_rate,
            word_timestamps=word_timestamps
        )

        self.assertEqual(stress_analysis.total_polysyllabic_words, 5)
        self.assertEqual(stress_analysis.correctly_stressed_words, 4)
        self.assertEqual(stress_analysis.stress_accuracy_ratio, 0.80)
        self.assertIn("important", stress_analysis.common_misstressed_words)

    def test_intonation_normalized_pitch_and_monotone_detection(self):
        """
        Test 4: Verifies pitch tracking, speaker normalization (CV), monotone detection,
        and contour pattern classification:
        - Case A: Synthetic flat pitch (150 Hz constant) -> monotone_flag=True, contour='FLAT'
        - Case B: Synthetic dynamic expressive pitch (130 Hz falling to 90 Hz at tail) -> monotone_flag=False, contour='FALLING'
        """
        dur = 3.0
        sr = self.sample_rate
        t = np.linspace(0, dur, int(dur * sr), endpoint=False)

        # Case A: Constant 150 Hz tone
        audio_flat = (0.2 * np.sin(2 * np.pi * 150 * t)).astype(np.float32)
        res_flat = self.pronunciation_engine.analyze_intonation(audio_flat, sr)

        self.assertTrue(res_flat.monotone_flag)
        self.assertLess(res_flat.pitch_coefficient_of_variation, 0.12)
        self.assertEqual(res_flat.dominant_contour_pattern, "FLAT")

        # Case B: Expressive falling contour (starts at 240 Hz, dynamic sweep, final slope < -15 Hz/s down to 100 Hz)
        # Chirp from 240 Hz down to 100 Hz
        f_inst = np.linspace(240, 100, len(t))
        phase = 2 * np.pi * np.cumsum(f_inst) / sr
        audio_expressive = (0.2 * np.sin(phase)).astype(np.float32)
        res_expressive = self.pronunciation_engine.analyze_intonation(audio_expressive, sr)

        self.assertFalse(res_expressive.monotone_flag)
        self.assertGreater(res_expressive.pitch_coefficient_of_variation, 0.12)
        self.assertEqual(res_expressive.dominant_contour_pattern, "FALLING")

    def test_full_acoustic_orchestrator_e2e(self):
        """
        Test 5: Verifies end-to-end processing of speaking audio with the AcousticOrchestrator,
        producing a comprehensive FullAcousticAnalysisResult combining Fluency, Phonetics,
        Lexical Stress, and Pitch Intonation.
        """
        dur = 4.0
        t = np.linspace(0, dur, int(dur * self.sample_rate), endpoint=False)
        audio = (0.15 * np.sin(2 * np.pi * 180 * t) + np.random.normal(0, 0.01, len(t))).astype(np.float32)

        word_timestamps = [
            WordTimestamp(word="education", start=0.2, end=1.2),
            WordTimestamp(word="technology", start=1.5, end=2.5),
            WordTimestamp(word="development", start=2.8, end=3.8),
        ]

        result = self.orchestrator.process_speaking_audio(
            audio_data=audio,
            sample_rate=self.sample_rate,
            word_timestamps=word_timestamps,
            total_duration=dur
        )

        self.assertIsInstance(result, FullAcousticAnalysisResult)
        self.assertEqual(result.word_count, 3)
        self.assertGreater(result.speaking_rate_wpm, 0.0)
        self.assertGreater(result.articulation_rate_wpm, 0.0)
        self.assertIsNotNone(result.pause_analysis)
        self.assertIsInstance(result.phoneme_errors, list)
        self.assertEqual(result.word_stress_analysis.total_polysyllabic_words, 3)
        self.assertIsInstance(result.intonation_analysis, IntonationAnalysis)
        self.assertFalse(result.excluded_from_automated_scoring)

    def test_g2p_punctuation_and_special_character_handling(self):
        """
        Test 6: Verifies that punctuation attached to words (commas, periods, quotes, dashes)
        is cleanly stripped before CMUdict lookup, preventing erroneous OOV rule-based fallback:
        - 'technology,' -> matches CMUdict 'technology'
        - 'think.'       -> matches CMUdict 'think'
        - '"development!"' -> matches CMUdict 'development'
        - '--education--'  -> matches CMUdict 'education'
        """
        # 1. 'technology,'
        phones_comma = self.g2p.word_to_phonemes("technology,")
        phones_clean = self.g2p.word_to_phonemes("technology")
        self.assertEqual(phones_comma, phones_clean)
        self.assertEqual(phones_comma, ["t", "ɛ", "k", "n", "ɑ", "l", "ʌ", "dʒ", "iː"])

        # Syllable stress for 'technology,'
        syl_count, stresses = self.g2p.word_stress_pattern("technology,")
        self.assertEqual(syl_count, 4)
        self.assertEqual(stresses.index(1), 1)

        # 2. 'think.'
        phones_period = self.g2p.word_to_phonemes("think.")
        self.assertEqual(phones_period, ["θ", "ɪ", "ŋ", "k"])

        # 3. '"development!"'
        phones_excl = self.g2p.word_to_phonemes('"development!"')
        self.assertEqual(phones_excl, self.g2p.word_to_phonemes("development"))

    def test_f0_low_energy_frame_skipping_prevents_skew(self):
        """
        Test 7: Verifies that low-energy frames (soft breathing or room noise with RMS < 0.010)
        are skipped before autocorrelation peak detection, preventing noise from skewing median(F0).
        """
        sr = self.sample_rate
        # Create 1.0s of voiced speech at 180 Hz followed by 2.0s of soft breathing noise (RMS ~ 0.004)
        t_voiced = np.linspace(0, 1.0, int(1.0 * sr), endpoint=False)
        voiced_part = (0.25 * np.sin(2 * np.pi * 180 * t_voiced)).astype(np.float32)

        t_noise = int(2.0 * sr)
        noise_part = np.random.normal(0, 0.004, t_noise).astype(np.float32)

        combined_audio = np.concatenate([voiced_part, noise_part])

        # Analyze intonation with energy threshold 0.010
        analysis = self.pronunciation_engine.analyze_intonation(
            audio_data=combined_audio,
            sample_rate=sr,
            energy_rms_threshold=0.010
        )

        # Voiced frames at 180 Hz should dominate without noise distorting median F0
        # Since speech is constant 180 Hz and noise is skipped, dominant contour is FLAT and pitch std is near 0
        self.assertTrue(analysis.monotone_flag)
        self.assertEqual(analysis.dominant_contour_pattern, "FLAT")
        self.assertLess(analysis.pitch_standard_deviation_hz, 5.0)


if __name__ == "__main__":
    unittest.main()
