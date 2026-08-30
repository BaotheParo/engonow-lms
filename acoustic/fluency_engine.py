"""
acoustic/fluency_engine.py
==========================
Acoustic Fluency Engine & Two-Layer Disfluency Analyzer for IELTS Speaking Assessment.
Extracts speech rate, articulation rate, phonation ratio, and pause distributions,
reconciling Faster-Whisper transcripts with acoustic feature detectors.
"""

from typing import List, Dict, Tuple, Optional, Set, Union
import re
import numpy as np
import logging

from acoustic.models import WordTimestamp, PauseAnalysis, FluencyResult
from acoustic.continuity_gate import AudioContinuityGate

logger = logging.getLogger("FluencyEngine")


class FluencyEngine:
    """
    Production-grade Speech Fluency Engine computing IELTS acoustic metrics,
    pause classifications, and two-layer filler disfluency reconciliation.
    """

    STANDARD_FILLERS: Set[str] = {
        "um", "umm", "uh", "uhh", "er", "err", "ah", "ahh",
        "like", "you know", "you_know", "you-know", "well"
    }

    FILLER_NORMALIZATION: Dict[str, str] = {
        "um": "um",
        "umm": "um",
        "uh": "uh",
        "uhh": "uh",
        "er": "er",
        "err": "er",
        "ah": "ah",
        "ahh": "ah",
        "like": "like",
        "you know": "you know",
        "you_know": "you know",
        "you-know": "you know",
        "well": "well",
    }

    def __init__(self, continuity_gate: Optional[AudioContinuityGate] = None):
        self.continuity_gate = continuity_gate or AudioContinuityGate()

    def detect_acoustic_fillers(
        self,
        audio_data: Union[bytes, np.ndarray],
        sample_rate: int,
        word_timestamps: List[WordTimestamp]
    ) -> List[Tuple[float, float, str]]:
        """
        Layer 2: Acoustic Filler Detector.
        Identifies audio intervals with stationary pitch and low spectral variance
        typical of filled pauses ('uh', 'um') that may have been suppressed by ASR.

        Parameters:
            audio_data: Raw audio bytes or numpy array.
            sample_rate: Audio sampling rate in Hz.
            word_timestamps: Aligned word timestamps from transcript.

        Returns:
            List of (start_seconds, end_seconds, filler_type) tuples.
        """
        samples = AudioContinuityGate._to_float32_array(audio_data)
        if samples is None or len(samples) == 0 or sample_rate <= 0 or not word_timestamps:
            return []

        acoustic_fillers: List[Tuple[float, float, str]] = []

        # Inspect gaps between consecutive words
        for i in range(len(word_timestamps) - 1):
            gap_start = word_timestamps[i].end
            gap_end = word_timestamps[i + 1].start
            gap_dur = gap_end - gap_start

            # Typical filler duration is between 0.30s and 1.0s
            if 0.30 <= gap_dur <= 1.0:
                s_idx = max(0, min(len(samples), int(gap_start * sample_rate)))
                e_idx = max(s_idx, min(len(samples), int(gap_end * sample_rate)))
                gap_samples = samples[s_idx:e_idx]

                if len(gap_samples) < int(0.20 * sample_rate):
                    continue

                rms = float(np.sqrt(np.mean(gap_samples ** 2)))
                # Energy must be above silence floor (> 0.005)
                if rms > 0.005:
                    # Periodicity check via normalized autocorrelation
                    # Pitch range for human voice: 80 Hz - 350 Hz -> sample lag range
                    min_lag = max(1, int(sample_rate / 350))
                    max_lag = min(len(gap_samples) // 2, int(sample_rate / 80))

                    if max_lag > min_lag and len(gap_samples) > max_lag * 2:
                        corr = np.correlate(gap_samples, gap_samples, mode="full")
                        center = len(gap_samples) - 1
                        r_zero = corr[center]
                        if r_zero > 0:
                            lag_slice = corr[center + min_lag : center + max_lag]
                            max_corr_peak = float(np.max(lag_slice)) / r_zero

                            # Voiced vocalic sounds ("uh", "um") have strong periodic autocorrelation (> 0.35)
                            # White noise / unvoiced pauses have max_corr_peak < 0.15
                            if max_corr_peak > 0.35:
                                # Check energy stability (low coefficient of variation)
                                frame_size = int(0.05 * sample_rate)
                                if frame_size > 0 and len(gap_samples) >= frame_size * 2:
                                    frames = [
                                        gap_samples[j : j + frame_size]
                                        for j in range(0, len(gap_samples) - frame_size, frame_size // 2)
                                    ]
                                    frame_energies = [np.sqrt(np.mean(f ** 2)) for f in frames if len(f) > 0]
                                    energy_std = float(np.std(frame_energies)) if frame_energies else 1.0
                                    energy_mean = float(np.mean(frame_energies)) if frame_energies else 1.0
                                    cv = energy_std / (energy_mean + 1e-6)

                                    if cv < 0.50:
                                        acoustic_fillers.append((gap_start, gap_end, "uh"))
                                        logger.debug(
                                            "[ACOUSTIC FILLER] Detected voiced filler (r_peak=%.2f, cv=%.2f) at %.2fs - %.2fs (dur=%.2fs)",
                                            max_corr_peak, cv, gap_start, gap_end, gap_dur
                                        )

        return acoustic_fillers

    def analyze_fluency(
        self,
        audio_data: Union[bytes, np.ndarray],
        sample_rate: int,
        word_timestamps: List[WordTimestamp],
        total_duration_seconds: float
    ) -> FluencyResult:
        """
        Executes end-to-end fluency feature extraction, pause dynamics classification,
        two-layer filler reconciliation, and continuity gating.

        Parameters:
            audio_data: Raw PCM audio bytes or numpy array.
            sample_rate: Audio sampling rate (e.g. 16000).
            word_timestamps: Word-level alignment timestamps.
            total_duration_seconds: Total response duration in seconds.

        Returns:
            Populated FluencyResult dataclass.
        """
        pause_analysis = PauseAnalysis()
        detected_artifacts: List[Tuple[float, float]] = []
        cognitive_pause_durations: List[float] = []

        # Ensure audio bytes are decoded into 1D float32 PCM array normalized to 16,000 Hz
        norm_audio = AudioContinuityGate._to_float32_array(audio_data, sample_rate=sample_rate, target_sample_rate=16000)
        if norm_audio is not None and len(norm_audio) > 0:
            audio_data = norm_audio
            sample_rate = 16000

        if total_duration_seconds <= 0:
            total_duration_seconds = word_timestamps[-1].end if word_timestamps else 0.0

        word_count = len(word_timestamps)

        # ----------------------------------------------------------------------
        # 1. Layer 1: Transcript-based Filler Detection
        # ----------------------------------------------------------------------
        transcript_filler_intervals: List[Tuple[float, float, str]] = []
        i = 0
        while i < len(word_timestamps):
            w_curr = word_timestamps[i]
            w_curr_clean = re.sub(r"[^\w\s]", "", w_curr.word.lower().strip())

            # Check 2-word filler: "you know"
            if i + 1 < len(word_timestamps):
                w_next = word_timestamps[i + 1]
                w_next_clean = re.sub(r"[^\w\s]", "", w_next.word.lower().strip())
                two_word = f"{w_curr_clean} {w_next_clean}"
                if two_word == "you know" and (w_next.start - w_curr.end) < 0.30:
                    norm_type = "you know"
                    transcript_filler_intervals.append((w_curr.start, w_next.end, norm_type))
                    pause_analysis.filled_pause_count += 1
                    pause_analysis.filled_pause_counts_by_type[norm_type] = (
                        pause_analysis.filled_pause_counts_by_type.get(norm_type, 0) + 1
                    )
                    i += 2
                    continue

            # Check single-word filler
            if w_curr_clean in self.STANDARD_FILLERS:
                norm_type = self.FILLER_NORMALIZATION.get(w_curr_clean, w_curr_clean)
                transcript_filler_intervals.append((w_curr.start, w_curr.end, norm_type))
                pause_analysis.filled_pause_count += 1
                pause_analysis.filled_pause_counts_by_type[norm_type] = (
                    pause_analysis.filled_pause_counts_by_type.get(norm_type, 0) + 1
                )

            i += 1

        # ----------------------------------------------------------------------
        # 2. Layer 2: Acoustic-detected Filler Detection & Reconciliation
        # ----------------------------------------------------------------------
        acoustic_fillers = self.detect_acoustic_fillers(audio_data, sample_rate, word_timestamps)
        for a_start, a_end, a_type in acoustic_fillers:
            # Check overlap with existing transcript fillers
            overlaps = any(
                not (a_end <= t_start or a_start >= t_end)
                for t_start, t_end, _ in transcript_filler_intervals
            )
            if not overlaps:
                pause_analysis.filled_pause_count += 1
                pause_analysis.filled_pause_counts_by_type[a_type] = (
                    pause_analysis.filled_pause_counts_by_type.get(a_type, 0) + 1
                )
                transcript_filler_intervals.append((a_start, a_end, a_type))

        # ----------------------------------------------------------------------
        # 3. Inter-Word Pause Classification & Continuity Analysis
        # ----------------------------------------------------------------------
        raw_gaps: List[Tuple[float, float]] = []
        for j in range(len(word_timestamps) - 1):
            gap_start = word_timestamps[j].end
            gap_end = word_timestamps[j + 1].start
            gap_dur = gap_end - gap_start
            if gap_dur >= 0.25:
                raw_gaps.append((gap_start, gap_end))

        # Evaluate audio continuity across detected gaps
        continuity_evals = self.continuity_gate.check_continuity(audio_data, sample_rate, raw_gaps)
        gap_artifact_map = {(start, end): is_art for start, end, is_art in continuity_evals}

        total_pause_duration = 0.0

        for start, end in raw_gaps:
            gap_dur = end - start
            is_artifact = gap_artifact_map.get((start, end), False)

            # Check if this gap contains an acoustic filler
            is_acoustic_filler = any(
                not (end <= f_start or start >= f_end)
                for f_start, f_end, _ in acoustic_fillers
            )

            if is_acoustic_filler:
                # Accounted for in filled pause metrics
                total_pause_duration += gap_dur
                continue

            if is_artifact:
                # Technical network/codec drop-out: exclude from silent cognitive pause penalty
                pause_analysis.possible_technical_artifact_count += 1
                detected_artifacts.append((start, end))
                # Add to total pause duration to avoid artificially inflating articulation rate
                total_pause_duration += gap_dur
            else:
                # Natural human pause
                if 0.25 <= gap_dur <= 0.75:
                    # Micro-pause (normal cognitive phrasing, not penalized)
                    pause_analysis.silent_micro_pause_count += 1
                    total_pause_duration += gap_dur
                elif gap_dur > 0.75:
                    # Cognitive pause (fluency hesitation penalty)
                    pause_analysis.silent_cognitive_pause_count += 1
                    cognitive_pause_durations.append(gap_dur)
                    total_pause_duration += gap_dur

        # Compute average cognitive pause duration
        if cognitive_pause_durations:
            pause_analysis.average_cognitive_pause_duration_seconds = round(
                float(np.mean(cognitive_pause_durations)), 4
            )
        else:
            pause_analysis.average_cognitive_pause_duration_seconds = 0.0

        pause_analysis.total_pause_duration_seconds = round(total_pause_duration, 4)

        # ----------------------------------------------------------------------
        # 4. Speech Rate, Articulation Rate & Phonation Calculations
        # ----------------------------------------------------------------------
        if word_count == 0:
            # Edge case: No words detected (pure silence or unvoiced noise)
            speaking_rate_wpm = 0.0
            articulation_rate_wpm = 0.0
            phonation_ratio = 0.0
            phonation_time = 0.0
        else:
            phonation_time = max(0.0, total_duration_seconds - total_pause_duration)
            phonation_time = round(phonation_time, 4)

            duration_minutes = total_duration_seconds / 60.0 if total_duration_seconds > 0 else 0.0
            phonation_minutes = phonation_time / 60.0 if phonation_time > 0 else 0.0

            speaking_rate_wpm = (
                round(word_count / duration_minutes, 2) if duration_minutes > 0 else 0.0
            )
            articulation_rate_wpm = (
                round(word_count / phonation_minutes, 2) if phonation_minutes > 0 else 0.0
            )
            phonation_ratio = (
                round(phonation_time / total_duration_seconds, 4) if total_duration_seconds > 0 else 0.0
            )

        # ----------------------------------------------------------------------
        # 5. Continuity Threshold Exclusion Gate (15% Artifact Rule)
        # ----------------------------------------------------------------------
        excluded, exclusion_reason = self.continuity_gate.evaluate_exclusion(
            total_duration_seconds, detected_artifacts
        )

        return FluencyResult(
            speaking_rate_wpm=speaking_rate_wpm,
            articulation_rate_wpm=articulation_rate_wpm,
            phonation_ratio=phonation_ratio,
            total_duration_seconds=round(total_duration_seconds, 4),
            phonation_time_seconds=phonation_time,
            word_count=word_count,
            pause_analysis=pause_analysis,
            excluded_from_automated_scoring=excluded,
            exclusion_reason=exclusion_reason
        )
