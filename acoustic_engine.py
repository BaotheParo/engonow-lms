import math
import statistics
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple


@dataclass
class WordToken:
    word: str
    start: float
    end: float
    probability: float
    logprob: float
    duration: float
    gap_before: float
    gap_class: str
    confidence_source: str = "WORD_PROBABILITY"


@dataclass
class WhisperSegment:
    segment_id: int
    start: float
    end: float
    text: str
    avg_logprob: float
    no_speech_prob: float
    compression_ratio: float


@dataclass
class ParsedWhisperOutput:
    words: List[WordToken]
    segments: List[WhisperSegment]
    total_duration: float
    total_words: int
    raw_transcript: str
    logprob_fallback_count: int = 0


@dataclass
class FluencyFeatures:
    speech_rate_wpm: float
    articulation_rate_wpm: float
    phonation_ratio: float
    silent_ratio: float
    mean_pause_duration: float
    long_pause_ratio: float
    pause_freq_per_min: float
    hesitation_density: float
    max_fluent_streak: int

    s_speech_rate: float
    s_articulation_rate: float
    s_pause_ratio: float
    s_hesitation: float
    s_streak: float

    fc_raw: float
    fc_band: int


@dataclass
class PronunciationFeatures:
    fw_baseline_logprob: float
    calibration_shift: float
    fw_sample_count: int

    mean_cal_logprob: float
    p5_cal_logprob: float
    logprob_std: float
    content_mean_cal_logprob: float

    severe_error_ratio: float
    severe_error_count: int

    high_noise_segment_ratio: float

    s_mean: float
    s_severe: float
    s_consistency: float
    s_tail: float

    pr_raw: float
    pr_band: int
    calibration_reliable: bool
    genuine_confidence_word_count: int = 0
    genuine_confidence_coverage: float = 0.0


@dataclass
class AcousticScore:
    fc_score: int
    pr_score: int
    fc_raw: float
    pr_raw: float
    fluency: FluencyFeatures
    pronunciation: PronunciationFeatures
    diagnostics: Dict
    warnings: List[str]


#  Pause Classification Thresholds
TAU_MICRO      = 0.15
TAU_NATURAL    = 0.50
TAU_HESITATION = 2.00

#  Function Word Set (for speaker normalisation)
FUNCTION_WORDS = frozenset({
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should',
    'could', 'may', 'might', 'can', 'i', 'you', 'he', 'she', 'we', 'they',
    'it', 'this', 'that', 'these', 'those', 'my', 'your', 'his', 'her',
    'our', 'their', 'its', 'not', 'so', 'as', 'if', 'all', 'me', 'him',
    'us', 'them', 'been', 'being', 'am', 'its', 'up', 'out', 'about'
})

#  High-Frequency Tier B Content Words (top ~300)
TIER_B_HIGH_FREQ = frozenset({
    'think', 'know', 'work', 'time', 'year', 'way', 'day', 'people',
    'new', 'good', 'first', 'last', 'old', 'place', 'make', 'life',
    'come', 'take', 'give', 'get', 'go', 'see', 'say', 'tell', 'ask',
    'want', 'need', 'like', 'love', 'live', 'feel', 'become', 'show',
    'seem', 'put', 'use', 'help', 'keep', 'let', 'begin', 'start',
    'try', 'mean', 'change', 'turn', 'move', 'play', 'run', 'hold',
    'school', 'home', 'family', 'friend', 'job', 'money', 'city',
    'country', 'world', 'health', 'food', 'water', 'air', 'learn',
    'study', 'education', 'important', 'different', 'social', 'local',
    'public', 'national', 'general', 'personal', 'human', 'large',
    'small', 'long', 'high', 'low', 'young', 'able', 'real', 'free',
    'true', 'early', 'late', 'hard', 'easy', 'able', 'right', 'left',
    'because', 'when', 'where', 'which', 'who', 'what', 'how', 'why',
    'also', 'then', 'than', 'very', 'more', 'most', 'some', 'any',
    'many', 'much', 'such', 'even', 'still', 'back', 'just', 'only',
    'well', 'both', 'each', 'every', 'other', 'another', 'same'
})

#  Filler Token Patterns
FILLER_WORDS = frozenset({'um', 'uh', 'er', 'ah', 'hmm', 'hm', 'ehm', 'umm', 'uhh', 'err'})
FILLER_PHRASES = ['you know', 'i mean', 'kind of', 'sort of']
# Note: 'like' requires context check  handled separately in FluencyEngine

#  Speaker Normalisation Constants
EXPECTED_FW_BASELINE   = -0.18
MIN_FW_SAMPLES_FOR_CAL = 5
MAX_CAL_SHIFT          = 0.60

#  Severe Error Thresholds (by frequency tier)
SEVERE_THRESHOLD_TIER_A = -0.80
SEVERE_THRESHOLD_TIER_B = -1.10
SEVERE_THRESHOLD_TIER_C = -1.60

# Groq may include word probability without calculating it. Values at or below
# this sentinel are treated as missing data; genuine low confidence above it is
# preserved as pronunciation evidence.
INVALID_WORD_PROBABILITY_MAX = 0.001
HIGH_FALLBACK_RATE_THRESHOLD = 0.20
GENUINE_CONFIDENCE_SOURCES = frozenset({"WORD_PROBABILITY", "WORD_LOGPROB"})


def _normalize_word(word: str) -> str:
    """Normalize only for lexical comparisons; never mutate WordToken.word."""
    return word.lower().strip().strip("'.,!?-")


def is_nonlexical_filler(word: str) -> bool:
    """Return whether a token is safe to annotate as a filler in the text track."""
    return _normalize_word(word) in FILLER_WORDS


def parse_whisper_output(whisper_response: dict) -> ParsedWhisperOutput:
    raw_words = whisper_response.get("words") or whisper_response.get("word_timestamps")
    if not raw_words:
        raise ValueError(
            "Whisper response is missing a non-empty 'words' or "
            "'word_timestamps' array."
        )

    segments_raw = whisper_response.get("segments") or []
    parsed_segments = []
    for entry in segments_raw:
        parsed_segments.append({
            "start": float(entry.get("start", 0.0)),
            "end": float(entry.get("end", 0.0)),
            "avg_logprob": float(entry.get("avg_logprob", -0.5))
        })

    words = []
    logprob_fallback_count = 0
    for index, entry in enumerate(raw_words):
        word = str(entry.get("word", ""))
        start = float(entry.get("start", 0.0))
        end = float(entry.get("end", 0.0))
        duration = end - start

        # Preserve genuine low confidence, but reject Groq's zero-like sentinel.
        try:
            candidate_probability = float(entry.get("probability"))
        except (TypeError, ValueError):
            candidate_probability = None
        probability_is_valid = (
            candidate_probability is not None
            and math.isfinite(candidate_probability)
            and INVALID_WORD_PROBABILITY_MAX < candidate_probability <= 1.0
        )
        logprob_is_valid = False

        if probability_is_valid:
            probability = candidate_probability
            logprob = math.log(probability + 1e-9)
            confidence_source = "WORD_PROBABILITY"
        else:
            try:
                candidate_logprob = float(entry.get("logprob"))
            except (TypeError, ValueError):
                candidate_logprob = None
            logprob_is_valid = (
                candidate_logprob is not None
                and math.isfinite(candidate_logprob)
            )

        if not probability_is_valid and logprob_is_valid:
            logprob = candidate_logprob
            probability = math.exp(logprob)
            confidence_source = "WORD_LOGPROB"
        elif not probability_is_valid:
            # Map word to parent segment
            matched_logprob = None
            for seg in parsed_segments:
                if seg["start"] - 0.02 <= start <= seg["end"] + 0.02:
                    matched_logprob = seg["avg_logprob"]
                    break
            if matched_logprob is None or not math.isfinite(matched_logprob):
                matched_logprob = parsed_segments[-1]["avg_logprob"] if parsed_segments else -0.5
            if not math.isfinite(matched_logprob):
                matched_logprob = -0.5
            
            logprob = matched_logprob
            probability = math.exp(logprob)
            logprob_fallback_count += 1
            confidence_source = (
                "SEGMENT_FALLBACK" if parsed_segments else "DEFAULT_FALLBACK"
            )

        if index == 0:
            gap_before = 0.0
            gap_class = "NONE"
        else:
            gap_before = start - words[-1].end
            if gap_before < TAU_MICRO:
                gap_class = "MICRO"
            elif gap_before < TAU_NATURAL:
                gap_class = "NATURAL"
            elif gap_before < TAU_HESITATION:
                gap_class = "HESITATION"
            else:
                gap_class = "EXTENDED"

        words.append(WordToken(
            word=word,
            start=start,
            end=end,
            probability=probability,
            logprob=logprob,
            duration=duration,
            gap_before=gap_before,
            gap_class=gap_class,
            confidence_source=confidence_source,
        ))

    segments = [
        WhisperSegment(
            segment_id=int(entry.get("id", 0)),
            start=float(entry.get("start", 0.0)),
            end=float(entry.get("end", 0.0)),
            text=str(entry.get("text", "")),
            avg_logprob=float(entry.get("avg_logprob", -0.5)),
            no_speech_prob=float(entry.get("no_speech_prob", 0.05)),
            compression_ratio=float(entry.get("compression_ratio", 1.5)),
        )
        for entry in (whisper_response.get("segments") or [])
    ]

    total_duration = words[-1].end - words[0].start if words else 0.0
    raw_transcript = " ".join(word.word for word in words)

    return ParsedWhisperOutput(
        words=words,
        segments=segments,
        total_duration=total_duration,
        total_words=len(words),
        raw_transcript=raw_transcript,
        logprob_fallback_count=logprob_fallback_count,
    )


def _norm_speech_rate(sr: float) -> float:
    if sr < 60:
        score = 0.0
    elif sr < 95:
        score = (sr - 60) / 35 * 0.25
    elif sr < 125:
        score = 0.25 + (sr - 95) / 30 * 0.25
    elif sr < 155:
        score = 0.50 + (sr - 125) / 30 * 0.30
    elif sr < 185:
        score = 0.80 + (sr - 155) / 30 * 0.15
    elif sr < 210:
        score = 0.95 + (sr - 185) / 25 * 0.05
    else:
        score = max(0.75, 1.00 - (sr - 210) / 80)
    return max(0.0, min(1.0, score))


def _norm_articulation_rate(ar: float) -> float:
    if ar < 80:
        score = 0.0
    elif ar < 130:
        score = (ar - 80) / 50 * 0.40
    elif ar < 180:
        score = 0.40 + (ar - 130) / 50 * 0.35
    elif ar < 220:
        score = 0.75 + (ar - 180) / 40 * 0.20
    else:
        score = min(1.0, 0.95 + (ar - 220) / 100 * 0.05)
    return max(0.0, min(1.0, score))


def _norm_pause_ratio(silent_ratio: float, long_pause_ratio: float) -> float:
    if silent_ratio > 0.55:
        sr_sub = 0.0
    elif silent_ratio > 0.42:
        sr_sub = (0.55 - silent_ratio) / 0.13 * 0.20
    elif silent_ratio > 0.30:
        sr_sub = 0.20 + (0.42 - silent_ratio) / 0.12 * 0.25
    elif silent_ratio > 0.20:
        sr_sub = 0.45 + (0.30 - silent_ratio) / 0.10 * 0.25
    elif silent_ratio > 0.12:
        sr_sub = 0.70 + (0.20 - silent_ratio) / 0.08 * 0.20
    else:
        sr_sub = min(1.0, 0.90 + (0.12 - silent_ratio) / 0.12 * 0.10)

    if long_pause_ratio > 0.25:
        lp_penalty = 0.30
    elif long_pause_ratio > 0.12:
        lp_penalty = 0.20
    elif long_pause_ratio > 0.06:
        lp_penalty = 0.10
    elif long_pause_ratio > 0.02:
        lp_penalty = 0.05
    else:
        lp_penalty = 0.0

    return max(0.0, min(1.0, sr_sub - lp_penalty))


def _norm_hesitation_density(hd: float) -> float:
    if hd > 0.15:
        score = 0.0
    elif hd > 0.10:
        score = (0.15 - hd) / 0.05 * 0.20
    elif hd > 0.07:
        score = 0.20 + (0.10 - hd) / 0.03 * 0.25
    elif hd > 0.04:
        score = 0.45 + (0.07 - hd) / 0.03 * 0.25
    elif hd > 0.02:
        score = 0.70 + (0.04 - hd) / 0.02 * 0.20
    elif hd > 0.005:
        score = 0.90 + (0.02 - hd) / 0.015 * 0.08
    else:
        score = 0.98
    return max(0.0, min(1.0, score))


def _norm_max_fluent_streak(mfs: int) -> float:
    if mfs < 0:
        score = 0.0
    elif mfs < 40:
        score = mfs / 40
    else:
        score = 1.0
    return max(0.0, min(1.0, score))


def _count_fillers(words: List[WordToken]) -> int:
    normalized_words = [_normalize_word(word.word) for word in words]
    filler_count = 0

    for index, normalized_word in enumerate(normalized_words):
        if normalized_word in FILLER_WORDS:
            filler_count += 1

        if index < len(normalized_words) - 1:
            pair = f"{normalized_word} {normalized_words[index + 1]}"
            if pair in FILLER_PHRASES:
                filler_count += 1

        if normalized_word == "like":
            previous_word = normalized_words[index - 1] if index > 0 else ""
            next_word = normalized_words[index + 1] if index < len(normalized_words) - 1 else ""
            if (
                previous_word not in {'feels', 'feel', 'felt', 'sounds', 'looks', 'seems', 'appears'}
                and next_word != "to"
            ):
                filler_count += 1

    return filler_count


def _fc_raw_to_band(fc_raw: float) -> int:
    if fc_raw < 0.10:
        return 1
    if fc_raw < 0.20:
        return 2
    if fc_raw < 0.25:
        return 3
    if fc_raw < 0.35:
        return 4
    if fc_raw < 0.45:
        return 5
    if fc_raw < 0.57:
        return 6
    if fc_raw < 0.70:
        return 7
    if fc_raw < 0.84:
        return 8
    return 9


def compute_fluency_features(parsed: ParsedWhisperOutput) -> FluencyFeatures:
    if parsed.total_words < 3 or parsed.total_duration < 1.0:
        return FluencyFeatures(
            speech_rate_wpm=0.0,
            articulation_rate_wpm=0.0,
            phonation_ratio=0.0,
            silent_ratio=0.0,
            mean_pause_duration=0.0,
            long_pause_ratio=0.0,
            pause_freq_per_min=0.0,
            hesitation_density=0.0,
            max_fluent_streak=0,
            s_speech_rate=0.0,
            s_articulation_rate=0.0,
            s_pause_ratio=0.0,
            s_hesitation=0.0,
            s_streak=0.0,
            fc_raw=0.0,
            fc_band=1,
        )

    phonated_time = sum(word.duration for word in parsed.words)
    significant_gaps = [
        word.gap_before
        for index, word in enumerate(parsed.words)
        if index > 0 and word.gap_before >= TAU_MICRO
    ]
    significant_pause_time = sum(significant_gaps)
    extended_pauses = sum(gap >= TAU_HESITATION for gap in significant_gaps)
    total_significant_pauses = len(significant_gaps)

    silent_ratio = significant_pause_time / parsed.total_duration
    mean_pause_duration = (
        statistics.mean(significant_gaps) if significant_gaps else 0.0
    )
    long_pause_ratio = (
        extended_pauses / total_significant_pauses
        if total_significant_pauses
        else 0.0
    )
    duration_minutes = parsed.total_duration / 60
    pause_freq_per_min = total_significant_pauses / duration_minutes
    speech_rate_wpm = parsed.total_words / duration_minutes
    articulation_rate_wpm = (
        parsed.total_words / (phonated_time / 60) if phonated_time > 0 else 0.0
    )
    phonation_ratio = phonated_time / parsed.total_duration
    hesitation_density = _count_fillers(parsed.words) / parsed.total_words

    current_streak = 0
    max_fluent_streak = 0
    for index, word in enumerate(parsed.words):
        if index > 0 and word.gap_before >= TAU_HESITATION:
            max_fluent_streak = max(max_fluent_streak, current_streak)
            current_streak = 1
        else:
            current_streak += 1
    max_fluent_streak = max(max_fluent_streak, current_streak)

    s_speech_rate = _norm_speech_rate(speech_rate_wpm)
    s_articulation_rate = _norm_articulation_rate(articulation_rate_wpm)
    s_pause_ratio = _norm_pause_ratio(silent_ratio, long_pause_ratio)
    s_hesitation = _norm_hesitation_density(hesitation_density)
    s_streak = _norm_max_fluent_streak(max_fluent_streak)

    fc_raw = (
        0.28 * s_speech_rate
        + 0.25 * s_pause_ratio
        + 0.22 * s_articulation_rate
        + 0.15 * s_hesitation
        + 0.10 * s_streak
    )

    fc_band = _fc_raw_to_band(fc_raw)

    return FluencyFeatures(
        speech_rate_wpm=speech_rate_wpm,
        articulation_rate_wpm=articulation_rate_wpm,
        phonation_ratio=phonation_ratio,
        silent_ratio=silent_ratio,
        mean_pause_duration=mean_pause_duration,
        long_pause_ratio=long_pause_ratio,
        pause_freq_per_min=pause_freq_per_min,
        hesitation_density=hesitation_density,
        max_fluent_streak=max_fluent_streak,
        s_speech_rate=s_speech_rate,
        s_articulation_rate=s_articulation_rate,
        s_pause_ratio=s_pause_ratio,
        s_hesitation=s_hesitation,
        s_streak=s_streak,
        fc_raw=fc_raw,
        fc_band=fc_band,
    )


def _compute_calibration_shift(words: List[WordToken]) -> Tuple[float, float, int]:
    """
    Returns (calibration_shift, fw_baseline_logprob, fw_sample_count).
    calibration_shift = 0.0 if insufficient function word samples.
    """
    fw_words = [
        word
        for word in words
        if (
            word.confidence_source in GENUINE_CONFIDENCE_SOURCES
            and _normalize_word(word.word) in FUNCTION_WORDS
        )
    ]
    fw_sample_count = len(fw_words)
    if fw_sample_count < MIN_FW_SAMPLES_FOR_CAL:
        return (0.0, 0.0, fw_sample_count)

    fw_baseline = statistics.mean([word.logprob for word in fw_words])
    shift = EXPECTED_FW_BASELINE - fw_baseline
    shift = max(-MAX_CAL_SHIFT, min(MAX_CAL_SHIFT, shift))
    return (shift, fw_baseline, fw_sample_count)


def _is_severe_error(word: str, calibrated_logprob: float) -> bool:
    """
    Returns True if the calibrated logprob falls below the tier-appropriate threshold.
    """
    w = _normalize_word(word)
    if w in FUNCTION_WORDS:
        threshold = SEVERE_THRESHOLD_TIER_A
    elif w in TIER_B_HIGH_FREQ:
        threshold = SEVERE_THRESHOLD_TIER_B
    else:
        threshold = SEVERE_THRESHOLD_TIER_C
    return calibrated_logprob < threshold


def _norm_pr_mean(mean_cal_lp: float) -> float:
    """Maps calibrated mean logprob [2.0, 0.0] to [0.0, 1.0]."""
    return max(0.0, min(1.0, (mean_cal_lp + 2.0) / 2.0))


def _norm_pr_severe(severe_ratio: float) -> float:
    """Maps severe error ratio [0.0, 1.0] to quality score [0.0, 1.0] (inverted)."""
    if severe_ratio > 0.30:
        score = 0.0
    elif severe_ratio > 0.20:
        score = (0.30 - severe_ratio) / 0.10 * 0.20
    elif severe_ratio > 0.12:
        score = 0.20 + (0.20 - severe_ratio) / 0.08 * 0.25
    elif severe_ratio > 0.06:
        score = 0.45 + (0.12 - severe_ratio) / 0.06 * 0.25
    elif severe_ratio > 0.02:
        score = 0.70 + (0.06 - severe_ratio) / 0.04 * 0.20
    elif severe_ratio > 0.005:
        score = 0.90 + (0.02 - severe_ratio) / 0.015 * 0.08
    else:
        score = 0.98
    return max(0.0, min(1.0, score))


def _norm_pr_consistency(lp_std: float) -> float:
    """Maps logprob standard deviation [0.0, 1.5+] to quality score [0.0, 1.0] (inverted)."""
    return max(0.0, min(1.0, 1.0 - (lp_std / 1.2)))


def _norm_pr_tail(p5_cal_lp: float) -> float:
    """Maps 5th-percentile calibrated logprob [3.5, 0.0] to quality score [0.0, 1.0]."""
    return max(0.0, min(1.0, (p5_cal_lp + 3.5) / 3.5))


def compute_pronunciation_features(parsed: ParsedWhisperOutput) -> PronunciationFeatures:
    genuine_words = [
        word
        for word in parsed.words
        if word.confidence_source in GENUINE_CONFIDENCE_SOURCES
    ]
    genuine_count = len(genuine_words)
    genuine_coverage = genuine_count / parsed.total_words if parsed.total_words else 0.0

    if parsed.total_words < 5 or genuine_count < 5:
        avg_logprobs = [
            segment.avg_logprob
            for segment in parsed.segments
            if segment.avg_logprob is not None
        ]
        global_avg = statistics.mean(avg_logprobs) if avg_logprobs else -0.5

        if global_avg > -0.18:
            pr_band = 8
        elif global_avg > -0.28:
            pr_band = 7
        elif global_avg > -0.38:
            pr_band = 6
        elif global_avg > -0.50:
            pr_band = 5
        elif global_avg > -0.65:
            pr_band = 4
        else:
            pr_band = 3

        return PronunciationFeatures(
            fw_baseline_logprob=0.0,
            calibration_shift=0.0,
            fw_sample_count=0,
            mean_cal_logprob=global_avg,
            p5_cal_logprob=0.0,
            logprob_std=0.0,
            content_mean_cal_logprob=0.0,
            severe_error_ratio=0.0,
            severe_error_count=0,
            high_noise_segment_ratio=0.0,
            s_mean=0.0,
            s_severe=0.0,
            s_consistency=0.0,
            s_tail=0.0,
            pr_raw=global_avg,
            pr_band=pr_band,
            calibration_reliable=False,
            genuine_confidence_word_count=genuine_count,
            genuine_confidence_coverage=genuine_coverage,
        )

    shift, fw_baseline, fw_count = _compute_calibration_shift(genuine_words)
    calibrated_logprobs = [word.logprob + shift for word in genuine_words]
    mean_cal_logprob = statistics.mean(calibrated_logprobs)
    sorted_calibrated_logprobs = sorted(calibrated_logprobs)
    p5_cal_logprob = sorted_calibrated_logprobs[
        int(len(sorted_calibrated_logprobs) * 0.05)
    ]
    if len(calibrated_logprobs) > 1:
        logprob_std = statistics.stdev(calibrated_logprobs)
    else:
        logprob_std = statistics.pstdev(calibrated_logprobs)

    content_logprobs = [
        calibrated_logprob
        for word, calibrated_logprob in zip(genuine_words, calibrated_logprobs)
        if _normalize_word(word.word) not in FUNCTION_WORDS
    ]
    content_mean_cal_logprob = (
        statistics.mean(content_logprobs) if content_logprobs else 0.0
    )

    severe_error_count = sum(
        _is_severe_error(word.word, calibrated_logprob)
        for word, calibrated_logprob in zip(genuine_words, calibrated_logprobs)
    )
    severe_error_ratio = severe_error_count / genuine_count
    high_noise_segment_count = sum(
        segment.no_speech_prob > 0.50 for segment in parsed.segments
    )
    high_noise_segment_ratio = (
        high_noise_segment_count / len(parsed.segments)
        if parsed.segments
        else 0.0
    )

    s_mean = _norm_pr_mean(mean_cal_logprob)
    s_severe = _norm_pr_severe(severe_error_ratio)
    s_consistency = _norm_pr_consistency(logprob_std)
    s_tail = _norm_pr_tail(p5_cal_logprob)
    pr_raw = (
        0.40 * s_mean
        + 0.30 * s_severe
        + 0.20 * s_consistency
        + 0.10 * s_tail
    )

    if pr_raw < 0.10:
        pr_band = 1
    elif pr_raw < 0.20:
        pr_band = 2
    elif pr_raw < 0.32:
        pr_band = 3
    elif pr_raw < 0.44:
        pr_band = 4
    elif pr_raw < 0.56:
        pr_band = 5
    elif pr_raw < 0.67:
        pr_band = 6
    elif pr_raw < 0.78:
        pr_band = 7
    elif pr_raw < 0.89:
        pr_band = 8
    else:
        pr_band = 9

    return PronunciationFeatures(
        fw_baseline_logprob=fw_baseline,
        calibration_shift=shift,
        fw_sample_count=fw_count,
        mean_cal_logprob=mean_cal_logprob,
        p5_cal_logprob=p5_cal_logprob,
        logprob_std=logprob_std,
        content_mean_cal_logprob=content_mean_cal_logprob,
        severe_error_ratio=severe_error_ratio,
        severe_error_count=severe_error_count,
        high_noise_segment_ratio=high_noise_segment_ratio,
        s_mean=s_mean,
        s_severe=s_severe,
        s_consistency=s_consistency,
        s_tail=s_tail,
        pr_raw=pr_raw,
        pr_band=pr_band,
        calibration_reliable=(fw_count >= MIN_FW_SAMPLES_FOR_CAL),
        genuine_confidence_word_count=genuine_count,
        genuine_confidence_coverage=genuine_coverage,
    )


def _build_diagnostics(ff: FluencyFeatures, pf: PronunciationFeatures) -> Dict:
    """
    Builds a structured dict of human-readable diagnostics for the LMS frontend.
    This dict is safe to serialize to JSON and is NOT used for scoring.
    """
    return {
        "fluency": {
            "speech_rate_wpm":        round(ff.speech_rate_wpm, 1),
            "articulation_rate_wpm":  round(ff.articulation_rate_wpm, 1),
            "silent_ratio_pct":       round(ff.silent_ratio * 100, 1),
            "long_pause_ratio_pct":   round(ff.long_pause_ratio * 100, 1),
            "hesitation_density_pct": round(ff.hesitation_density * 100, 1),
            "max_fluent_streak_words":ff.max_fluent_streak,
            "sub_scores": {
                "speech_rate":    round(ff.s_speech_rate, 3),
                "articulation":   round(ff.s_articulation_rate, 3),
                "pause_quality":  round(ff.s_pause_ratio, 3),
                "hesitation":     round(ff.s_hesitation, 3),
                "streak":         round(ff.s_streak, 3),
            },
            "fc_raw":  round(ff.fc_raw, 4),
            "fc_band": ff.fc_band,
        },
        "pronunciation": {
            "calibration_shift":        round(pf.calibration_shift, 4),
            "calibration_reliable":     pf.calibration_reliable,
            "fw_sample_count":          pf.fw_sample_count,
            "genuine_confidence_word_count": pf.genuine_confidence_word_count,
            "genuine_confidence_coverage_pct": round(
                pf.genuine_confidence_coverage * 100, 1
            ),
            "mean_calibrated_logprob":  round(pf.mean_cal_logprob, 4),
            "severe_error_ratio_pct":   round(pf.severe_error_ratio * 100, 1),
            "severe_error_count":       pf.severe_error_count,
            "logprob_consistency_std":  round(pf.logprob_std, 4),
            "high_noise_segment_pct":   round(pf.high_noise_segment_ratio * 100, 1),
            "sub_scores": {
                "mean_quality":   round(pf.s_mean, 3),
                "error_penalty":  round(pf.s_severe, 3),
                "consistency":    round(pf.s_consistency, 3),
                "tail_quality":   round(pf.s_tail, 3),
            },
            "pr_raw":  round(pf.pr_raw, 4),
            "pr_band": pf.pr_band,
        }
    }


def _collect_warnings(
    parsed: ParsedWhisperOutput,
    pf: PronunciationFeatures,
) -> List[str]:
    """
    Returns a list of data quality warning strings. Warnings do NOT affect scores.
    They are passed to the LMS for operator awareness.
    """
    warnings = []
    if parsed.total_words < 30:
        warnings.append(
            f"SHORT_RESPONSE: only {parsed.total_words} words  "
            "acoustic metrics less reliable below 30 words"
        )
    if not pf.calibration_reliable:
        warnings.append(
            f"LOW_FW_CALIBRATION: only {pf.fw_sample_count} function word samples "
            f"(need {MIN_FW_SAMPLES_FOR_CAL})  PR calibration skipped"
        )
    if pf.high_noise_segment_ratio > 0.15:
        warnings.append(
            f"HIGH_NOISE: {pf.high_noise_segment_ratio*100:.0f}% of segments show "
            "elevated no_speech_prob  recording quality may affect PR score"
        )
    if abs(pf.calibration_shift) > 0.45:
        warnings.append(
            f"LARGE_CAL_SHIFT: shift={pf.calibration_shift:.3f}  "
            "possible extreme recording condition or heavy accent"
        )
    fallback_rate = (
        parsed.logprob_fallback_count / parsed.total_words
        if parsed.total_words
        else 0.0
    )
    if fallback_rate >= HIGH_FALLBACK_RATE_THRESHOLD:
        warnings.append(
            f"HIGH_FALLBACK_RATE: {fallback_rate*100:.1f}% of words used segment "
            "logprob fallback. PR score is based on reduced genuine-confidence data."
        )
    if pf.genuine_confidence_word_count < 5:
        warnings.append(
            f"INSUFFICIENT_GENUINE_PR_DATA: only "
            f"{pf.genuine_confidence_word_count} words had genuine word-level "
            "confidence (need 5). PR score is low reliability."
        )
    return warnings


def score_acoustic(whisper_response: dict) -> AcousticScore:
    """
    Primary entry point. Accepts the raw Groq Whisper verbose_json dict.
    Returns AcousticScore with fc_score and pr_score as deterministic integers 1-9.
    """
    parsed      = parse_whisper_output(whisper_response)
    fluency     = compute_fluency_features(parsed)
    pronunc     = compute_pronunciation_features(parsed)
    diagnostics = _build_diagnostics(fluency, pronunc)
    warnings    = _collect_warnings(parsed, pronunc)

    return AcousticScore(
        fc_score      = fluency.fc_band,
        pr_score      = pronunc.pr_band,
        fc_raw        = fluency.fc_raw,
        pr_raw        = pronunc.pr_raw,
        fluency       = fluency,
        pronunciation = pronunc,
        diagnostics   = diagnostics,
        warnings      = warnings,
    )


def calibrate_thresholds(corpus: List[Dict]) -> Dict:
    """
    Offline calibration utility. Not called in production.

    Args:
        corpus: List of dicts, each with keys:
                'whisper_response': dict (raw Whisper API output)
                'human_fc_band':    int  (certified examiner FC band 1-9)
                'human_pr_band':    int  (certified examiner PR band 1-9)

    Returns:
        Dict with recommended threshold adjustments and MAE report.
    """
    fc_errors, pr_errors = [], []
    for sample in corpus:
        result = score_acoustic(sample['whisper_response'])
        fc_errors.append(abs(result.fc_score - sample['human_fc_band']))
        pr_errors.append(abs(result.pr_score - sample['human_pr_band']))

    return {
        "n_samples":       len(corpus),
        "fc_mae":          statistics.mean(fc_errors) if fc_errors else None,
        "pr_mae":          statistics.mean(pr_errors) if pr_errors else None,
        "fc_max_error":    max(fc_errors) if fc_errors else None,
        "pr_max_error":    max(pr_errors) if pr_errors else None,
        "recommendation":  (
            "Thresholds require manual adjustment if fc_mae > 0.75 or pr_mae > 0.75. "
            "Adjust the piecewise breakpoints in _fc_raw_to_band() and _pr_raw_to_band() "
            "using the corpus distribution to minimise MAE."
        )
    }


if __name__ == "__main__":
    test_response = {
        "duration": 10.0,
        "text": "I think education is very important",
        "words": [
            {"word": "I",           "start": 0.10, "end": 0.22, "probability": 0.97},
            {"word": "think",       "start": 0.25, "end": 0.60, "probability": 0.91},
            {"word": "education",   "start": 0.62, "end": 1.20, "probability": 0.78},
            {"word": "is",          "start": 2.80, "end": 2.95, "probability": 0.96},
            {"word": "very",        "start": 2.97, "end": 3.25, "probability": 0.88},
            {"word": "important",   "start": 3.28, "end": 3.95, "probability": 0.82},
        ],
        "segments": [
            {"id": 0, "start": 0.0, "end": 5.0, "text": "I think education is very important",
             "avg_logprob": -0.25, "compression_ratio": 1.5, "no_speech_prob": 0.04}
        ]
    }
    parsed = parse_whisper_output(test_response)
    assert parsed.total_words == 6
    assert parsed.words[3].gap_class == 'HESITATION'
    assert parsed.words[0].gap_class == 'NONE'
    print("PROMPT 1 VALIDATION PASSED")
    print(f"  Gap before 'is': {parsed.words[3].gap_before:.2f}s  {parsed.words[3].gap_class}")
    ff = compute_fluency_features(parsed)
    print(f"  Speech Rate: {ff.speech_rate_wpm:.1f} WPM")
    print(f"  Silent Ratio: {ff.silent_ratio:.3f}")
    print(f"  FC Raw: {ff.fc_raw:.4f}    FC Band: {ff.fc_band}")
    assert 1 <= ff.fc_band <= 9, "FC band out of range"
    print("PROMPT 2 VALIDATION PASSED")
    pf_result = compute_pronunciation_features(parsed)
    print(f"  FW Baseline LogProb: {pf_result.fw_baseline_logprob:.4f}")
    print(f"  Calibration Shift: {pf_result.calibration_shift:.4f}")
    print(f"  Mean Cal LogProb: {pf_result.mean_cal_logprob:.4f}")
    print(f"  Severe Error Ratio: {pf_result.severe_error_ratio:.4f}")
    print(f"  PR Raw: {pf_result.pr_raw:.4f}    PR Band: {pf_result.pr_band}")
    assert 1 <= pf_result.pr_band <= 9, "PR band out of range"
    print("PROMPT 3 VALIDATION PASSED")
    score = score_acoustic(test_response)
    print(f"\n  ACOUSTIC SCORE SUMMARY:")
    print(f"  FC Score: {score.fc_score}  (raw={score.fc_raw:.4f})")
    print(f"  PR Score: {score.pr_score}  (raw={score.pr_raw:.4f})")
    print(f"  Warnings: {score.warnings}")
    assert isinstance(score.fc_score, int), "FC score must be int"
    assert isinstance(score.pr_score, int), "PR score must be int"
    print("PROMPT 4 VALIDATION PASSED  acoustic_engine.py complete")
