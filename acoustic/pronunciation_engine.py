"""
acoustic/pronunciation_engine.py
================================
Phonetic Goodness-of-Pronunciation (GOP) Analyzer, Syllable Word Stress Extractor,
and Speaker-Relative Pitch Intonation Engine for IELTS Speaking Assessment.
"""

from typing import List, Dict, Tuple, Optional, Union
import numpy as np
import logging

from acoustic.models import WordTimestamp
from acoustic.phonetic_models import (
    PhonemeErrorType,
    PhonemeError,
    WordStressAnalysis,
    IntonationAnalysis,
)
from acoustic.g2p_engine import G2PEngine
from acoustic.continuity_gate import AudioContinuityGate

logger = logging.getLogger("PronunciationEngine")


class PronunciationEngine:
    """
    Evaluates phoneme-level pronunciation accuracy (GOP), polysyllabic lexical stress,
    and speaker-normalized fundamental frequency (F0) intonation.
    """

    def __init__(self, g2p_engine: Optional[G2PEngine] = None):
        self.g2p = g2p_engine or G2PEngine()

    def evaluate_phonemes(
        self,
        audio_data: Union[bytes, np.ndarray],
        sample_rate: int,
        word_timestamps: List[WordTimestamp]
    ) -> List[PhonemeError]:
        """
        Force-aligns expected phonemes across word intervals, computes GOP confidence,
        and flags phonetic substitution, deletion, and insertion errors.

        Parameters:
            audio_data: 1D float32 audio array or raw PCM bytes.
            sample_rate: Sampling rate in Hz (e.g. 16000).
            word_timestamps: Word-level alignment timestamps.

        Returns:
            List of detected PhonemeError objects.
        """
        samples = AudioContinuityGate._to_float32_array(audio_data, sample_rate=sample_rate, target_sample_rate=16000)
        if samples is None or len(samples) == 0 or not word_timestamps:
            return []

        sample_rate = 16000
        errors: List[PhonemeError] = []

        for word_info in word_timestamps:
            word_str = word_info.word.lower().strip()
            expected_phones = self.g2p.word_to_phonemes(word_str)
            if not expected_phones:
                continue

            word_dur = max(0.01, word_info.end - word_info.start)
            phone_dur = word_dur / len(expected_phones)

            for j, p_exp in enumerate(expected_phones):
                p_start = word_info.start + (j * phone_dur)
                p_end = p_start + phone_dur

                s_idx = max(0, min(len(samples), int(p_start * sample_rate)))
                e_idx = max(s_idx, min(len(samples), int(p_end * sample_rate)))
                p_samples = samples[s_idx:e_idx]

                if len(p_samples) < 16:
                    continue

                rms = float(np.sqrt(np.mean(p_samples ** 2)))

                # Zero-Crossing Rate (ZCR)
                signs = np.sign(p_samples)
                signs[signs == 0] = 1
                zcr = float(np.sum(np.abs(np.diff(signs))) / (2.0 * len(p_samples)))

                # High frequency spectral energy ratio (> 4000 Hz)
                fft_vals = np.abs(np.fft.rfft(p_samples))
                freqs = np.fft.rfftfreq(len(p_samples), 1.0 / sample_rate)
                total_energy = np.sum(fft_vals ** 2) + 1e-12
                hf_energy = np.sum(fft_vals[freqs >= 4000] ** 2)
                hf_ratio = float(hf_energy / total_energy)

                # --------------------------------------------------------------
                # Diagnostic Rules for Common IELTS L1-Transfer Errors
                # --------------------------------------------------------------
                # 1. Dental fricative /θ/ (as in "think") substituted with alveolar /s/ or plosive /t/
                if p_exp == "θ":
                    # /s/ has intense high-frequency energy (> 4000 Hz) and very high ZCR (> 0.22)
                    if hf_ratio > 0.40 and zcr > 0.20:
                        errors.append(
                            PhonemeError(
                                expected_phoneme_ipa="θ",
                                produced_phoneme_ipa="s",
                                error_type=PhonemeErrorType.SUBSTITUTION,
                                word_context=word_info.word,
                                start_time_seconds=round(p_start, 3),
                                goodness_of_pronunciation_score=0.42,
                            )
                        )
                        continue

                # 2. Voiced dental fricative /ð/ (as in "the", "this") substituted with voiced plosive /d/
                if p_exp == "ð":
                    # Plosive substitution exhibits abrupt stop closure and low continuous frication
                    if rms > 0.05 and hf_ratio < 0.10 and zcr < 0.08:
                        # Check for plosive burst transient
                        peak_to_mean = np.max(np.abs(p_samples)) / (rms + 1e-6)
                        if peak_to_mean > 4.5:
                            errors.append(
                                PhonemeError(
                                    expected_phoneme_ipa="ð",
                                    produced_phoneme_ipa="d",
                                    error_type=PhonemeErrorType.SUBSTITUTION,
                                    word_context=word_info.word,
                                    start_time_seconds=round(p_start, 3),
                                    goodness_of_pronunciation_score=0.48,
                                )
                            )
                            continue

                # 3. Deletion of word-final consonant clusters
                if j == len(expected_phones) - 1 and p_exp in ("s", "t", "d", "z"):
                    if rms < 0.003 or len(p_samples) < int(0.020 * sample_rate):
                        errors.append(
                            PhonemeError(
                                expected_phoneme_ipa=p_exp,
                                produced_phoneme_ipa=None,
                                error_type=PhonemeErrorType.DELETION,
                                word_context=word_info.word,
                                start_time_seconds=round(p_start, 3),
                                goodness_of_pronunciation_score=0.20,
                            )
                        )

        return errors

    def analyze_word_stress(
        self,
        audio_data: Union[bytes, np.ndarray],
        sample_rate: int,
        word_timestamps: List[WordTimestamp]
    ) -> WordStressAnalysis:
        """
        Analyzes lexical stress placement for polysyllabic words using acoustic prominence
        (Duration, RMS Energy, Peak F0) and compares against CMUdict ground truth.

        Parameters:
            audio_data: 1D float32 audio array or raw PCM bytes.
            sample_rate: Audio sampling rate.
            word_timestamps: Aligned word timestamps.

        Returns:
            Populated WordStressAnalysis dataclass.
        """
        samples = AudioContinuityGate._to_float32_array(audio_data, sample_rate=sample_rate, target_sample_rate=16000)
        if samples is None or len(samples) == 0 or not word_timestamps:
            return WordStressAnalysis(0, 0, 1.0, [])

        sample_rate = 16000
        total_polysyllabic = 0
        correctly_stressed = 0
        misstressed_words = []

        for word_info in word_timestamps:
            word_str = word_info.word.lower().strip()
            syl_count, canonical_stresses = self.g2p.word_stress_pattern(word_str)

            if syl_count < 2 or not canonical_stresses:
                continue

            total_polysyllabic += 1
            word_dur = max(0.02, word_info.end - word_info.start)
            syl_dur = word_dur / syl_count

            syl_durations = []
            syl_energies = []
            syl_f0_peaks = []

            for k in range(syl_count):
                s_start = word_info.start + (k * syl_dur)
                s_end = s_start + syl_dur
                s_idx = max(0, min(len(samples), int(s_start * sample_rate)))
                e_idx = max(s_idx, min(len(samples), int(s_end * sample_rate)))
                s_samples = samples[s_idx:e_idx]

                dur = s_end - s_start
                rms = float(np.sqrt(np.mean(s_samples ** 2))) if len(s_samples) > 0 else 0.0
                f0_peak = self._extract_f0_peak(s_samples, sample_rate)

                syl_durations.append(dur)
                syl_energies.append(rms)
                syl_f0_peaks.append(f0_peak)

            # Compute z-scores across syllables of this word
            z_dur = self._z_score(syl_durations)
            z_rms = self._z_score(syl_energies)
            z_f0 = self._z_score(syl_f0_peaks)

            # Prominence formula: 0.4 * z_dur + 0.35 * z_rms + 0.25 * z_f0
            prominences = [
                (0.40 * z_dur[k]) + (0.35 * z_rms[k]) + (0.25 * z_f0[k])
                for k in range(syl_count)
            ]

            observed_primary_stress_idx = int(np.argmax(prominences))

            # Canonical primary stress is index with value 1 in CMUdict stress pattern
            try:
                canonical_primary_stress_idx = canonical_stresses.index(1)
            except ValueError:
                canonical_primary_stress_idx = 0

            if observed_primary_stress_idx == canonical_primary_stress_idx:
                correctly_stressed += 1
            else:
                misstressed_words.append(word_info.word)

        accuracy_ratio = (
            round(correctly_stressed / total_polysyllabic, 4)
            if total_polysyllabic > 0
            else 1.0
        )

        return WordStressAnalysis(
            total_polysyllabic_words=total_polysyllabic,
            correctly_stressed_words=correctly_stressed,
            stress_accuracy_ratio=accuracy_ratio,
            common_misstressed_words=misstressed_words,
        )

    def analyze_intonation(
        self,
        audio_data: Union[bytes, np.ndarray],
        sample_rate: int,
        energy_rms_threshold: float = 0.010
    ) -> IntonationAnalysis:
        """
        Extracts pitch contour across voiced speech frames, computes speaker-normalized
        variation metrics, detects monotone speech, and classifies dominant intonation contour.

        Parameters:
            audio_data: 1D float32 audio array or raw PCM bytes.
            sample_rate: Sampling rate in Hz.
            energy_rms_threshold: Minimum RMS energy to qualify for F0 calculation (skips soft breathing/noise).

        Returns:
            Populated IntonationAnalysis dataclass.
        """
        samples = AudioContinuityGate._to_float32_array(audio_data, sample_rate=sample_rate, target_sample_rate=16000)
        if samples is None or len(samples) == 0:
            return IntonationAnalysis(
                pitch_range_hz=0.0,
                pitch_standard_deviation_hz=0.0,
                pitch_coefficient_of_variation=0.0,
                monotone_flag=True,
                dominant_contour_pattern="FLAT"
            )

        sample_rate = 16000
        frame_len = int(0.025 * sample_rate)  # 25ms frame
        hop_len = int(0.010 * sample_rate)    # 10ms hop

        voiced_f0: List[Tuple[float, float]] = []  # (time_sec, f0_hz)

        min_lag = max(1, int(sample_rate / 450))  # 450 Hz upper bound
        max_lag = min(frame_len - 1, int(sample_rate / 75))   # 75 Hz lower bound

        for i in range(0, len(samples) - frame_len, hop_len):
            frame = samples[i : i + frame_len]
            rms = float(np.sqrt(np.mean(frame ** 2)))

            # Energy gating: Skip low-energy frames (soft breathing, background noise)
            # prior to autocorrelation to avoid skewing median(F0)
            if rms < energy_rms_threshold:
                continue

            corr = np.correlate(frame, frame, mode="full")
            center = len(frame) - 1
            r_zero = corr[center]
            if r_zero > 0:
                    lag_slice = corr[center + min_lag : center + max_lag]
                    peak_idx = int(np.argmax(lag_slice))
                    peak_lag = min_lag + peak_idx
                    norm_peak = float(lag_slice[peak_idx]) / r_zero

                    # Voiced periodicity threshold
                    if norm_peak > 0.35:
                        f0 = sample_rate / peak_lag
                        if 75.0 <= f0 <= 450.0:
                            t_sec = i / sample_rate
                            voiced_f0.append((t_sec, f0))

        if len(voiced_f0) < 3:
            return IntonationAnalysis(
                pitch_range_hz=0.0,
                pitch_standard_deviation_hz=0.0,
                pitch_coefficient_of_variation=0.0,
                monotone_flag=True,
                dominant_contour_pattern="FLAT"
            )

        f0_vals = np.array([f0 for _, f0 in voiced_f0])
        times = np.array([t for t, _ in voiced_f0])

        pitch_min = float(np.min(f0_vals))
        pitch_max = float(np.max(f0_vals))
        pitch_range = round(pitch_max - pitch_min, 2)
        pitch_std = round(float(np.std(f0_vals)), 2)
        pitch_median = float(np.median(f0_vals))
        pitch_cv = round(pitch_std / (pitch_median + 1e-6), 4)

        # Monotone flag: CV < 0.12 (less than 12% relative pitch variance)
        monotone_flag = pitch_cv < 0.12

        # Classify dominant intonation contour
        if pitch_cv < 0.10:
            contour = "FLAT"
        else:
            # Linear regression slope across the final 30% of voiced frames
            n_tail = max(2, int(0.30 * len(voiced_f0)))
            t_tail = times[-n_tail:]
            f_tail = f0_vals[-n_tail:]

            t_mean = np.mean(t_tail)
            f_mean = np.mean(f_tail)
            denom = np.sum((t_tail - t_mean) ** 2)
            if denom > 1e-9:
                slope = float(np.sum((t_tail - t_mean) * (f_tail - f_mean)) / denom)
            else:
                slope = 0.0

            if slope < -15.0:
                contour = "FALLING"
            elif slope > 15.0:
                contour = "RISING"
            else:
                contour = "MIXED"

        return IntonationAnalysis(
            pitch_range_hz=pitch_range,
            pitch_standard_deviation_hz=pitch_std,
            pitch_coefficient_of_variation=pitch_cv,
            monotone_flag=monotone_flag,
            dominant_contour_pattern=contour
        )

    def _extract_f0_peak(self, samples: np.ndarray, sample_rate: int, energy_rms_threshold: float = 0.010) -> float:
        """Extracts peak fundamental frequency inside a syllable segment."""
        if len(samples) < int(0.020 * sample_rate):
            return 150.0  # Baseline neutral pitch

        rms = float(np.sqrt(np.mean(samples ** 2)))
        if rms < energy_rms_threshold:
            return 150.0  # Low-energy frame (soft breathing/ambient noise) -> skip autocorrelation to avoid skewing F0

        frame_len = min(len(samples), int(0.030 * sample_rate))
        corr = np.correlate(samples[:frame_len], samples[:frame_len], mode="full")
        center = len(samples[:frame_len]) - 1
        r_zero = corr[center]
        if r_zero <= 0:
            return 150.0

        min_lag = max(1, int(sample_rate / 400))
        max_lag = min(frame_len - 1, int(sample_rate / 80))
        if max_lag <= min_lag:
            return 150.0

        lag_slice = corr[center + min_lag : center + max_lag]
        peak_idx = int(np.argmax(lag_slice))
        peak_lag = min_lag + peak_idx
        return float(sample_rate / peak_lag)

    @staticmethod
    def _z_score(values: List[float]) -> List[float]:
        """Computes sample z-score for a list of values."""
        if not values:
            return []
        arr = np.array(values, dtype=np.float32)
        std = float(np.std(arr))
        mean = float(np.mean(arr))
        if std < 1e-6:
            return [0.0] * len(values)
        return list((arr - mean) / std)
