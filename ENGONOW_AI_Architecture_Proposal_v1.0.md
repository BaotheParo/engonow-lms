# TECHNICAL PROPOSAL \& ARCHITECTURE EVALUATION DOCUMENT

\---

**Project:** ENGONOW Smart LMS — Automated IELTS Speaking Assessment Module
**Document Reference:** ENGONOW-ARCH-2026-001
**Version:** 1.0 
**Prepared For:** Chief Executive Officer \& Board of Directors, ENGONOW
**Prepared By:** AI Architecture \& EdTech Technical Consultancy Division
**Date:** June 23, 2026
**Classification:** Internal — Confidential

\---

|Version|Date|Author|Status|
|-|-|-|-|
|0.1|June 10, 2026|Lead Backend Engineer|Initial Draft|
|0.9|June 18, 2026|AI Architecture Consultant|Review \& Expansion|
|1.0|June 23, 2026|AI Architecture Consultant|Final — Board Submission|

\---

## TABLE OF CONTENTS

1. Executive Summary
2. Evaluation of the Initial Technical Hypothesis
3. Architectural Options

   * Option 1: Full Commercial API Stack
   * Option 2: Hybrid Architecture — Open-Source STT + Targeted Commercial APIs 
   * Option 3: Fully Self-Hosted Open-Source Stack
4. Options Comparison Matrix
5. Consultant's Definitive Recommendation
6. Proposed Implementation Roadmap
7. Risk Register
8. Approval Signatures

\---

\---

## 1\. EXECUTIVE SUMMARY

### 1.1 Module Objective

ENGONOW Smart LMS is developing an **Automated IELTS Speaking Mock Test Module** designed to deliver on-demand, AI-powered speaking assessment to learners without requiring a human examiner for every session. This capability represents a significant competitive differentiator in the Vietnamese EdTech market and directly supports ENGONOW's core mission: delivering accessible, high-quality IELTS preparation at scale.

The module will evaluate learner spoken responses across the four official IELTS Speaking Band Descriptors as defined by Cambridge Assessment English:

|#|Criterion|Core Evaluation Domain|
|-|-|-|
|1|**Fluency \& Coherence (FC)**|Speech rate, pause patterns, hesitation frequency, logical flow of ideas|
|2|**Lexical Resource (LR)**|Vocabulary range, precision, collocations, and idiomatic expression usage|
|3|**Grammatical Range \& Accuracy (GRA)**|Structural variety, tense control, clause complexity, and error frequency|
|4|**Pronunciation (P)**|Phoneme accuracy, word stress, sentence rhythm, and overall intelligibility|

The system will conduct full simulations of all three IELTS Speaking Parts, generate a per-criterion Band score (1–9), and produce actionable written feedback reports — all within minutes of test completion.

\---

### 1.2 Strategic Cost Optimization Framework

A naive, end-to-end commercial API approach for a 15-minute speaking test would cost an estimated **$0.50 – $2.00 per test** in API fees. At a modest volume of 2,000 tests/month, this equates to **$12,000 – $24,000 per year** in operational API spend alone — economically unsustainable for an MVP phase.

The Lead Backend Engineer has proposed a **strategic criterion decomposition approach** that forms the basis of this evaluation:

> \*\*Insight:\*\* Not all four IELTS criteria require expensive audio-level processing. Lexical Resource and Grammatical Range are fundamentally \*text-level\* phenomena. Once a high-quality transcript is produced, these two criteria can be evaluated via an LLM at a fraction of the cost of audio API processing.

This leads to a two-track processing architecture:

* **Track 1 — Text Track (LR + GRA):** Transcribe audio once using an STT model, then submit the text transcript to a commercial or local LLM for linguistic evaluation. This eliminates per-second audio charges for what is effectively an NLP task.
* **Track 2 — Audio Track (P + FC):** Either leverage a dedicated pronunciation API, or extract measurable acoustic signals (pause timing, speech rate) directly from STT model outputs (word-level timestamps), minimizing dependency on expensive full-audio analytics APIs.

The three architectural options presented in this document represent **three distinct implementations of this framework** at different cost, accuracy, and engineering complexity trade-off points, enabling the Board to make an informed, risk-calibrated investment decision.

\---

\---

## 2\. EVALUATION OF THE INITIAL TECHNICAL HYPOTHESIS

### 2.1 Hypothesis Recap (As Submitted by Lead Backend Engineer)

> \*\*Hypothesis A — Lexical \& Grammar:\*\* Use an open-source Speech-to-Text (STT) model to produce a transcript, then feed the text to a commercial or open-source LLM to evaluate vocabulary and grammar — avoiding audio API costs for text-level analysis.

> \*\*Hypothesis B — Pronunciation \& Fluency:\*\* Use open-source ML models to analyze audio waveforms, or leverage word-level confidence scores and timestamps from the STT model to mathematically calculate pause durations and pronunciation accuracy, without requiring deep acoustic waveform processing.

\---

### 2.2 Assessment of Hypothesis A: STT → LLM for Lexical \& Grammar

#### &#x20;Strengths

**Architecturally sound and industry-validated.** The pattern of decoupling audio transcription from linguistic analysis is a well-established best practice in production NLP pipelines. It enables independent replacement of either component without architectural disruption.

**LLMs are the state-of-the-art for rubric-based text evaluation.** Peer-reviewed studies and internal benchmarks demonstrate that leading models (GPT-4o, Claude 3.5 Sonnet, Gemini 1.5 Pro) achieve high inter-rater agreement with certified IELTS examiners on grammar and vocabulary tasks when provided with well-structured prompts aligned to official band descriptors.

**The cost optimization is mathematically valid.** Processing a 600-word IELTS speaking transcript costs approximately $0.003 – $0.012 per test with leading LLM APIs, versus $0.08 – $0.30 for equivalent audio-level processing with speech analytics APIs. The cost difference is an order of magnitude.

**Prompt engineering provides high pedagogical flexibility.** Official IELTS Band Descriptors for Bands 5–9 can be embedded directly into system prompts, enabling nuanced, criterion-specific scoring with explicit, citable feedback. This is not easily achievable with acoustic models alone.

#### &#x20;Risks and Limitations

**Transcription error propagation.** The quality of LLM-based scoring is entirely contingent on STT accuracy. For Vietnamese learners of English, STT models encounter a specific set of phoneme substitution patterns (e.g., /θ/ → /t/ in "three," final consonant deletion, vowel shortening) that can introduce transcription errors. A grammar error caused by mishearing is indistinguishable from a genuine learner error at the transcript level — leading to unfair penalization.

**LLM scoring inconsistency without calibration.** Without structured output schemas, few-shot examples calibrated against Cambridge-certified scripts, and temperature controls, LLMs may produce inconsistent Band score assignments across sessions. A robust prompt engineering framework is a prerequisite, not an afterthought.

**Sequential latency without parallelization.** A naive synchronous pipeline (record → STT → LLM) compounds API latency. Mitigation via asynchronous processing and parallel criterion evaluation calls is required from the outset.

#### MVP Feasibility Rating:  HIGH

This is a proven architectural pattern with mature tooling. Risks are manageable with proper STT model selection and a validated prompt library. Recommended to proceed as the foundation of the LR/GRA evaluation pipeline.

\---

### 2.3 Assessment of Hypothesis B: Audio-Derived Signals for Pronunciation \& Fluency

#### &#x20;Strengths

**Timestamp-based fluency calculation is scientifically grounded.** Word-level timestamp outputs from STT models (notably OpenAI Whisper's `word\_timestamps` feature) enable reliable mathematical derivation of the following IELTS-relevant metrics:

|Metric|Calculation|
|-|-|
|Speech Rate|Total words ÷ total speech duration (words/minute)|
|Mean Pause Duration|Sum of inter-word silences ÷ total pause count (seconds)|
|Long Pause Frequency|Count of pauses > 0.5 seconds ÷ total duration (pauses/minute)|
|Articulation Rate|Total words ÷ total phonated time (words/second)|
|Hesitation Density|Detected filler tokens ("uh", "um", "er") ÷ total words|

These metrics correlate strongly with official IELTS Fluency \& Coherence descriptors and can be assembled into a transparent, auditable scoring function without any additional API calls.

**Computationally negligible cost.** Fluency metric derivation requires only Python arithmetic on existing STT output. There is no additional API cost or infrastructure requirement beyond the STT inference already performed.

**Avoids over-engineering for an MVP.** Deep acoustic signal processing (formant analysis, prosody modeling, F0 contour extraction) is technically sophisticated and carries a high implementation risk for a 3-month timeline. The timestamp-based approach achieves strong coverage of fluency criteria without this complexity.

#### &#x20;Risks and Limitations

**Pronunciation assessment via STT confidence scores is linguistically insufficient.** This is the most critical technical risk in the original hypothesis and must be addressed directly. A word-level confidence score reflects the *STT model's recognition certainty* — it is a proxy for *acoustic clarity*, not *phonemic accuracy*. These are meaningfully different:

> \*\*Example:\*\* A Vietnamese learner who consistently substitutes /l/ with /n/ (e.g., "nook" for "look") may still receive a high word confidence score from Whisper if the model has encountered this accent pattern in training data. The STT system has "understood" the word — but the learner's pronunciation is nonetheless a Band 5 error. Relying on confidence scores would produce \*\*false positives\*\*, awarding learners high pronunciation scores for phonemically incorrect speech.

**Open-source phoneme-level models require significant deployment effort.** Tools such as Montreal Forced Aligner (MFA), wav2vec 2.0, and Allosaurus are capable of genuine phoneme-level analysis but require: acoustic model training or fine-tuning for non-native accents, Grapheme-to-Phoneme configuration, and extensive validation against IELTS rubrics. This scope exceeds a 3-month MVP timeline if implemented from scratch.

#### MVP Feasibility Rating — Nuanced Assessment:

|Sub-Component|MVP Feasibility|
|-|-|
|Fluency via Whisper timestamps| HIGH — Recommended to proceed|
|Pronunciation via confidence scores only| LOW Accuracy — Not recommended without augmentation|
|Full phoneme-level open-source model| OUT OF SCOPE for 3-month MVP|
|Pronunciation via targeted commercial API| HIGH — Recommended bridge solution|

\---

### 2.4 Overall Hypothesis Verdict

The Lead Backend Engineer's hypothesis demonstrates **strong first-principles reasoning and a sound cost-optimization instinct.** The core framework is correct and forms the direct basis of the recommended architecture. The single point requiring augmentation is the **pronunciation evaluation pathway**: confidence score proxies are insufficient for protecting ENGONOW's academic credibility. A dedicated pronunciation assessment mechanism — either commercial API (for MVP speed) or a validated acoustic model (for Phase 2 cost optimization) — must be incorporated.

\---

\---

## 3\. ARCHITECTURAL OPTIONS

\---

### OPTION 1: Full Commercial API Stack

> \*"Maximum Accuracy, Maximum Speed-to-Market"\*

\---

#### 3.1.1 Approach Overview

This option deploys best-in-class commercial APIs for all four IELTS criteria. The engineering team builds only integration logic, scoring normalization, and the student-facing feedback layer. No machine learning model deployment, GPU infrastructure, or MLOps tooling is required.

\---

#### 3.1.2 Technical Stack

|Component|Technology|Provider|
|-|-|-|
|Speech-to-Text + Pronunciation Assessment|Azure AI Speech — Pronunciation Assessment API|Microsoft Azure|
|Fluency Score (Built-In)|Azure Speech `FluencyScore` + `ProsodyScore`|Microsoft Azure|
|Lexical Resource Evaluation|GPT-4o mini|OpenAI|
|Grammatical Range \& Accuracy|GPT-4o mini (parallel call)|OpenAI|
|Audio Storage|Azure Blob Storage|Microsoft Azure|
|Backend API|Python / FastAPI|Open-Source|
|Database|PostgreSQL|Open-Source|

\---

#### 3.1.3 System Architecture Flow

```
┌─────────────────────────────────────────────────────────┐
│                  STUDENT INTERFACE (LMS)                │
└────────────────────────┬────────────────────────────────┘
                         │  Audio Upload (WAV/MP3, \~15 min)
                         ▼
┌─────────────────────────────────────────────────────────┐
│              AZURE AI SPEECH SERVICES                   │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Pronunciation Assessment API                    │   │
│  │  ├── Word-level transcript                       │   │
│  │  ├── Phoneme-level accuracy scores (IPA)         │   │
│  │  ├── FluencyScore (pause/rate analysis)          │   │
│  │  ├── ProsodyScore (rhythm, intonation)           │   │
│  │  └── Overall Pronunciation Band (mapped 1–9)    │   │
│  └──────────────────────────────────────────────────┘   │
└────────────┬────────────────────────────────────────────┘
             │  Transcript (text)
             ▼
┌─────────────────────────────────────────────────────────┐
│              OPENAI GPT-4o mini (Parallel Calls)        │
│  ┌───────────────────┐  ┌───────────────────────────┐   │
│  │  LR Rubric Prompt │  │  GRA Rubric Prompt        │   │
│  │  → Band Score     │  │  → Band Score             │   │
│  │  → LR Feedback    │  │  → Error Annotations      │   │
│  └───────────────────┘  └───────────────────────────┘   │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│          SCORING ENGINE \& REPORT GENERATOR              │
│  ├── Normalize all sub-scores to IELTS Band 1–9        │
│  ├── Compute weighted overall Band estimate            │
│  ├── Generate student feedback report (PDF/HTML)       │
│  └── Persist results → PostgreSQL                      │
└─────────────────────────────────────────────────────────┘
```

\---

#### 3.1.4 How It Grades the 4 Criteria

|Criterion|Mechanism|Accuracy Level|
|-|-|-|
|**Pronunciation (P)**|Azure Pronunciation Assessment returns phoneme-level accuracy, including IPA transcription, specific mispronounced phonemes, and an aggregate score (0–100). ENGONOW maps this to IELTS Band 1–9 via a calibrated conversion function.| Excellent|
|**Fluency \& Coherence (FC)**|Azure natively returns `FluencyScore` (pause patterns, speech rate) and `ProsodyScore` (rhythm, stress). Coherence (topic development, discourse markers) is evaluated by GPT-4o mini on the transcript.| Excellent|
|**Lexical Resource (LR)**|Full transcript submitted to GPT-4o mini with a structured IELTS LR Band descriptor system prompt. Returns JSON: Band score, identified strengths, specific vocabulary gaps, and recommended improvements.| Excellent|
|**Grammatical Range \& Accuracy (GRA)**|Parallel GPT-4o mini call with GRA-specific rubric. Returns JSON: Band score, error type classification (tense, subject-verb agreement, clause structure), and corrected examples.| Excellent|

\---

#### 3.1.5 Pros

**Business Benefits:**

* Fastest time-to-market: estimated **6–8 weeks** from approval to production deployment
* Highest out-of-the-box accuracy — protects ENGONOW's academic and institutional reputation at launch
* Azure Pronunciation Assessment is the recognized industry standard for non-native speaker evaluation, used by major EdTech platforms globally
* Microsoft and OpenAI SLAs guarantee **99.9% uptime** — appropriate for a commercial student-facing product
* No ML engineering expertise required — backend team builds integration and product logic only
* Elastic scaling: usage-based pricing means cost scales linearly with revenue

**Technical Benefits:**

* Azure Pronunciation Assessment delivers IPA-level phoneme analysis and pedagogically specific feedback ("The phoneme /θ/ in the word 'three' was produced as /t/")
* GPT-4o mini provides strong LR/GRA scoring at extremely low per-token cost (\~$0.15/$0.60 per 1M tokens input/output)
* Extensive official documentation, SDKs (Python, Node.js), and community support reduce integration risk
* Built-in audio format normalization — handles WAV, MP3, OGG without preprocessing

\---

#### 3.1.6 Cons

* **Highest per-test operational cost** of all three options — unsustainable above \~3,000 tests/month without significant revenue
* **Maximum vendor lock-in** — dependent on both Microsoft Azure and OpenAI pricing decisions, which have historically increased year-over-year
* **Data privacy exposure** — all learner audio is transmitted to third-party cloud infrastructure; requires legal review for compliance with Vietnam's Personal Data Protection Decree (PDPD 13/2023) and potential GDPR obligations if serving international learners
* **Zero proprietary IP developed** — any competitor with an API key can build an identical product; no defensible technical moat
* Long-term unit economics deteriorate as scale increases; does not benefit from infrastructure amortization

\---

#### 3.1.7 Estimated Cost Impact

|Cost Category|Estimate|Basis|
|-|-|-|
|Operational cost per test|**$0.40 – $0.80**|\~15 min audio × Azure Speech rate ($0.016/min) + GPT-4o mini tokens|
|Operational cost at 1,000 tests/month|**$400 – $800/month**|API costs only|
|Operational cost at 5,000 tests/month|**$2,000 – $4,000/month**|API costs only|
|Development cost|**Low**|6–8 weeks, 1–2 backend engineers|
|Infrastructure overhead|**Minimal**|Serverless / cloud-managed only|
|**Overall Rating**| HIGH Operational /  LOW Development|—|

\---

\---

### OPTION 2: Hybrid Architecture — Open-Source STT + Targeted Commercial APIs

> \*"Optimized Cost-Accuracy Balance — Recommended for Phase 1 MVP"\* 

\---

#### 3.2.1 Approach Overview

This option is the direct implementation of the Lead Engineer's hypothesis in its most robust, production-ready form. Open-source tooling handles audio transcription and fluency metric extraction — eliminating the highest-volume audio API expense. Targeted commercial APIs are retained only for the two criteria that are most accuracy-critical and most difficult to replicate with open-source alternatives in a 3-month window: **pronunciation assessment** and **linguistic scoring**.

This is not a compromise architecture. It is a **deliberately engineered cost-accuracy optimization** that produces 80–90% of Option 1's accuracy at approximately **25% of its per-test operational cost.**

\---

#### 3.2.2 Technical Stack

|Component|Technology|Type|Deployment|
|-|-|-|-|
|Speech-to-Text|OpenAI Whisper Large v3 (via `faster-whisper`)|Open-Source|Self-Hosted|
|Fluency Metrics Engine|Custom Python module (Whisper timestamp analysis)|Open-Source / Proprietary|Self-Hosted|
|Pronunciation Assessment|Azure AI Speech — Pronunciation Assessment API|Commercial API|Cloud (Targeted)|
|Lexical Resource|Claude 3.5 Haiku or GPT-4o mini|Commercial API|Cloud|
|Grammatical Range \& Accuracy|Claude 3.5 Haiku or GPT-4o mini|Commercial API|Cloud|
|Grammar Annotation (Supplementary)|LanguageTool (self-hosted, optional)|Open-Source|Self-Hosted|
|GPU Compute (STT)|AWS EC2 `g4dn.xlarge` (1× NVIDIA T4 16GB)|Cloud Infrastructure|Managed|
|Async Task Queue|Celery + Redis|Open-Source|Self-Hosted|
|Audio/Data Storage|AWS S3 + PostgreSQL (RDS)|Cloud|Managed|
|Backend API|Python / FastAPI|Open-Source|Self-Hosted|

\---

#### 3.2.3 The Fluency Calculation Engine — Technical Specification

The following Python-based module derives IELTS-relevant fluency signals from Whisper's `word\_timestamps` output, requiring no additional API call:

```python
# ─────────────────────────────────────────────────────────────────
#  ENGONOW Fluency Metrics Engine v1.0
#  Input:  Whisper word\_timestamps output
#  Output: IELTS-aligned fluency signals
# ─────────────────────────────────────────────────────────────────

def compute\_fluency\_metrics(word\_timestamps: list\[dict]) -> dict:

    # ── Core temporal calculations ───────────────────────────────
    total\_words       = len(word\_timestamps)
    total\_duration    = word\_timestamps\[-1]\["end"] - word\_timestamps\[0]\["start"]
    phonated\_time     = sum(w\["end"] - w\["start"] for w in word\_timestamps)
    silent\_time       = total\_duration - phonated\_time

    pauses = \[
        word\_timestamps\[i]\["start"] - word\_timestamps\[i - 1]\["end"]
        for i in range(1, len(word\_timestamps))
        if (word\_timestamps\[i]\["start"] - word\_timestamps\[i - 1]\["end"]) > 0.15
    ]  # Threshold: >150ms = meaningful pause

    # ── Derived IELTS fluency signals ────────────────────────────
    speech\_rate       = (total\_words / total\_duration) \* 60          # words/min
    articulation\_rate = total\_words / phonated\_time                  # words/sec
    mean\_pause\_dur    = sum(pauses) / len(pauses) if pauses else 0   # seconds
    long\_pause\_ratio  = len(\[p for p in pauses if p > 0.5]) / max(len(pauses), 1)
    silence\_ratio     = silent\_time / total\_duration                  # 0.0 – 1.0

    # ── Composite fluency score (Band-aligned, tunable weights) ──
    fluency\_score = (
        normalize(speech\_rate, target\_range=(100, 160)) \* 0.30 +
        normalize(mean\_pause\_dur, target\_range=(0.0, 0.5), invert=True) \* 0.25 +
        (1 - long\_pause\_ratio) \* 0.25 +
        normalize(articulation\_rate, target\_range=(2.5, 4.0)) \* 0.20
    )  # → 0.0–1.0, mapped to IELTS Band 4.0–9.0

    return {
        "speech\_rate\_wpm":      round(speech\_rate, 1),
        "articulation\_rate":    round(articulation\_rate, 2),
        "mean\_pause\_duration":  round(mean\_pause\_dur, 3),
        "long\_pause\_ratio":     round(long\_pause\_ratio, 3),
        "silence\_ratio":        round(silence\_ratio, 3),
        "fluency\_composite":    round(fluency\_score, 3),
        "estimated\_band":       map\_to\_ielts\_band(fluency\_score)
    }
```

> \*\*Note:\*\* Coherence (logical flow, discourse marker usage, topic development) is evaluated at the text level by the LLM call as a supplement to the acoustic fluency metrics above.

\---

#### 3.2.4 System Architecture Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     STUDENT INTERFACE (LMS)                     │
└───────────────────────────┬─────────────────────────────────────┘
                            │  Audio Upload (WAV/MP3, \~15 min)
                            ▼
              ┌─────────────────────────────┐
              │   ASYNC TASK QUEUE (Celery) │
              └──────────┬──────────────────┘
                         │
          ┌──────────────┴───────────────────────┐
          │                                      │
          ▼                                      ▼
┌──────────────────────┐              ┌──────────────────────────┐
│  WHISPER LARGE v3    │              │  AZURE PRONUNCIATION API │
│  (Self-Hosted GPU)   │              │  (Targeted Audio Call)   │
│  ├── Full Transcript │              │  ├── Phoneme Accuracy    │
│  ├── Word Timestamps │              │  ├── Word Stress         │
│  └── Confidence Data │              │  └── Pronunciation Band  │
└───────┬──────────────┘              └───────────┬──────────────┘
        │                                         │
        ├──────────────────────────┐              │
        │                         │              │
        ▼                         ▼              │
┌───────────────────┐   ┌──────────────────────┐ │
│  FLUENCY ENGINE   │   │  LLM API             │ │
│  (Python — Local) │   │  (Claude Haiku /     │ │
│                   │   │   GPT-4o mini)        │ │
│  ├── Speech Rate  │   │                      │ │
│  ├── Pause Stats  │   │  ├── LR Band + Notes │ │
│  └── FC Score     │   │  └── GRA Band + Errs │ │
└───────┬───────────┘   └──────────┬───────────┘ │
        │                          │              │
        └──────────────────────────┴──────────────┘
                                   │
                                   ▼
              ┌────────────────────────────────────┐
              │   SCORE AGGREGATOR \& REPORT ENGINE  │
              │   ├── Normalize all to Band 1–9    │
              │   ├── Compute weighted overall      │
              │   ├── Generate detailed report      │
              │   └── Persist → PostgreSQL           │
              └────────────────────────────────────┘
```

\---

#### 3.2.5 How It Grades the 4 Criteria

|Criterion|Mechanism|Accuracy Level|
|-|-|-|
|**Pronunciation (P)**|Original audio segment passed to Azure Pronunciation Assessment. Whisper transcript is supplied as the reference text to improve forced-alignment accuracy. Returns phoneme-level score mapped to IELTS Band.| Very Good|
|**Fluency \& Coherence (FC)**|**Fluency:** Mathematically derived from Whisper word timestamps via the ENGONOW Fluency Engine (speech rate, pause analysis, articulation rate). **Coherence:** LLM evaluates transcript structure, discourse marker usage, and topic development against IELTS FC descriptors.| Very Good|
|**Lexical Resource (LR)**|Whisper transcript submitted to Claude Haiku / GPT-4o mini with structured IELTS LR rubric prompt. Returns Band score, specific vocabulary observations, and improvement guidance.| Very Good|
|**Grammatical Range \& Accuracy (GRA)**|Transcript submitted to LLM with GRA-specific rubric. Returns Band score, classified error types (tense, agreement, clause structure), frequency count, and corrected example sentences.| Very Good|

\---

#### 3.2.6 Pros

**Business Benefits:**

* **Estimated 65–75% reduction in per-test API cost** compared to Option 1 — directly improving unit economics and product margin from Day 1
* **Builds proprietary technical IP:** The custom Fluency Calculation Engine, Whisper deployment pipeline, and IELTS-calibrated prompt library are defensible internal assets that competitors cannot replicate by simply purchasing API access
* **Reduced vendor dependency:** Only pronunciation and LLM calls use external APIs; transcription infrastructure is fully owned
* **Improved data privacy posture:** Audio transcription occurs on ENGONOW's own servers; only targeted audio segments and text are sent to external APIs — significantly reducing data exposure
* **Phase 2 migration path is built-in:** The modular architecture allows Azure Pronunciation Assessment to be replaced with a fine-tuned local model as volume grows, without rebuilding the pipeline

**Technical Benefits:**

* Whisper Large v3 achieves state-of-the-art WER (Word Error Rate) for non-native English, with benchmarked performance of approximately 5–9% WER for Vietnamese-accented speech — sufficient for high-quality LR/GRA transcript analysis
* Whisper word timestamp precision (\~50–100ms) is adequate for IELTS-relevant fluency metric calculation
* Celery-based async processing enables parallel execution of Fluency Engine, LLM calls, and Azure API — keeping total pipeline latency under 45 seconds for a 15-minute test
* Modular, containerized (Docker) deployment enables straightforward infrastructure maintenance and component-level updates
* Achievable within **10–12 weeks** with one backend engineer and one ML/DevOps engineer

\---

#### 3.2.7 Cons

* **Requires GPU compute infrastructure:** A self-hosted Whisper deployment adds a fixed monthly cost (\~$200–400 for a `g4dn.xlarge` instance) and introduces DevOps complexity not present in Option 1
* **STT deployment setup:** Containerizing and optimizing `faster-whisper` for production latency (target: <15 seconds for a 15-minute audio file) requires initial configuration effort and performance tuning
* **Fluency model requires examiner validation before production release:** The mathematical scoring model must be calibrated against a corpus of expert-rated IELTS samples (minimum 50 scripts across Bands 5–8) to ensure statistical alignment
* **Retains Azure dependency for pronunciation:** Though at significantly lower volume per test than Option 1, this remains a third-party dependency
* Development cost is moderately higher than Option 1 due to infrastructure setup

\---

#### 3.2.8 Estimated Cost Impact

|Cost Category|Estimate|Basis|
|-|-|-|
|Operational cost per test|**$0.09 – $0.18**|Azure Pronunciation (audio segment) + LLM tokens only|
|Operational cost at 1,000 tests/month|**$90 – $180/month**|API costs + \~$280–380 fixed infra|
|Operational cost at 5,000 tests/month|**$450 – $900/month**|API costs + \~$280–380 fixed infra|
|Total monthly cost at 1,000 tests/month|**\~$370 – $560/month**|All-in|
|Development cost|**Medium**|10–12 weeks, 1 backend + 1 ML engineer|
|Infrastructure overhead|**Medium**|1× GPU instance, managed DB, task queue|
|**Overall Rating**| MEDIUM Operational /  MEDIUM Development|—|

\---

\---

### OPTION 3: Fully Self-Hosted Open-Source Stack

> \*"Zero External API Dependency — Maximum Long-Term Control"\*

\---

#### 3.3.1 Approach Overview

This option eliminates all commercial API dependencies. Every component — transcription, pronunciation evaluation, fluency analysis, and linguistic scoring — is deployed on ENGONOW's own infrastructure using open-source models and frameworks. There are zero marginal API costs per test.

\---

#### 3.3.2 Technical Stack

|Component|Technology|Type|
|-|-|-|
|Speech-to-Text|OpenAI Whisper Large v3 (`faster-whisper`)|Open-Source|
|Pronunciation (Phoneme-Level)|Montreal Forced Aligner (MFA) v3 + CMU Pronouncing Dictionary|Open-Source|
|Pronunciation (Alternative)|wav2vec 2.0 fine-tuned for English phoneme recognition|Open-Source|
|Fluency Engine|Custom Python (Whisper timestamps) — same as Option 2|Open-Source / Proprietary|
|Lexical Resource + GRA|LLaMA 3.1 8B Instruct (quantized GGUF) or Mistral 7B v0.3|Open-Source|
|Grammar Annotation|LanguageTool (self-hosted, Java/REST)|Open-Source|
|GPU Compute|AWS EC2 `g5.xlarge` or `g4dn.2xlarge` (2–4× GPU)|Cloud Infrastructure|
|Backend|Python / FastAPI + Celery + Redis|Open-Source|
|Database|PostgreSQL (self-managed)|Open-Source|

\---

#### 3.3.3 How It Grades the 4 Criteria

|Criterion|Mechanism|Accuracy Level|
|-|-|-|
|**Pronunciation (P)**|Montreal Forced Aligner aligns the audio stream to the transcript at phoneme level, producing per-phoneme confidence scores. These are compared against the CMU Pronouncing Dictionary's canonical phoneme sequences. Mismatch patterns are mapped to IELTS Pronunciation Band descriptors. Alternatively: wav2vec 2.0 outputs phoneme probability distributions compared against expected sequences.| Good (with calibration)|
|**Fluency \& Coherence (FC)**|Identical to Option 2: Whisper timestamp-based mathematical computation. Coherence via local LLaMA/Mistral inference.| Very Good|
|**Lexical Resource (LR)**|Full transcript processed by self-hosted LLaMA 3.1 8B / Mistral 7B with IELTS-specific system prompt. Returns Band score and vocabulary feedback via local GPU inference.| Good|
|**Grammatical Range \& Accuracy (GRA)**|LLaMA/Mistral for holistic GRA scoring. LanguageTool provides deterministic grammar error detection and classification as a supplementary signal.| Good|

\---

#### 3.3.4 Pros

**Business Benefits:**

* **Zero marginal API cost per test** — all variable cost is eliminated; only fixed infrastructure expenses apply
* **Maximum data privacy** — no learner audio, transcript, or personal data leaves ENGONOW's own servers; full compliance with PDPD 13/2023 without external DPA negotiations
* **Complete IP ownership** — every model weight, scoring function, and inference pipeline is fully proprietary
* Highly favorable unit economics at scale: above \~8,000 tests/month, Option 3's all-in cost falls below Options 1 and 2
* Positions ENGONOW for future fine-tuning on proprietary learner data — a defensible long-term AI moat

**Technical Benefits:**

* Full model customization: LLaMA/Mistral can be fine-tuned on IELTS-certified scoring corpora for criterion-specific accuracy improvement
* No API rate limits, no latency from external network calls
* Complete audit trail of every model inference decision

\---

#### 3.3.5 Cons

**This option is explicitly NOT recommended for the Phase 1 MVP for the following reasons:**

* **Highest engineering complexity of the three options.** Requires concurrent expertise in ASR deployment, forced phoneme alignment, LLM quantization and inference optimization, and NLP pipeline engineering. This is a multi-specialist undertaking, not a single-engineer project.
* **LLaMA 3.1 8B and Mistral 7B are materially less capable than GPT-4o or Claude 3.5 for nuanced rubric-based scoring.** The performance gap is most pronounced at Band 7–9 discrimination — precisely the range most important for ENGONOW's advanced learners. Serving high-Band learners with an under-powered local LLM risks credibility damage.
* **Montreal Forced Aligner setup for non-native Vietnamese-accented English is non-trivial.** It requires a validated acoustic model, G2P (Grapheme-to-Phoneme) configuration, and a labeled pronunciation dataset for error pattern calibration. This is a 4–6 month engineering effort in itself.
* **The 3-month MVP timeline is HIGH RISK.** The aggregate scope of deploying a multi-GPU stack, MFA pipeline, local LLM, and LanguageTool integration simultaneously exceeds what a small team can safely deliver with production-grade quality.
* **Infrastructure management overhead is substantial** — GPU memory management, model version control, inference server monitoring (e.g., NVIDIA Triton), and database performance tuning all require dedicated operational attention.

\---

#### 3.3.6 Estimated Cost Impact

|Cost Category|Estimate|Basis|
|-|-|-|
|Operational cost per test|**\~$0.01 – $0.04**|Compute amortization only|
|Operational cost at 1,000 tests/month|**\~$700 – $1,300/month**|High fixed infrastructure (unfavorable at low volume)|
|Operational cost at 5,000 tests/month|**\~$750 – $1,400/month**|Fixed cost; better per-unit economics|
|Break-even vs. Option 2|**\~8,000 – 12,000 tests/month**|Volume at which Option 3 becomes cost-superior|
|Development cost|**High**|18–24 weeks, 3+ engineers|
|Infrastructure overhead|**High**|Multi-GPU cluster: \~$700–1,200/month|
|**Overall Rating**| LOW Operational at Scale /  HIGH Development|—|

\---

\---

## 4\. OPTIONS COMPARISON MATRIX

|Evaluation Dimension|Option 1: Full Commercial|Option 2: Hybrid |Option 3: Full Open-Source|
|-|:-:|:-:|:-:|
|**Pronunciation Accuracy**||||
|**Fluency Accuracy**||||
|**Lexical Resource Accuracy**||||
|**Grammar Accuracy**||||
|**Cost per Test (Operational)**| $0.40–$0.80| $0.09–$0.18| $0.01–$0.04|
|**Monthly All-In @ 1K Tests**| \~$550–$950| \~$370–$560| \~$700–$1,300|
|**Monthly All-In @ 5K Tests**| \~$2,300–$4,500| \~$730–$1,280| \~$750–$1,400|
|**3-Month MVP Feasibility**| High| High| Low|
|**Development Complexity**| Low| Medium| High|
|**Time to Production**| 6–8 weeks| 10–12 weeks| 18–24 weeks|
|**GPU Infrastructure Required**| None| 1× GPU| Multi-GPU|
|**Vendor Lock-In Risk**| High| Moderate| None|
|**Data Privacy Level**| Moderate| Good| Excellent|
|**Long-term Scalability (Cost)**| Expensive| Good| Excellent|
|**Proprietary IP Created**| None| Significant| Extensive|
|**Maintenance Overhead**| Low| Medium| High|
|**Recommended for MVP**| Over-cost| **YES**| Over-scope|

\---

\---

## 5\. CONSULTANT'S DEFINITIVE RECOMMENDATION

### &#x20;Invest in Option 2: Hybrid Architecture for Phase 1 MVP

\---

### 5.1 Recommendation Rationale

After rigorous evaluation of all three architectural options against ENGONOW's defined constraints — a **3-month MVP delivery window**, a **limited engineering team of 2**, a **budget-conscious operational model**, and an **absolute requirement for academically credible scoring** — this consultancy issues an unambiguous recommendation:

> \*\*ENGONOW should invest in Option 2: Hybrid Architecture for the Phase 1 MVP.\*\*

The justification rests on five strategic pillars:

\---

**Pillar 1: It Directly Protects ENGONOW's Most Valuable Asset — Institutional Credibility**

An English preparation center's reputation is its primary commercial asset. Learners and their families make significant financial and time investments based on trust in the center's assessment quality. Option 2 retains Azure Pronunciation Assessment — the industry benchmark for non-native phoneme analysis — precisely where accuracy failure would be most visible and most damaging. Cutting corners on pronunciation scoring (as a pure confidence-score approach would do) risks the scenario where a learner receives a Band 7.0 Pronunciation score from ENGONOW's system and a Band 5.5 from the actual IELTS examiner. That discrepancy destroys trust and generates churn. Option 2 is designed to prevent this outcome.

\---

**Pillar 2: The Cost Savings Are Substantial and Immediately Material**

At a conservative launch volume of 1,000 tests/month, Option 2 saves approximately **$180 – $390 per month** over Option 1 in direct API costs. Over the first year of operation, this represents a saving of **$2,200 – $4,700 annually** — enough to cover the entire MVP development cost differential. As volume grows, these savings compound. The investment in Option 2's slightly higher development complexity has a payback period of under 6 months.

\---

**Pillar 3: It Builds Proprietary Technical IP — The Foundation of a Defensible Competitive Moat**

Option 1 produces no internal intellectual property. Option 2 produces three proprietary assets: (1) the ENGONOW Fluency Calculation Engine — a tunable, data-driven scoring model; (2) the Whisper deployment and accent-optimization pipeline; and (3) the IELTS-calibrated LLM prompt library. These assets are increasingly valuable as ENGONOW collects real learner data. Option 1 cannot be differentiated by any competitor with a credit card. Option 2 begins the process of building a system that cannot be trivially replicated.

\---

**Pillar 4: The MVP Timeline is Achievable Without Engineering Risk**

Option 2 can be safely delivered in **10–12 weeks** with the existing team. Option 3's 18–24 week timeline — with its multi-GPU infrastructure, MFA phoneme pipeline, and local LLM optimization requirements — carries substantial delivery risk for a 3-month MVP mandate. Delayed launch costs ENGONOW revenue and market opportunity. Option 2 is the highest-confidence path to an on-time, production-quality release.

\---

**Pillar 5: It is Explicitly Designed as a Phase 2 Springboard**

Option 2 is not a permanent endpoint — it is an engineered bridge. Every component of the Hybrid Architecture is independently replaceable. The Azure Pronunciation API is a slot that can be filled, in Phase 2, with a fine-tuned `wav2vec 2.0` model trained on ENGONOW's own growing corpus of scored learner audio. The commercial LLM calls can be replaced, in Phase 3, with a domain-fine-tuned local model when volume justifies the infrastructure investment. Option 2 enables ENGONOW to **generate revenue while building toward Option 3** — rather than gambling MVP launch on Option 3's unproven complexity.

\---

### 5.2 Strategic Migration Roadmap

|Phase|Timeline|Architecture State|Primary Goal|
|-|-|-|-|
|**Phase 1 — MVP**|Months 1–3|Option 2 Hybrid as specified|Launch, validate accuracy, generate revenue|
|**Phase 2 — Optimization**|Months 4–9|Replace Azure Pronunciation with fine-tuned wav2vec 2.0 (trained on ENGONOW accent-labeled corpus)|Eliminate pronunciation API cost; improve accent-specific accuracy|
|**Phase 3 — Full Ownership**|Months 10–18|Migrate LLM calls to fine-tuned domain-specific model; full Option 3 stack|Zero marginal API cost; maximum competitive differentiation|

\---

### 5.3 Post-Approval Action Plan (Phase 1)

|Week|Milestone|Owner|
|-|-|-|
|**Week 1**|Provision AWS EC2 `g4dn.xlarge`; deploy `faster-whisper` via Docker; performance baseline testing|ML/DevOps Engineer|
|**Week 2**|Integrate Azure Pronunciation Assessment API; build audio segmentation and format normalization pipeline|Backend Engineer|
|**Week 3–4**|Develop and unit-test ENGONOW Fluency Calculation Engine; validate against 30 expert-rated IELTS sample scripts|ML/DevOps Engineer|
|**Week 5–6**|Design and calibrate IELTS LR/GRA prompt library; A/B test Band score output against human examiner ratings on 50-script corpus|Backend Engineer + Examiner Consultant|
|**Week 7–8**|Build scoring aggregation engine, Band normalization function, and student feedback report generator|Backend Engineer|
|**Week 9–10**|Full system integration testing; load testing (concurrent test simulation); latency optimization|Both Engineers|
|**Week 11**|Staged rollout to pilot cohort (30–50 learners); examiner blind validation study|Both + Academic Director|
|**Week 12**|Production hardening; monitoring dashboards; documentation; Board sign-off for full launch|Both Engineers|

\---

### 5.4 Phase 1 Budget Summary

|Budget Line Item|Estimated Cost (3 months)|
|-|-|
|AWS EC2 `g4dn.xlarge` (on-demand, 3 months)|\~$750 – $950|
|AWS S3 + RDS PostgreSQL (storage/DB)|\~$150 – $250|
|Azure Speech API (development, validation, launch testing)|\~$200 – $350|
|LLM API — Claude Haiku / GPT-4o mini (dev + early launch)|\~$150 – $250|
|Examiner validation corpus consultation (50 scripts)|\~$300 – $500|
|**Total Phase 1 Infrastructure \& API Budget**|**\~$1,550 – $2,300**|
|**Estimated Monthly Operational Cost at Launch (1K tests)**|**\~$370 – $560/month**|

\---

\---

## 6\. RISK REGISTER

|Risk|Likelihood|Impact|Mitigation Strategy|
|-|:-:|:-:|-|
|Whisper Large v3 WER insufficient for Vietnamese accent → degrades LR/GRA quality|Medium|High|Benchmark on 50-sample Vietnamese-accent IELTS corpus before architecture commitment; fallback to Azure STT at comparable cost if WER > 12%|
|Fluency scoring model misaligned with certified IELTS rubric|Medium|High|Mandatory 3-examiner blind validation study on 50 scored scripts (Bands 5–8) prior to production release; recalibrate weights if Pearson r < 0.80|
|Azure Pronunciation API delivers inconsistent results for strong Vietnamese accent|Low-Medium|High|Validate with 30-sample accent corpus pre-integration; maintain Microsoft Azure technical support contract during MVP|
|LLM prompt inconsistency in Band score output|Medium|Medium|Enforce `temperature=0`, structured JSON schema output; implement human-in-loop audit for first 500 production tests; automated confidence-interval flagging|
|AWS GPU instance availability or cost spike|Low|Medium|Pre-purchase 6-month Reserved Instance for 40–60% cost reduction; maintain Spot Instance fallback configuration|
|Vietnam PDPD 13/2023 compliance challenge for data sent to Azure/OpenAI|Low-Medium|High|Engage legal counsel for DPA review; evaluate Azure Vietnam region availability; implement audio anonymization (strip metadata) before external API transmission|
|Team capacity overrun on 12-week timeline|Low-Medium|Medium|Week 6 scope review checkpoint; pre-identify one external contractor for Whisper deployment support if needed|

\---

\---

