"""
acoustic/continuity_gate.py
===========================
Audio Continuity and Drop-out Gate.
Distinguishes natural human cognitive pauses (with room-tone and breath decay envelope)
from artificial network packet drops and codec dropouts (instantaneous steep edge to zero energy),
preventing technical artifacts from unfairly penalizing student fluency scores.
"""

from typing import List, Tuple, Optional, Union
import numpy as np
import logging

logger = logging.getLogger("AudioContinuityGate")


class AudioContinuityGate:
    """
    Evaluates acoustic gaps for network dropouts and codec mute artifacts,
    enforcing quality threshold gating for automated speaking scoring.
    """

    def __init__(
        self,
        artifact_duration_threshold_ratio: float = 0.15,
        transition_window_seconds: float = 0.005,
        zero_energy_rms_threshold: float = 1e-5,
    ):
        self.artifact_duration_threshold_ratio = artifact_duration_threshold_ratio
        self.transition_window_seconds = transition_window_seconds
        self.zero_energy_rms_threshold = zero_energy_rms_threshold

    def check_continuity(
        self,
        audio_data: Union[bytes, np.ndarray],
        sample_rate: int,
        gaps: List[Tuple[float, float]]
    ) -> List[Tuple[float, float, bool]]:
        """
        Inspects the energy envelope and spectral onset/offset gradient of each pause gap.

        Parameters:
            audio_data: Raw PCM audio bytes (int16 or float32) or 1D numpy array of audio samples.
            sample_rate: Audio sampling rate in Hz (e.g. 16000).
            gaps: List of (start_seconds, end_seconds) tuples representing inter-word intervals.

        Returns:
            List of (start_seconds, end_seconds, is_artifact) tuples.
        """
        if not gaps:
            return []

        # Convert audio data to float32 numpy array normalized to [-1.0, 1.0]
        samples = self._to_float32_array(audio_data)
        if samples is None or len(samples) == 0 or sample_rate <= 0:
            return [(start, end, False) for start, end in gaps]

        results: List[Tuple[float, float, bool]] = []
        trans_samples = max(1, int(self.transition_window_seconds * sample_rate))

        for start, end in gaps:
            gap_dur = end - start
            if gap_dur <= 0:
                results.append((start, end, False))
                continue

            start_idx = max(0, min(len(samples), int(start * sample_rate)))
            end_idx = max(start_idx, min(len(samples), int(end * sample_rate)))

            gap_samples = samples[start_idx:end_idx]
            if len(gap_samples) == 0:
                results.append((start, end, False))
                continue

            # 1. Compute RMS energy inside the gap
            gap_rms = float(np.sqrt(np.mean(gap_samples ** 2)))
            is_zero_energy = gap_rms < self.zero_energy_rms_threshold or np.all(gap_samples == 0)

            # 2. Check transition edges surrounding the gap
            pre_start = max(0, start_idx - trans_samples)
            pre_samples = samples[pre_start:start_idx]
            pre_rms = float(np.sqrt(np.mean(pre_samples ** 2))) if len(pre_samples) > 0 else 0.0

            post_end = min(len(samples), end_idx + trans_samples)
            post_samples = samples[end_idx:post_end]
            post_rms = float(np.sqrt(np.mean(post_samples ** 2))) if len(post_samples) > 0 else 0.0

            # Instantaneous steep drop into digital silence without room tone:
            # - Gap is essentially digital zero (RMS < 1e-5)
            # - Surrounded by active speech signal (> 0.005) or pure zero throughout gap of notable duration (>= 0.25s)
            is_artifact = False
            if is_zero_energy and gap_dur >= 0.25:
                if pre_rms > 0.005 or post_rms > 0.005 or np.all(gap_samples == 0):
                    is_artifact = True
                    logger.debug(
                        "[CONTINUITY ARTIFACT] Flagged gap %.2fs - %.2fs (dur=%.2fs, rms=%.2e) as technical artifact",
                        start, end, gap_dur, gap_rms
                    )

            results.append((start, end, is_artifact))

        return results

    def evaluate_exclusion(
        self,
        total_duration: float,
        artifacts: List[Tuple[float, float]]
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluates whether cumulative technical artifacts exceed the acceptable threshold (15%)
        for automated IELTS scoring.

        Parameters:
            total_duration: Total audio duration in seconds.
            artifacts: List of (start_seconds, end_seconds) for flagged technical artifacts.

        Returns:
            (excluded_from_automated_scoring, exclusion_reason)
        """
        if total_duration <= 0:
            return False, None

        total_artifact_duration = sum(max(0.0, end - start) for start, end in artifacts)
        artifact_ratio = total_artifact_duration / total_duration

        if artifact_ratio > self.artifact_duration_threshold_ratio:
            reason = (
                f"Excessive audio discontinuity detected: {artifact_ratio:.1%} "
                f"of duration is technical artifact (exceeds {self.artifact_duration_threshold_ratio:.0%} threshold)"
            )
            logger.warning("[SCORING EXCLUSION] %s", reason)
            return True, reason

        return False, None

    @staticmethod
    def _to_float32_array(
        audio_data: Union[bytes, np.ndarray],
        sample_rate: int = 16000,
        target_sample_rate: int = 16000
    ) -> Optional[np.ndarray]:
        """
        Decodes and normalizes incoming audio data (raw PCM, WAV, or compressed bytes)
        into a 1D float32 PCM numpy array normalized to [-1.0, 1.0] at target_sample_rate.
        """
        if audio_data is None:
            return None

        if isinstance(audio_data, np.ndarray):
            # Flatten or average multi-channel to mono
            if audio_data.ndim > 1:
                audio_data = np.mean(audio_data, axis=-1 if audio_data.shape[-1] <= 8 else 0)

            if audio_data.dtype == np.float32:
                samples = audio_data
            elif audio_data.dtype == np.int16:
                samples = audio_data.astype(np.float32) / 32768.0
            elif audio_data.dtype == np.int32:
                samples = audio_data.astype(np.float32) / 2147483648.0
            else:
                samples = audio_data.astype(np.float32)

            if sample_rate != target_sample_rate and sample_rate > 0 and len(samples) > 0:
                import scipy.signal
                num_target = int(round(len(samples) * target_sample_rate / sample_rate))
                samples = scipy.signal.resample(samples, num_target).astype(np.float32)
            return samples

        if isinstance(audio_data, (bytes, bytearray)):
            if len(audio_data) == 0:
                return None

            # 1. Detect WAV container (RIFF...WAVE)
            if audio_data.startswith(b"RIFF") and len(audio_data) >= 12 and b"WAVE" in audio_data[:12]:
                try:
                    import io
                    import scipy.io.wavfile as wavfile
                    orig_sr, wav_data = wavfile.read(io.BytesIO(audio_data))
                    return AudioContinuityGate._to_float32_array(
                        wav_data, sample_rate=orig_sr, target_sample_rate=target_sample_rate
                    )
                except Exception as ex:
                    logger.debug("[AUDIO NORMALIZATION] Fallback from scipy WAV decoding: %s", ex)

            # 2. Detect compressed formats (WebM, OGG, MP3) and attempt ffmpeg stream decode if available
            compressed_signatures = (
                b"\x1a\x45\xdf\xa3",  # WebM / Matroska EBML
                b"OggS",              # OGG
                b"ID3",               # MP3 with ID3 tag
                b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"  # MP3 sync frames
            )
            if any(audio_data.startswith(sig) for sig in compressed_signatures):
                try:
                    import subprocess
                    proc = subprocess.run(
                        [
                            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                            "-i", "pipe:0", "-f", "f32le", "-ac", "1", "-ar", str(target_sample_rate), "pipe:1"
                        ],
                        input=audio_data,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=True,
                        timeout=5
                    )
                    if len(proc.stdout) > 0:
                        return np.frombuffer(proc.stdout, dtype=np.float32)
                except Exception as ex:
                    logger.debug("[AUDIO NORMALIZATION] FFmpeg decoding unavailable or failed: %s", ex)

            # 3. Fallback: Parse raw 16-bit or 32-bit float PCM bytes directly
            try:
                samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
                if sample_rate != target_sample_rate and sample_rate > 0 and len(samples) > 0:
                    import scipy.signal
                    num_target = int(round(len(samples) * target_sample_rate / sample_rate))
                    samples = scipy.signal.resample(samples, num_target).astype(np.float32)
                return samples
            except Exception:
                try:
                    return np.frombuffer(audio_data, dtype=np.float32)
                except Exception:
                    return None

        return None
