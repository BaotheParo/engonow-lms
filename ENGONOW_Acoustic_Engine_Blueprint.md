# ENGONOW IELTS — Acoustic Assessment Engine
## Plan B: Pure Physics & DSP Blueprint + Coding Agent Prompts

**Document Reference:** ENGONOW-ACOUSTIC-ENGINE-001
**Classification:** Principal Architect Technical Specification
**Author:** Principal AI System Architect & DSP/Computational Linguistics Specialist
**Date:** July 2026

---

# SECTION 1: THE ACOUSTIC BLUEPRINT

---

## 1.0 Design Philosophy

This engine operates on a single core principle: **measure what Whisper actually
gives you, not what you wish it gave you.** The Groq Whisper API with
`verbose_json` and `timestamp_granularities[]=word` provides four categories
of extractable signal:

| Signal Category | Source | What It Measures |
|----------------|--------|-----------------|
| Word timestamps | `words[i].start`, `words[i].end` | Phonation time, articulation duration |
| Inter-word gaps | `words[i].start − words[i−1].end` | Pause behaviour, hesitation |
| Word probability | `words[i].probability` | ASR confidence → pronunciation proxy |
| Segment stats | `segments[i].avg_logprob`, `no_speech_prob` | Intelligibility, segment-level clarity |

Two IELTS criteria are derivable from these signals with deterministic math:

- **Fluency & Coherence (FC):** Entirely derivable from timing signals and gap
  patterns. The acoustic evidence for fluency is temporal — how fast, how many
  pauses, how long those pauses are.
- **Pronunciation (PR):** Indirectly but usefully inferable from probability
  distributions after speaker normalization. Low word probability on common
  words is a strong proxy for phoneme-level mispronunciation.

**What this engine deliberately cannot measure:** Coherence (logical flow of
ideas — requires text/LLM analysis), lexical resource, and grammatical range.
Those remain in the LLM domain. This engine delivers `fc_score` and `pr_score`
as deterministic integers so the LLM is never asked to evaluate acoustic
properties it cannot hear.

---

## 1.1 Whisper Output Schema Reference

```
Groq Whisper API response (verbose_json, word timestamps enabled):

{
  "task": "transcribe",
  "language": "english",
  "duration": 892.14,         ← total audio duration in seconds
  "text": "full transcript",
  "words": [                  ← word-level array
    {
      "word": "because",
      "start": 14.22,         ← word onset in seconds
      "end": 14.68,           ← word offset in seconds
      "probability": 0.9134   ← ASR confidence [0.0, 1.0]
    }
  ],
  "segments": [               ← segment-level array (silence-bounded chunks)
    {
      "id": 3,
      "start": 14.10,
      "end": 18.40,
      "text": "because I believe that...",
      "avg_logprob": -0.247,  ← mean log-prob across segment tokens
      "compression_ratio": 1.58,
      "no_speech_prob": 0.03  ← probability this segment contains no speech
    }
  ]
}

CRITICAL NOTE: `probability` is NOT `logprob`. Convert:
  logprob = math.log(probability + 1e-9)   ← +epsilon avoids log(0)
```

---

## 1.2 Fluency & Coherence (FC) — Mathematical Framework

FC is measured across **five independent acoustic dimensions**, each normalized
to a [0, 1] sub-score, then combined into a weighted composite.

---

### 1.2.1 Pause Taxonomy

Before any FC computation, classify all inter-word gaps:

```
gap_i = words[i].start − words[i−1].end    (for i = 1, 2, ..., N−1)

Taxonomy:
  MICRO     : gap_i < 0.15s   → coarticulation gap, discard from analysis
  NATURAL   : 0.15s ≤ gap_i < 0.50s → clause boundary, unremarkable
  HESITATION: 0.50s ≤ gap_i < 2.00s → cognitive load, language planning
  EXTENDED  : gap_i ≥ 2.00s   → fluency breakdown, significant penalty

τ_micro     = 0.15   (seconds)
τ_natural   = 0.50
τ_hesitation= 2.00
```

*Pedagogical grounding:* The 0.50s threshold is derived from psycholinguistic
research on planning pauses in L2 English (Skehan, 2009; Tavakoli & Skehan, 2005).
Pauses under 0.50s reflect articulatory phrasing and are normal across all band
levels. The 2.0s threshold marks the point where listeners perceive fluency
breakdown rather than natural topic development.

---

### 1.2.2 Dimension F1: Speech Rate (SR)

```
SR = (W_total / T_total) × 60      [words per minute]

Where:
  W_total = total word count (including fillers)
  T_total = words[-1].end − words[0].start   [total speaking time, seconds]
```

**Normalization function `f_SR(SR)` → [0, 1]:**

```
SR < 60           →  0.00                       (near-silence)
60 ≤ SR < 95      →  (SR − 60) / 35 × 0.25      [0.00, 0.25]
95 ≤ SR < 125     →  0.25 + (SR − 95) / 30 × 0.25  [0.25, 0.50]
125 ≤ SR < 155    →  0.50 + (SR − 125) / 30 × 0.30  [0.50, 0.80]
155 ≤ SR < 185    →  0.80 + (SR − 155) / 30 × 0.15  [0.80, 0.95]
185 ≤ SR < 210    →  0.95 + (SR − 185) / 25 × 0.05  [0.95, 1.00]
SR ≥ 210          →  max(0.75, 1.00 − (SR − 210) / 80)  (too fast → declining)
```

*Calibration anchor points (from CALL literature):*

| Cambridge Band | Typical SR Range (WPM) |
|---------------|------------------------|
| Band 4 | 70–100 |
| Band 5 | 95–125 |
| Band 6 | 120–150 |
| Band 7 | 140–175 |
| Band 8 | 160–195 |
| Band 9 | 155–205 (natural, not forced) |

---

### 1.2.3 Dimension F2: Articulation Rate (AR)

```
AR = (W_total / T_phonated) × 60   [words per minute during phonation only]

Where:
  T_phonated = Σᵢ (words[i].end − words[i].start)   [sum of all word durations]
```

AR excludes pauses. It measures how fast a speaker talks *when they are
actually talking*. High SR with high AR = genuinely fast and fluent. High SR
with low AR = many short words rather than genuine articulatory speed.

**Normalization function `f_AR(AR)` → [0, 1]:**

```
AR < 80           →  0.00
80 ≤ AR < 130     →  (AR − 80) / 50 × 0.40
130 ≤ AR < 180    →  0.40 + (AR − 130) / 50 × 0.35
180 ≤ AR < 220    →  0.75 + (AR − 180) / 40 × 0.20
AR ≥ 220          →  min(1.0, 0.95 + (AR − 220) / 100 × 0.05)
```

---

### 1.2.4 Dimension F3: Pause Ratio Score (PRS)

```
T_significant_pause = Σ(gap_i for gap_i ≥ τ_micro)
silent_ratio = T_significant_pause / T_total       [0, 1]

N_long   = count(gap_i ≥ τ_hesitation)
N_hes    = count(τ_natural ≤ gap_i < τ_hesitation)
N_total_significant = count(gap_i ≥ τ_micro)

long_pause_ratio  = N_long / max(N_total_significant, 1)
pause_freq_per_min = N_total_significant / (T_total / 60)
```

**Normalization function `f_PRS(silent_ratio, long_pause_ratio)` → [0, 1]:**

```
# Primary signal: silent_ratio (proportion of time spent in pauses)
if silent_ratio > 0.55:   sr_sub = 0.00
elif silent_ratio > 0.42: sr_sub = (0.55 − silent_ratio) / 0.13 × 0.20
elif silent_ratio > 0.30: sr_sub = 0.20 + (0.42 − silent_ratio) / 0.12 × 0.25
elif silent_ratio > 0.20: sr_sub = 0.45 + (0.30 − silent_ratio) / 0.10 × 0.25
elif silent_ratio > 0.12: sr_sub = 0.70 + (0.20 − silent_ratio) / 0.08 × 0.20
else:                     sr_sub = min(1.0, 0.90 + (0.12 − silent_ratio) / 0.12 × 0.10)

# Secondary penalty: long_pause_ratio
if long_pause_ratio > 0.25:   lp_penalty = 0.30
elif long_pause_ratio > 0.12: lp_penalty = 0.20
elif long_pause_ratio > 0.06: lp_penalty = 0.10
elif long_pause_ratio > 0.02: lp_penalty = 0.05
else:                         lp_penalty = 0.00

f_PRS = max(0.0, sr_sub − lp_penalty)
```

| Cambridge Band | Typical silent_ratio | Typical long_pause_ratio |
|---------------|---------------------|--------------------------|
| Band 4 | 0.45–0.60 | 0.20–0.40 |
| Band 5 | 0.35–0.48 | 0.10–0.22 |
| Band 6 | 0.25–0.38 | 0.05–0.12 |
| Band 7 | 0.16–0.26 | 0.02–0.06 |
| Band 8 | 0.10–0.18 | 0.005–0.02 |
| Band 9 | 0.05–0.14 | < 0.005 |

---

### 1.2.5 Dimension F4: Hesitation Density (HD)

Detect filler tokens via a curated regex lexicon applied to the word sequence:

```
FILLER_LEXICON = {
    'um', 'uh', 'er', 'ah', 'hmm', 'hm', 'ehm', 'umm', 'uhh', 'err',
    'you know', 'i mean', 'kind of', 'sort of', 'like'  ← discourse particle
}

N_fillers = count of words whose normalized form matches FILLER_LEXICON
HD = N_fillers / W_total    [0, 1]

Note: 'like' is only a filler when it appears as a standalone token between
content words, not when it appears in simile constructions ("I like", "feels like").
Implement context-sensitive check: flag 'like' only when not immediately preceded
by a verb or subject pronoun.
```

**Normalization function `f_HD(HD)` → [0, 1]:**

```
HD > 0.15:  0.00   (>15% of words are fillers → severe)
HD > 0.10:  (0.15 − HD) / 0.05 × 0.20
HD > 0.07:  0.20 + (0.10 − HD) / 0.03 × 0.25
HD > 0.04:  0.45 + (0.07 − HD) / 0.03 × 0.25
HD > 0.02:  0.70 + (0.04 − HD) / 0.02 × 0.20
HD > 0.005: 0.90 + (0.02 − HD) / 0.015 × 0.08
HD ≤ 0.005: 0.98  (near-zero fillers)
```

---

### 1.2.6 Dimension F5: Maximum Fluent Streak (MFS)

```
MFS = max length (in words) of any contiguous word sequence
      where no gap_i ≥ τ_hesitation (2.0s)

MFS_normalized = min(1.0, MFS / 40)

Calibration anchor:
  Band 4: MFS typically < 8 words before hesitation break
  Band 5: MFS 8–15 words
  Band 6: MFS 15–25 words
  Band 7: MFS 25–40 words
  Band 8: MFS 35–55 words
  Band 9: MFS > 50 words (extended unbroken clauses)
```

---

### 1.2.7 FC Composite Score and Band Mapping

**Weighted composite → [0, 1]:**

```python
FC_raw = (
    0.28 × f_SR(SR)           +   # Speech rate
    0.25 × f_PRS(...)         +   # Pause ratio & long pause
    0.22 × f_AR(AR)           +   # Articulation rate
    0.15 × f_HD(HD)           +   # Hesitation density
    0.10 × MFS_normalized         # Max fluent streak
)
```

Weight rationale: PRS (0.25+0.28=0.53 combined pause/rate signals) dominates
because the Cambridge FC descriptor uses temporal language as its primary
discriminator at every band level. MFS has lower weight (0.10) because it can
be gamed by producing fewer total utterances.

**FC Raw → Integer Band 1–9 (piecewise linear):**

```
FC_raw < 0.10  →  Band 1
FC_raw < 0.20  →  Band 2
FC_raw < 0.32  →  Band 3
FC_raw < 0.44  →  Band 4
FC_raw < 0.56  →  Band 5
FC_raw < 0.68  →  Band 6
FC_raw < 0.79  →  Band 7
FC_raw < 0.90  →  Band 8
FC_raw ≥ 0.90  →  Band 9
```

---

## 1.3 Pronunciation (PR) — Mathematical Framework

PR is derived from the statistical properties of word-level probability
distributions, after **speaker normalization** to remove recording-quality and
accent-baseline confounds.

---

### 1.3.1 The Logprob Signal

```
word_logprob_i = math.log(words[i].probability + 1e-9)

Typical value ranges:
  probability = 0.98 → logprob ≈ −0.020  (very confident = good pronunciation)
  probability = 0.80 → logprob ≈ −0.223  (confident)
  probability = 0.50 → logprob ≈ −0.693  (uncertain)
  probability = 0.20 → logprob ≈ −1.609  (poor = likely mispronunciation)
  probability = 0.05 → logprob ≈ −2.996  (severe error or extreme noise)
```

**The fundamental premise:** For common English words that a speaker of this
L1 background should know, the ASR model's uncertainty (low logprob) is
explained by one of two causes:

1. The speaker produced the phoneme incorrectly → **pronunciation error**
2. Background noise degraded the acoustic signal → **recording artifact**

We separate these causes through **Speaker Normalisation**.

---

### 1.3.2 Speaker Normalisation via Function Word Baseline

Function words (articles, prepositions, conjunctions, auxiliary verbs, pronouns)
are phonemically simple and acoustically predictable. A native speaker of any
accent will produce "the", "is", "and" with near-identical phoneme sequences.

```
FUNCTION_WORD_SET = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should',
    'could', 'may', 'might', 'can', 'i', 'you', 'he', 'she', 'we', 'they',
    'it', 'this', 'that', 'these', 'those', 'my', 'your', 'his', 'her',
    'our', 'their', 'its', 'not', 'so', 'as', 'if', 'all', 'me', 'him', 'us'
}

fw_logprobs = [logprob_i for word_i in words if word_i.lower() ∈ FUNCTION_WORD_SET]

# Require minimum 5 function word samples for reliable baseline
if len(fw_logprobs) < 5:
    calibration_shift = 0.0   ← fallback: no normalization
else:
    speaker_fw_baseline = mean(fw_logprobs)

    # Expected baseline for clear recording, any accent:
    # Native/Band 9:  −0.08 to −0.15
    # Good recording, non-native: −0.15 to −0.30
    # Home recording with mic noise: −0.25 to −0.45
    EXPECTED_FW_BASELINE = −0.18   ← calibrated constant

    calibration_shift = EXPECTED_FW_BASELINE − speaker_fw_baseline
    calibration_shift = clamp(calibration_shift, −0.60, +0.60)

# Apply shift to ALL word logprobs
calibrated_logprob_i = logprob_i + calibration_shift
```

The calibration shift corrects for microphone quality and recording environment.
A speaker in a noisy room will have systematically lower logprobs for all words.
We estimate the noise floor from function words and subtract it from content
words, leaving only the pronunciation-specific deviation.

---

### 1.3.3 Word Frequency Category (Rarity Correction)

Not all content words have equal logprob priors. The word "photosynthesis" will
have lower probability than "important" even for a native speaker, because the
language model has seen it less often in training. We classify words into
frequency tiers to set appropriate severe-error thresholds:

```
TIER_A_FUNCTION_WORDS = FUNCTION_WORD_SET   ← severe threshold: −0.80
TIER_B_HIGH_FREQ = {                         ← severe threshold: −1.10
    # Top 500 most frequent English content words
    'think', 'work', 'time', 'day', 'year', 'way', 'know', 'people',
    'new', 'good', 'first', 'old', 'last', 'place', 'make', 'life',
    # ... (full list in code constants)
}
TIER_C_GENERAL = None                        ← all other words, severe threshold: −1.60

def get_severe_threshold(word: str) -> float:
    word_lower = word.lower().strip("'.,!?")
    if word_lower in TIER_A_FUNCTION_WORDS:  return −0.80
    if word_lower in TIER_B_HIGH_FREQ:       return −1.10
    return −1.60                             # TIER_C default
```

A word's logprob is flagged as a SEVERE ERROR only when it falls below the
threshold appropriate for its frequency tier. This prevents penalizing a
speaker for having a wide vocabulary with rare words.

---

### 1.3.4 PR Feature Vector

```
# All computations use calibrated_logprob_i values

1. mean_cal_lp        = mean(calibrated_logprob_i for all words)
2. p5_cal_lp          = percentile(calibrated_logprob_i, 5)   ← worst 5%
3. lp_std             = stdev(calibrated_logprob_i)
4. severe_error_ratio = count(calibrated_logprob_i < severe_threshold(word_i)) / W_total
5. content_mean_lp    = mean(calibrated_logprob_i for word_i ∉ FUNCTION_WORD_SET)

# Segment-level cross-check
6. n_speech_segments  = count(segments where no_speech_prob < 0.30)
7. high_noise_ratio   = count(segments where no_speech_prob > 0.50) / total_segments
   (high_noise_ratio > 0.15 → flag for possible recording quality issue)
```

---

### 1.3.5 PR Composite Score and Band Mapping

**Sub-score normalization:**

```
# Sub-score P1: Mean logprob quality
# mean_cal_lp range: −2.0 (very poor) to 0.0 (perfect)
s_mean = clamp((mean_cal_lp + 2.0) / 2.0, 0.0, 1.0)

# Sub-score P2: Severe error penalty
# severe_error_ratio: 0.0 (no errors) to 1.0 (all words severe errors)
if severe_error_ratio > 0.30:   s_severe = 0.00
elif severe_error_ratio > 0.20: s_severe = (0.30 − severe_error_ratio) / 0.10 × 0.20
elif severe_error_ratio > 0.12: s_severe = 0.20 + (0.20 − severe_error_ratio) / 0.08 × 0.25
elif severe_error_ratio > 0.06: s_severe = 0.45 + (0.12 − severe_error_ratio) / 0.06 × 0.25
elif severe_error_ratio > 0.02: s_severe = 0.70 + (0.06 − severe_error_ratio) / 0.04 × 0.20
elif severe_error_ratio > 0.005:s_severe = 0.90 + (0.02 − severe_error_ratio) / 0.015 × 0.08
else:                           s_severe = 0.98

# Sub-score P3: Consistency (low std = consistent pronunciation across all words)
# lp_std typically 0.1 (very consistent) to 1.2 (very erratic)
s_consistency = clamp(1.0 − (lp_std / 1.2), 0.0, 1.0)

# Sub-score P4: Worst-tail quality (P5 percentile)
# p5_cal_lp range: typically −3.5 (catastrophic errors) to −0.05 (nearly perfect)
s_tail = clamp((p5_cal_lp + 3.5) / 3.5, 0.0, 1.0)
```

**Weighted composite:**

```python
PR_raw = (
    0.40 × s_mean        +   # Overall average confidence quality
    0.30 × s_severe      +   # Proportion of severely mispronounced words
    0.20 × s_consistency +   # Consistency of pronunciation across all words
    0.10 × s_tail            # Quality of worst-performing words
)
```

Weight rationale: `s_mean` (0.40) dominates because overall confidence reflects
the general intelligibility profile. `s_severe` (0.30) has high weight because
severe mispronunciations cause comprehension breakdown — the Cambridge PR
descriptor's primary discriminator.

**PR Raw → Integer Band 1–9:**

```
PR_raw < 0.10  →  Band 1
PR_raw < 0.20  →  Band 2
PR_raw < 0.32  →  Band 3
PR_raw < 0.44  →  Band 4
PR_raw < 0.56  →  Band 5
PR_raw < 0.67  →  Band 6
PR_raw < 0.78  →  Band 7
PR_raw < 0.89  →  Band 8
PR_raw ≥ 0.89  →  Band 9
```

| Cambridge Band | Expected PR_raw Range | mean_cal_lp Range | severe_error_ratio |
|---------------|----------------------|-------------------|--------------------|
| Band 4 | 0.28–0.44 | −1.10 to −0.85 | 0.18–0.28 |
| Band 5 | 0.44–0.56 | −0.85 to −0.65 | 0.10–0.18 |
| Band 6 | 0.56–0.67 | −0.65 to −0.45 | 0.05–0.10 |
| Band 7 | 0.67–0.78 | −0.45 to −0.28 | 0.02–0.05 |
| Band 8 | 0.78–0.89 | −0.28 to −0.12 | 0.005–0.02 |
| Band 9 | ≥ 0.89 | > −0.12 | < 0.005 |

---

## 1.4 Engine Architecture: Complete Data Flow

```
                    Groq Whisper verbose_json
                           │
                           ▼
               ┌───────────────────────┐
               │   PHASE 1: PARSING    │
               │   WhisperParser       │
               │   - Build WordToken[] │
               │   - Build Segment[]   │
               │   - Compute gap[]     │
               │   - Classify gaps     │
               └──────────┬────────────┘
                          │
               ┌──────────▼────────────┐
               │ PHASE 2: CALIBRATION  │
               │ SpeakerNormalizer     │
               │ - Extract FW logprobs │
               │ - Compute fw_baseline │
               │ - Apply shift to all  │
               └──────────┬────────────┘
                          │
            ┌─────────────┴──────────────┐
            │                            │
   ┌────────▼────────┐       ┌────────────▼───────┐
   │  FLUENCY ENGINE │       │ PRONUNCIATION ENGINE│
   │                 │       │                     │
   │  SR, AR, PRS    │       │  mean_lp, severe,   │
   │  HD, MFS        │       │  consistency, tail  │
   │  → FC_raw [0-1] │       │  → PR_raw [0-1]     │
   └────────┬────────┘       └──────────┬──────────┘
            │                            │
   ┌────────▼────────┐       ┌────────────▼───────┐
   │  FC BAND MAPPER │       │  PR BAND MAPPER     │
   │  → fc_score 1-9 │       │  → pr_score 1-9     │
   └────────┬────────┘       └──────────┬──────────┘
            │                            │
            └─────────────┬──────────────┘
                          │
               ┌──────────▼────────────┐
               │  AcousticScore OUTPUT │
               │  fc_score: int        │
               │  pr_score: int        │
               │  fc_raw: float        │
               │  pr_raw: float        │
               │  features: dict       │
               │  diagnostics: dict    │
               └───────────────────────┘
```

---

## 1.5 Calibration Validation Protocol

Before production deployment, validate thresholds against a corpus:

1. Collect minimum 30 student audio recordings with certified IELTS PR and FC
   scores from qualified examiners.
2. Run the acoustic engine on each recording.
3. Compute MAE between `fc_score` and human FC band, and between `pr_score`
   and human PR band.
4. Target: MAE ≤ 0.75 on each criterion independently.
5. If MAE > 0.75: adjust the piecewise thresholds in the Band Mapper using
   linear regression on the calibration corpus (fit breakpoints to minimise MAE).

The engine includes a `calibrate(corpus_data)` hook that accepts
`[(features, human_fc, human_pr)]` pairs and outputs recommended threshold adjustments.

---

---

# SECTION 2: THE CODING AGENT PROMPTS

Each prompt below is self-contained and can be pasted directly into Codex /
Cursor in isolation. Execute them in order. Each prompt references the outputs
of the previous.

---

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                  CODING AGENT PROMPT 1 OF 5                                ║
║       DATA STRUCTURES, WHISPER PARSER & GAP CALCULATOR                     ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

**PROMPT 1 — DATA LAYER**

---

Create a new Python file at the path `acoustic_engine.py` inside the root of the ENGONOW project (same directory as `mock_ai_services.py`). This file will become a zero-dependency (stdlib + math only) acoustic assessment engine.

**STEP 1 — Add the following module-level imports and constants. Do NOT add any other imports:**

```python
import math
import statistics
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
```

**STEP 2 — Define these exact dataclasses. Use exactly these field names as the rest of the engine depends on them:**

```python
@dataclass
class WordToken:
    word: str               # raw word string as returned by Whisper
    start: float            # word onset time in seconds
    end: float              # word offset time in seconds
    probability: float      # Whisper raw probability [0.0, 1.0]
    logprob: float          # computed: math.log(probability + 1e-9)
    duration: float         # computed: end - start
    gap_before: float       # gap between this word's start and previous word's end (0.0 for first word)
    gap_class: str          # 'MICRO', 'NATURAL', 'HESITATION', 'EXTENDED', or 'NONE' for first word

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
    total_duration: float           # last word end - first word start
    total_words: int                # len(words)
    raw_transcript: str             # full text joined from words
```

**STEP 3 — Define the following constants block immediately after the dataclasses:**

```python
# ─── Pause Classification Thresholds ────────────────────────────────────────
TAU_MICRO      = 0.15   # seconds: below this → coarticulation, ignore
TAU_NATURAL    = 0.50   # seconds: natural phrase boundary
TAU_HESITATION = 2.00   # seconds: significant fluency breakdown

# ─── Function Word Set (for speaker normalisation) ──────────────────────────
FUNCTION_WORDS = frozenset({
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should',
    'could', 'may', 'might', 'can', 'i', 'you', 'he', 'she', 'we', 'they',
    'it', 'this', 'that', 'these', 'those', 'my', 'your', 'his', 'her',
    'our', 'their', 'its', 'not', 'so', 'as', 'if', 'all', 'me', 'him',
    'us', 'them', 'been', 'being', 'am', 'its', 'up', 'out', 'about'
})

# ─── High-Frequency Tier B Content Words (top ~300) ─────────────────────────
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

# ─── Filler Token Patterns ───────────────────────────────────────────────────
FILLER_WORDS = frozenset({'um', 'uh', 'er', 'ah', 'hmm', 'hm', 'ehm', 'umm', 'uhh', 'err'})
FILLER_PHRASES = ['you know', 'i mean', 'kind of', 'sort of']
# Note: 'like' requires context check — handled separately in FluencyEngine

# ─── Speaker Normalisation Constants ─────────────────────────────────────────
EXPECTED_FW_BASELINE   = -0.18   # expected mean logprob of function words for any accent, decent mic
MIN_FW_SAMPLES_FOR_CAL = 5       # minimum function word samples to attempt calibration
MAX_CAL_SHIFT          = 0.60    # maximum allowed calibration shift magnitude

# ─── Severe Error Thresholds (by frequency tier) ─────────────────────────────
SEVERE_THRESHOLD_TIER_A = -0.80   # function words
SEVERE_THRESHOLD_TIER_B = -1.10   # high-freq content words
SEVERE_THRESHOLD_TIER_C = -1.60   # all other words
```

**STEP 4 — Implement the parser function with this exact signature:**

```python
def parse_whisper_output(whisper_response: dict) -> ParsedWhisperOutput:
```

This function must:
- Accept the raw dict returned by the Groq Whisper API (verbose_json format)
- Extract the `words` array. Handle the case where the response uses the key `"words"` or `"word_timestamps"` (check both)
- For each word entry, compute `logprob = math.log(float(entry.get("probability", 0.01)) + 1e-9)`
- Compute `duration = end - start`
- Compute `gap_before` for each word: `words[i].start - words[i-1].end` (0.0 for first word)
- Classify `gap_class` using the TAU constants: gaps < TAU_MICRO → 'MICRO', < TAU_NATURAL → 'NATURAL', < TAU_HESITATION → 'HESITATION', else 'EXTENDED', first word → 'NONE'
- Extract the `segments` array and build `WhisperSegment` objects. Handle missing keys with safe defaults: `avg_logprob=-0.5`, `no_speech_prob=0.05`, `compression_ratio=1.5`
- Compute `total_duration = words[-1].end - words[0].start` (return 0.0 if no words)
- Build `raw_transcript` by joining `word.word` with spaces
- Return a complete `ParsedWhisperOutput`
- Raise a descriptive `ValueError` if the `words` array is empty or missing

**STEP 5 — Write a `__main__` block that validates the parser with this minimal synthetic fixture:**

```python
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
    assert parsed.words[3].gap_class == 'HESITATION'  # 2.80 - 1.20 = 1.60s
    assert parsed.words[0].gap_class == 'NONE'
    print("PROMPT 1 VALIDATION PASSED")
    print(f"  Gap before 'is': {parsed.words[3].gap_before:.2f}s → {parsed.words[3].gap_class}")
```

Do not create any other functions in this file yet. The parser is the complete deliverable for Prompt 1.

---

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                  CODING AGENT PROMPT 2 OF 5                                ║
║           FLUENCY ENGINE — ALL FC METRICS & NORMALIZATION                  ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

**PROMPT 2 — FLUENCY ENGINE**

---

Working in the existing `acoustic_engine.py` file from Prompt 1, add the following code. Do NOT modify any existing code. Append only.

**STEP 1 — Add this AcousticFeatures dataclass after the ParsedWhisperOutput dataclass:**

```python
@dataclass
class FluencyFeatures:
    speech_rate_wpm: float          # total_words / total_duration_minutes
    articulation_rate_wpm: float    # total_words / phonated_time_minutes
    phonation_ratio: float          # phonated_time / total_duration
    silent_ratio: float             # significant_pause_time / total_duration
    mean_pause_duration: float      # mean of all significant gaps
    long_pause_ratio: float         # extended_pauses / total_significant_pauses
    pause_freq_per_min: float       # significant_pauses / total_duration_minutes
    hesitation_density: float       # filler_count / total_words
    max_fluent_streak: int          # max words without a TAU_HESITATION+ pause

    # Sub-scores [0.0, 1.0] for each dimension
    s_speech_rate: float
    s_articulation_rate: float
    s_pause_ratio: float
    s_hesitation: float
    s_streak: float

    # Weighted composite
    fc_raw: float                   # [0.0, 1.0]
    fc_band: int                    # integer 1-9
```

**STEP 2 — Implement the five normalization helper functions. These are pure math functions with no side effects:**

Implement exactly these functions with these signatures:
- `def _norm_speech_rate(sr: float) -> float`
- `def _norm_articulation_rate(ar: float) -> float`
- `def _norm_pause_ratio(silent_ratio: float, long_pause_ratio: float) -> float`
- `def _norm_hesitation_density(hd: float) -> float`
- `def _norm_max_fluent_streak(mfs: int) -> float`

Use the piecewise linear formulas defined in the blueprint (Section 1.2.2 through 1.2.6). Implement each as a series of `if/elif/else` conditions. Use `max(0.0, min(1.0, x))` clamping on all return values.

**STEP 3 — Implement the filler detection helper:**

```python
def _count_fillers(words: List[WordToken]) -> int:
```

- Iterate through `words`
- Check each `word.word.lower().strip("'.,!?-")` against `FILLER_WORDS`
- For multi-word fillers (`FILLER_PHRASES`), check pairs of consecutive words
- For `'like'`: count it as a filler ONLY if its position satisfies BOTH conditions:
  - The previous word is NOT in `{'feels', 'feel', 'felt', 'sounds', 'looks', 'seems', 'appears'}` (simile constructions)
  - The next word is NOT `'to'` (infinitive "like to")
- Return total filler count as int

**STEP 4 — Implement the main fluency computation function:**

```python
def compute_fluency_features(parsed: ParsedWhisperOutput) -> FluencyFeatures:
```

This function must:
1. Guard: if `parsed.total_words < 3` or `parsed.total_duration < 1.0`, return a `FluencyFeatures` with all scores at 0.0 and `fc_band = 1`
2. Compute phonated time: `sum(w.duration for w in parsed.words)`
3. Compute significant gaps: all `gap_before` values where `gap_before >= TAU_MICRO` and word is not the first
4. Compute `silent_ratio`, `mean_pause_duration`, `long_pause_ratio`, `pause_freq_per_min` from those gaps
5. Compute `speech_rate_wpm`, `articulation_rate_wpm`, `phonation_ratio`
6. Compute `hesitation_density` using `_count_fillers`
7. Compute `max_fluent_streak`: iterate through words tracking the current streak length, reset when a gap ≥ TAU_HESITATION is encountered, track max
8. Call all five `_norm_*` functions to get sub-scores
9. Compute weighted composite: `fc_raw = 0.28*s_SR + 0.25*s_PRS + 0.22*s_AR + 0.15*s_HD + 0.10*s_MFS`
10. Map `fc_raw` to `fc_band` using the piecewise thresholds from Section 1.2.7
11. Return complete `FluencyFeatures`

Handle `statistics.mean([])` edge cases with explicit length checks before calling `statistics.mean()`.

**STEP 5 — Append to the `__main__` block (add these lines inside the existing `if __name__ == "__main__":` block):**

```python
    ff = compute_fluency_features(parsed)
    print(f"  Speech Rate: {ff.speech_rate_wpm:.1f} WPM")
    print(f"  Silent Ratio: {ff.silent_ratio:.3f}")
    print(f"  FC Raw: {ff.fc_raw:.4f}  →  FC Band: {ff.fc_band}")
    assert 1 <= ff.fc_band <= 9, "FC band out of range"
    print("PROMPT 2 VALIDATION PASSED")
```

---

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                  CODING AGENT PROMPT 3 OF 5                                ║
║        PRONUNCIATION ENGINE — LOGPROB ANALYSIS & SPEAKER CALIBRATION       ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

**PROMPT 3 — PRONUNCIATION ENGINE**

---

Working in the existing `acoustic_engine.py`, append the following. Do NOT modify prior code.

**STEP 1 — Add PronunciationFeatures dataclass:**

```python
@dataclass
class PronunciationFeatures:
    # Speaker calibration
    fw_baseline_logprob: float      # observed function word mean logprob
    calibration_shift: float        # shift applied to all logprobs
    fw_sample_count: int            # number of function words used for calibration

    # Calibrated logprob statistics
    mean_cal_logprob: float         # mean after calibration shift
    p5_cal_logprob: float           # 5th percentile (worst words) after calibration
    logprob_std: float              # standard deviation of calibrated logprobs
    content_mean_cal_logprob: float # mean excluding function words

    # Error analysis
    severe_error_ratio: float       # proportion of words below their tier threshold
    severe_error_count: int         # absolute count of severe errors

    # Segment-level
    high_noise_segment_ratio: float # proportion of segments with no_speech_prob > 0.50

    # Sub-scores [0.0, 1.0]
    s_mean: float
    s_severe: float
    s_consistency: float
    s_tail: float

    # Composite
    pr_raw: float                   # [0.0, 1.0]
    pr_band: int                    # integer 1-9
    calibration_reliable: bool      # True if fw_sample_count >= MIN_FW_SAMPLES_FOR_CAL
```

**STEP 2 — Implement the speaker normalisation function:**

```python
def _compute_calibration_shift(words: List[WordToken]) -> Tuple[float, float, int]:
    """
    Returns (calibration_shift, fw_baseline_logprob, fw_sample_count).
    calibration_shift = 0.0 if insufficient function word samples.
    """
```

- Extract all words where `word.word.lower().strip("'.,!?") in FUNCTION_WORDS`
- If count < `MIN_FW_SAMPLES_FOR_CAL`, return `(0.0, 0.0, count)`
- Compute `fw_baseline = statistics.mean([w.logprob for w in fw_words])`
- Compute `shift = EXPECTED_FW_BASELINE - fw_baseline`
- Clamp shift to `[-MAX_CAL_SHIFT, +MAX_CAL_SHIFT]`
- Return `(shift, fw_baseline, count)`

**STEP 3 — Implement the severe error detector:**

```python
def _is_severe_error(word: str, calibrated_logprob: float) -> bool:
    """
    Returns True if the calibrated logprob falls below the tier-appropriate threshold.
    """
```

- Normalise word: `w = word.lower().strip("'.,!?-")`
- If `w in FUNCTION_WORDS`: threshold = `SEVERE_THRESHOLD_TIER_A`
- Elif `w in TIER_B_HIGH_FREQ`: threshold = `SEVERE_THRESHOLD_TIER_B`
- Else: threshold = `SEVERE_THRESHOLD_TIER_C`
- Return `calibrated_logprob < threshold`

**STEP 4 — Implement the four PR sub-score normalization functions:**

```python
def _norm_pr_mean(mean_cal_lp: float) -> float:
    """Maps calibrated mean logprob [−2.0, 0.0] to [0.0, 1.0]."""
    return max(0.0, min(1.0, (mean_cal_lp + 2.0) / 2.0))

def _norm_pr_severe(severe_ratio: float) -> float:
    """Maps severe error ratio [0.0, 1.0] to quality score [0.0, 1.0] (inverted)."""
    # Implement as piecewise from Section 1.3.5

def _norm_pr_consistency(lp_std: float) -> float:
    """Maps logprob standard deviation [0.0, 1.5+] to quality score [0.0, 1.0] (inverted)."""
    return max(0.0, min(1.0, 1.0 - (lp_std / 1.2)))

def _norm_pr_tail(p5_cal_lp: float) -> float:
    """Maps 5th-percentile calibrated logprob [−3.5, 0.0] to quality score [0.0, 1.0]."""
    return max(0.0, min(1.0, (p5_cal_lp + 3.5) / 3.5))
```

Implement `_norm_pr_severe` as the piecewise function from Section 1.3.5.

**STEP 5 — Implement the main pronunciation computation function:**

```python
def compute_pronunciation_features(parsed: ParsedWhisperOutput) -> PronunciationFeatures:
```

This function must:
1. Guard: if `parsed.total_words < 5`, return default `PronunciationFeatures` with `pr_band = 1`
2. Call `_compute_calibration_shift` to get `(shift, fw_baseline, fw_count)`
3. Apply shift: `calibrated_logprobs = [w.logprob + shift for w in parsed.words]`
4. Compute `mean_cal_logprob = statistics.mean(calibrated_logprobs)`
5. Compute `p5_cal_logprob = sorted(calibrated_logprobs)[int(len(calibrated_logprobs) * 0.05)]`
6. Compute `logprob_std = statistics.stdev(calibrated_logprobs)` (use `statistics.pstdev` if only 1 sample)
7. Compute `content_mean_cal_logprob` using only non-function-word logprobs
8. For each word, call `_is_severe_error(word.word, calibrated_lp)` and count totals
9. Compute `high_noise_segment_ratio` from `parsed.segments`
10. Compute all four sub-scores using `_norm_pr_*` functions
11. Compute `pr_raw = 0.40*s_mean + 0.30*s_severe + 0.20*s_consistency + 0.10*s_tail`
12. Map `pr_raw` to `pr_band` using thresholds from Section 1.3.5
13. Set `calibration_reliable = (fw_count >= MIN_FW_SAMPLES_FOR_CAL)`
14. Return complete `PronunciationFeatures`

**STEP 6 — Append to `__main__` block:**

```python
    pf_result = compute_pronunciation_features(parsed)
    print(f"  FW Baseline LogProb: {pf_result.fw_baseline_logprob:.4f}")
    print(f"  Calibration Shift: {pf_result.calibration_shift:.4f}")
    print(f"  Mean Cal LogProb: {pf_result.mean_cal_logprob:.4f}")
    print(f"  Severe Error Ratio: {pf_result.severe_error_ratio:.4f}")
    print(f"  PR Raw: {pf_result.pr_raw:.4f}  →  PR Band: {pf_result.pr_band}")
    assert 1 <= pf_result.pr_band <= 9, "PR band out of range"
    print("PROMPT 3 VALIDATION PASSED")
```

---

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                  CODING AGENT PROMPT 4 OF 5                                ║
║         COMPOSITE SCORER, DIAGNOSTICS PAYLOAD & CALIBRATION HOOK           ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

**PROMPT 4 — COMPOSITE SCORER & CALIBRATION HOOK**

---

Working in the existing `acoustic_engine.py`, append the following. Do NOT modify prior code.

**STEP 1 — Add AcousticScore dataclass:**

```python
@dataclass
class AcousticScore:
    fc_score: int               # final integer band 1-9 for Fluency & Coherence
    pr_score: int               # final integer band 1-9 for Pronunciation
    fc_raw: float               # FC composite before banding [0.0, 1.0]
    pr_raw: float               # PR composite before banding [0.0, 1.0]
    fluency: FluencyFeatures    # full fluency feature object
    pronunciation: PronunciationFeatures  # full pronunciation feature object
    diagnostics: Dict           # human-readable diagnostic payload for LMS
    warnings: List[str]         # list of data quality warnings
```

**STEP 2 — Implement the diagnostics builder:**

```python
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
```

**STEP 3 — Implement the warning detector:**

```python
def _collect_warnings(parsed: ParsedWhisperOutput, pf: PronunciationFeatures) -> List[str]:
    """
    Returns a list of data quality warning strings. Warnings do NOT affect scores.
    They are passed to the LMS for operator awareness.
    """
    warnings = []
    if parsed.total_words < 30:
        warnings.append(f"SHORT_RESPONSE: only {parsed.total_words} words — acoustic metrics less reliable below 30 words")
    if not pf.calibration_reliable:
        warnings.append(f"LOW_FW_CALIBRATION: only {pf.fw_sample_count} function word samples (need {MIN_FW_SAMPLES_FOR_CAL}) — PR calibration skipped")
    if pf.high_noise_segment_ratio > 0.15:
        warnings.append(f"HIGH_NOISE: {pf.high_noise_segment_ratio*100:.0f}% of segments show elevated no_speech_prob — recording quality may affect PR score")
    if abs(pf.calibration_shift) > 0.45:
        warnings.append(f"LARGE_CAL_SHIFT: shift={pf.calibration_shift:.3f} — possible extreme recording condition or heavy accent")
    return warnings
```

**STEP 4 — Implement the top-level entry point of the engine:**

```python
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
```

**STEP 5 — Implement the calibration hook (for future threshold tuning):**

```python
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
```

**STEP 6 — Append to `__main__` block:**

```python
    score = score_acoustic(test_response)
    print(f"\n  ACOUSTIC SCORE SUMMARY:")
    print(f"  FC Score: {score.fc_score}  (raw={score.fc_raw:.4f})")
    print(f"  PR Score: {score.pr_score}  (raw={score.pr_raw:.4f})")
    print(f"  Warnings: {score.warnings}")
    assert isinstance(score.fc_score, int), "FC score must be int"
    assert isinstance(score.pr_score, int), "PR score must be int"
    print("PROMPT 4 VALIDATION PASSED — acoustic_engine.py complete")
```

---

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                  CODING AGENT PROMPT 5 OF 5                                ║
║         FASTAPI INTEGRATION INTO mock_ai_services.py                       ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

**PROMPT 5 — FASTAPI INTEGRATION**

---

Open the existing `mock_ai_services.py` file. You are modifying the
`/api/v1/ai/speaking-analyze` endpoint to use the new `acoustic_engine.py`
for FC and PR scoring instead of returning random values.

**STEP 1 — Add this import at the top of `mock_ai_services.py`, after all existing imports:**

```python
from acoustic_engine import score_acoustic, AcousticScore
```

**STEP 2 — Locate the existing `mock_speaking_analyze` function. Replace it entirely with this new version:**

```python
@app.post(
    "/api/v1/ai/speaking-analyze",
    summary="Hybrid Speaking Analyzer — Acoustic Engine (FC + PR) + LLM (GRA + LR)",
    description=(
        "Accepts a Whisper verbose_json response payload and scores Fluency (FC) "
        "and Pronunciation (PR) deterministically via the ENGONOW Acoustic Engine. "
        "GRA and LR scores are passed in from the separate LLM evaluation track. "
        "Returns a unified score payload for the Java Spring Boot grading layer."
    ),
)
async def speaking_analyze(
    session_id:           str   = Form(..., description="Unique speaking session identifier"),
    whisper_response_json: str  = Form(..., description="Full Groq Whisper verbose_json response as a JSON string"),
    grammar_score:        int   = Form(..., description="GRA score from LLM evaluation (integer 1-9)", ge=1, le=9),
    lexical_score:        int   = Form(..., description="LR score from LLM evaluation (integer 1-9)",  ge=1, le=9),
):
    """
    Acoustic Engine integration endpoint.

    FC and PR are computed deterministically from Whisper metadata.
    GRA and LR are accepted as already-computed LLM outputs (integer 1-9).
    All four scores are assembled for the Java composite scoring layer.
    """
    import json as _json

    logger.info(
        "[ACOUSTIC ENGINE] Received speaking-analyze request. session_id='%s'", session_id
    )

    # ── Parse Whisper response ────────────────────────────────────────────────
    try:
        whisper_dict = _json.loads(whisper_response_json)
    except _json.JSONDecodeError as e:
        logger.error("[ACOUSTIC ENGINE] Failed to parse whisper_response_json: %s", str(e))
        raise HTTPException(
            status_code=422,
            detail=f"whisper_response_json is not valid JSON: {str(e)}"
        )

    # ── Run Acoustic Engine ───────────────────────────────────────────────────
    try:
        acoustic: AcousticScore = score_acoustic(whisper_dict)
    except ValueError as e:
        logger.warning(
            "[ACOUSTIC ENGINE] Acoustic engine ValueError for session_id='%s': %s — returning default scores",
            session_id, str(e)
        )
        # Default to Band 3 on engine failure (safe fallback — not zero)
        acoustic = None

    if acoustic is not None:
        fc_score = acoustic.fc_score
        pr_score = acoustic.pr_score
        diagnostics = acoustic.diagnostics
        warnings = acoustic.warnings
    else:
        fc_score = 3
        pr_score = 3
        diagnostics = {}
        warnings = ["ACOUSTIC_ENGINE_FAILED: defaulted to Band 3 for FC and PR"]

    # ── Validate all four scores are strict integers 1-9 ─────────────────────
    for name, val in [("fc_score", fc_score), ("pr_score", pr_score),
                      ("grammar_score", grammar_score), ("lexical_score", lexical_score)]:
        if not isinstance(val, int) or not (1 <= val <= 9):
            logger.error("[ACOUSTIC ENGINE] Invalid score %s=%r for session_id='%s'", name, val, session_id)
            raise HTTPException(
                status_code=500,
                detail=f"Score validation failed: {name}={val} is not an integer in [1,9]"
            )

    logger.info(
        "[ACOUSTIC ENGINE] session_id='%s' | FC=%d PR=%d GRA=%d LR=%d",
        session_id, fc_score, pr_score, grammar_score, lexical_score,
    )

    return {
        "session_id":         session_id,
        "pronunciation_score": pr_score,
        "fluency_score":       fc_score,
        "grammar_score":       grammar_score,
        "lexical_score":       lexical_score,
        "diagnostics":         diagnostics,
        "warnings":            warnings,
    }
```

**STEP 3 — Add a dedicated health/diagnostics endpoint for the engine (append after the above function):**

```python
@app.get("/api/v1/ai/acoustic-health", summary="Acoustic Engine Self-Test")
async def acoustic_health():
    """
    Runs a synthetic fixture through the acoustic engine and returns the result.
    Used by the Java health-check layer to verify the acoustic engine is functional.
    """
    from acoustic_engine import score_acoustic

    synthetic_whisper = {
        "duration": 20.0,
        "text": "I believe that technology has changed the way people communicate significantly",
        "words": [
            {"word": "I",            "start": 0.10, "end": 0.20, "probability": 0.97},
            {"word": "believe",      "start": 0.22, "end": 0.58, "probability": 0.89},
            {"word": "that",         "start": 0.60, "end": 0.80, "probability": 0.94},
            {"word": "technology",   "start": 0.82, "end": 1.45, "probability": 0.81},
            {"word": "has",          "start": 1.47, "end": 1.62, "probability": 0.96},
            {"word": "changed",      "start": 1.64, "end": 2.10, "probability": 0.85},
            {"word": "the",          "start": 2.12, "end": 2.22, "probability": 0.98},
            {"word": "way",          "start": 2.24, "end": 2.48, "probability": 0.93},
            {"word": "people",       "start": 2.50, "end": 2.88, "probability": 0.91},
            {"word": "communicate",  "start": 2.90, "end": 3.60, "probability": 0.77},
            {"word": "significantly","start": 4.80, "end": 5.60, "probability": 0.73},
        ],
        "segments": [
            {"id": 0, "start": 0.0, "end": 6.0, "text": "...",
             "avg_logprob": -0.28, "compression_ratio": 1.6, "no_speech_prob": 0.03}
        ]
    }

    result = score_acoustic(synthetic_whisper)
    return {
        "status": "UP",
        "engine": "ENGONOW Acoustic Assessment Engine v1.0",
        "synthetic_test": {
            "fc_score": result.fc_score,
            "pr_score": result.pr_score,
            "fc_raw":   round(result.fc_raw, 4),
            "pr_raw":   round(result.pr_raw, 4),
            "warnings": result.warnings,
        }
    }
```

**STEP 4 — Verify the application starts without errors by running:**

```bash
uvicorn mock_ai_services:app --host 0.0.0.0 --port 8001 --reload
```

Then in a second terminal, test the health endpoint:

```bash
curl http://localhost:8001/api/v1/ai/acoustic-health
```

Expected: HTTP 200 with JSON containing `"status": "UP"` and `fc_score` and
`pr_score` both between 1 and 9.

**This completes the full acoustic engine integration. The `speaking_analyze`
endpoint now scores FC and PR deterministically from Whisper physics, with
no LLM involvement in those two criteria. GRA and LR remain in the LLM track.**

---

## APPENDIX A: INTEGRATION ARCHITECTURE AFTER ALL 5 PROMPTS

```
Java Spring Boot (FEAT-04)
       │
       │  1. POST audio file
       ▼
Groq Whisper API ── verbose_json ──► mock_ai_services.py
                                           │
                    ┌──────────────────────┴──────────────────────┐
                    │                                             │
                    ▼                                             ▼
            acoustic_engine.py                    Gemini 2.5 Flash (LLM)
            score_acoustic(whisper_dict)          evaluate_speaking_gemini()
                    │                                             │
            fc_score (int 1-9)                       grammar_score (int 1-9)
            pr_score (int 1-9)                       lexical_score (int 1-9)
                    │                                             │
                    └─────────────────┬───────────────────────────┘
                                      │
                                      ▼
                          /api/v1/ai/speaking-analyze
                          Unified JSON payload → Java
                                      │
                                      ▼
                          Java FEAT-04 Webhook Handler
                          Cambridge Penalisation Layer
                          (ENGONOW-IELTS-SPEC-001)
                                      │
                                      ▼
                          Final Band Score → PostgreSQL
```

## APPENDIX B: EXPECTED BENCHMARK IMPROVEMENT AFTER IMPLEMENTATION

| Benchmark File | Human Band | Old AI (LLM-only) | Expected New (Acoustic Engine) |
|----------------|-----------|------------------|-------------------------------|
| tiw_mock_test.mp3 | 7.5 | 5.50 | 6.5–7.5 |
| tiw_mock_test_2.mp3 | 6.0 | 4.83 | 5.5–6.5 |
| tiw_mock_test_3.mp3 | 4.5 | 4.17 | 4.0–5.0 |

The acoustic engine eliminates the modality gap for FC and PR. Remaining delta
is attributable to (a) the inherent limits of logprob as PR proxy vs. phoneme-level
analysis, and (b) the coherence component of FC (which requires calibrated
text analysis, not pure acoustics). Target MAE ≤ 0.75 after threshold calibration
on a corpus of 30+ human-rated recordings.

---

*End of Document — ENGONOW-ACOUSTIC-ENGINE-001 v1.0*
