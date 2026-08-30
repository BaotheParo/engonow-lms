"""
acoustic/acoustic_orchestrator.py
=================================
Unified Acoustic Orchestration Engine combining Fluency Analysis (Phase 4.2),
Audio Continuity Gating, Phonetic Error Diagnostics, Lexical Stress Accuracy,
and Pitch Intonation Contour Extraction (Phase 4.3).
"""

from typing import List, Optional, Union, Dict, Any
from dataclasses import asdict
import numpy as np
import logging

from acoustic.models import WordTimestamp, FluencyResult
from acoustic.phonetic_models import (
    PhonemeError,
    WordStressAnalysis,
    IntonationAnalysis,
    FullAcousticAnalysisResult,
)
from acoustic.fluency_engine import FluencyEngine
from acoustic.pronunciation_engine import PronunciationEngine
from acoustic.continuity_gate import AudioContinuityGate

logger = logging.getLogger("AcousticOrchestrator")


class AcousticOrchestrator:
    """
    Primary entry point for the ENGONOW AI Speaking Acoustic Engine.
    Executes the full multimodal acoustic diagnostics pipeline over candidate speech audio.
    """

    def __init__(
        self,
        fluency_engine: Optional[FluencyEngine] = None,
        pronunciation_engine: Optional[PronunciationEngine] = None,
    ):
        self.fluency_engine = fluency_engine or FluencyEngine()
        self.pronunciation_engine = pronunciation_engine or PronunciationEngine()

    def process_speaking_audio(
        self,
        audio_data: Union[bytes, np.ndarray],
        sample_rate: int,
        word_timestamps: List[WordTimestamp],
        total_duration: float = 0.0
    ) -> FullAcousticAnalysisResult:
        """
        Processes candidate speaking audio and aligned transcript tokens, returning
        a unified diagnostic assessment covering Fluency, Pronunciation (GOP),
        Syllable Stress, and Intonation.

        Parameters:
            audio_data: Raw PCM/WAV/compressed audio bytes or float32 numpy array.
            sample_rate: Sampling rate of the incoming audio in Hz.
            word_timestamps: Aligned WordTimestamp objects from ASR aligner.
            total_duration: Optional total audio duration in seconds.

        Returns:
            FullAcousticAnalysisResult object containing complete metrics.
        """
        # 1. Normalize audio to 16kHz float32 PCM
        samples = AudioContinuityGate._to_float32_array(
            audio_data, sample_rate=sample_rate, target_sample_rate=16000
        )
        norm_sr = 16000

        if samples is None:
            samples = np.zeros(0, dtype=np.float32)

        if total_duration <= 0.0:
            if len(samples) > 0:
                total_duration = len(samples) / norm_sr
            elif word_timestamps:
                total_duration = word_timestamps[-1].end
            else:
                total_duration = 0.0

        # 2. Phase 4.2: Fluency & Audio Continuity Gating
        fluency_result: FluencyResult = self.fluency_engine.analyze_fluency(
            audio_data=samples,
            sample_rate=norm_sr,
            word_timestamps=word_timestamps,
            total_duration_seconds=total_duration
        )

        # 3. Phase 4.3: Phoneme Diagnostics & Goodness-of-Pronunciation (GOP)
        phoneme_errors: List[PhonemeError] = self.pronunciation_engine.evaluate_phonemes(
            audio_data=samples,
            sample_rate=norm_sr,
            word_timestamps=word_timestamps
        )

        # 4. Phase 4.3: Polysyllabic Lexical Stress Analysis
        word_stress: WordStressAnalysis = self.pronunciation_engine.analyze_word_stress(
            audio_data=samples,
            sample_rate=norm_sr,
            word_timestamps=word_timestamps
        )

        # 5. Phase 4.3: Pitch Contour & Intonation Expressiveness Analysis
        intonation: IntonationAnalysis = self.pronunciation_engine.analyze_intonation(
            audio_data=samples,
            sample_rate=norm_sr
        )

        pause_analysis_dict = asdict(fluency_result.pause_analysis)

        return FullAcousticAnalysisResult(
            speaking_rate_wpm=fluency_result.speaking_rate_wpm,
            articulation_rate_wpm=fluency_result.articulation_rate_wpm,
            phonation_ratio=fluency_result.phonation_ratio,
            total_duration_seconds=fluency_result.total_duration_seconds,
            phonation_time_seconds=fluency_result.phonation_time_seconds,
            word_count=fluency_result.word_count,
            pause_analysis=pause_analysis_dict,
            phoneme_errors=phoneme_errors,
            word_stress_analysis=word_stress,
            intonation_analysis=intonation,
            excluded_from_automated_scoring=fluency_result.excluded_from_automated_scoring,
            exclusion_reason=fluency_result.exclusion_reason
        )
