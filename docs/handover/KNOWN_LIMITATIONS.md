# KNOWN_LIMITATIONS.md — ENGONOW Smart LMS

## 1. Executive Overview

This document establishes technical debt transparency for project stakeholders, mentors, and the incoming engineering team. It defines the operational boundaries of the current system as built, distinguishes mitigated risk from unmitigated risk, and states the long-term architectural evolution path. A limitation listed here is not a defect to be silently tolerated — it is a known, bounded risk with an explicit owner and, where one exists, a mitigation whose actual scope is stated precisely rather than implied to be broader than it is.

## 2. Known Technical Limitations & Current Mitigations

### Whisper Word-Level Timestamp Granularity

**Problem:** ASR alignment drift on trailing phonemes and inter-word silence boundaries under noisy audio conditions. Cross-attention-based timestamps (as opposed to a dedicated forced aligner) carry roughly 100-300ms of boundary imprecision, which sits close enough to the 0.75-second cognitive-pause threshold to affect classification at the margin.

**Current Mitigation:** A short-circuit continuity gate excludes a response from automated scoring (`excluded_from_automated_scoring = true`) when dropout/artifact ratio exceeds 15% of total duration (`acoustic/continuity_gate.py`). CMUdict phoneme-fallback filtering reduces the impact of individual misaligned boundaries on aggregate pronunciation scoring. Micro-pauses shorter than 0.25s are explicitly absorbed in `FluencyEngine` (`acoustic/fluency_engine.py`). This mitigation bounds the *blast radius* of alignment drift; it does not eliminate the underlying imprecision, which remains present in every response that does not trip the 15% exclusion threshold.

### Redis Pub/Sub Ephemeral Messaging vs. WebSockets

**Problem:** Redis Pub/Sub operates on fire-and-forget semantics — a message published to a channel with zero active subscribers is dropped, not queued. A frontend client that loses network connectivity mid-stream misses any status event published during the disconnected interval.

**Current Mitigation:** PostgreSQL remains the persistent source of truth for submission status; client reconnection triggers an immediate snapshot read of current state before resubscribing to future events (`RealtimeDeliveryServiceImpl.java`), so a missed event never produces stale data indefinitely — only a delay until the client reconnects or explicitly polls `/result` (`/api/v1/writing/submissions/{id}`). This mitigation is complete for its stated scope (no student is permanently unable to retrieve a completed result); it does not make the real-time channel itself reliable, and should not be treated as one going forward.

### Prompt Injection & Adversarial Hallucination Vectors

**Problem:** Essay and transcript content is passed to the LLM as part of the evaluation prompt. A sophisticated adversarial candidate could embed instruction-like text (system-prompt overrides, fake structured-output fragments, or escaped JSON/XML attempting to alter how the model interprets the surrounding prompt) intended to manipulate the assigned score.

**Current Mitigation, stated precisely:** Pydantic v2 strict validators, fence-stripping regex, and the deterministic Python-side Cambridge rounding override each address a *different, narrower* problem than prompt injection itself, and should not be read as injection defense:
- Pydantic validation and fence-stripping harden the system against **malformed or unparseable output** — a structural robustness concern, not a content-manipulation concern.
- The deterministic rounding override (`providers/rounding.py` and `CambridgeRoundingUtil.java`) recomputes `overall_band` from the four reported criterion scores, which catches an injection attempt that directly falsifies the *aggregate* figure — but it does **not** independently verify the four criterion scores themselves against any ground truth. An injection that successfully inflates all four criterion scores together passes through this mitigation unaffected, since the override only checks arithmetic consistency between the aggregate and its components, not the components' correctness.

**This remains an open, unmitigated risk.** No content-level defense (adversarial-input detection, treating essay/transcript text as strictly non-instructional data at the model-input-handling layer, or output-plausibility bounds-checking against the independent acoustic/statistical signal) is implemented as of this document. CUSUM drift monitoring (`telemetry/cusum_detector.py`) provides a population-level backstop — a successful injection campaign at meaningful scale would eventually surface as anomalous drift — but offers no protection against a single manipulated submission, and no real-time detection at the point of scoring.

### Heavy Acoustic DSP Compute Latency

**Problem:** Librosa/Soundfile/Scipy-based processing (F0 pitch contour extraction, GOP phonetic scoring) is CPU-bound and spikes AI Worker CPU utilization under concurrent long-turn audio, particularly Part 2 responses exceeding two minutes.

**Current Mitigation:** Asynchronous Kafka consumer execution decouples submission ingest from scoring latency, so ingest-path availability is unaffected by DSP compute pressure; per-process semaphore limits (`WORKER_CONCURRENCY_LIMIT = 5`) and Gunicorn multi-worker configuration bound the blast radius of a CPU spike to the process experiencing it rather than exhausting host resources. This does not reduce the underlying per-response compute cost — it contains its effect on throughput and availability, not the cost itself.

## 3. Architectural Trade-offs & Accepted Debts

| Trade-off | Current choice | Accepted debt |
|---|---|---|
| Orchestration | Multi-stage Docker Compose, single-host topology (`docker-compose.prod.yml`) | No automatic node failover, no horizontal pod autoscaling, no rolling zero-downtime deploys — a Kubernetes/Helm migration is deferred, not rejected |
| Data store topology | Monolithic PostgreSQL shared schema serving both LMS Core entities and Outbox/Inbox tables | Outbox write volume and business-data write volume share the same database's I/O and lock contention envelope; a fully partitioned event-store database (separate from the transactional schema) would isolate this but is not currently implemented |
| Kafka broker clustering | Single-broker KRaft topology (`replication.factor = 1`) | Single point of failure at the broker layer under host crash; multi-broker quorum and partition replication are deferred to distributed Kubernetes deployment |

## 4. 12-Month Technical Roadmap

### Phase 1 (Near-term, Q1-Q2)

- Migration from Whisper's native cross-attention timestamps to a dedicated forced aligner (Wav2Vec2 CTC-based, or Kaldi/Montreal Forced Aligner), targeting substantially tighter phoneme-boundary precision than the current ~100-300ms drift. Sub-10ms precision is an aspirational target subject to confirmation against real audio conditions during implementation, not a guaranteed outcome of the migration itself — forced-aligner accuracy in published evaluations is typically reported as a percentage of boundaries within a tolerance window, not a uniform bound.
- Dual-channel WebSocket / Redis Streams implementation for bidirectional audio streaming with guaranteed delivery. This is a distinct capability from the existing SSE status-push channel (`RealtimeDeliveryServiceImpl.java`) and does not revisit that channel's SSE-over-WebSocket decision — SSE remains correct for unidirectional status notification; this item targets a different use case (live, bidirectional audio interaction) that the current channel was never intended to serve.

### Phase 2 (Mid-term, Q3)

- Fine-tuning a domain-specific small language model on the Golden Corpus, targeting a 70% reduction in external LLM API cost. Cost target is a roadmap objective, not a committed figure — realized savings depend on achieved accuracy parity with the current multi-provider setup, which the Gatekeeper process would need to validate independently before any production cutover.
- Multi-region Kafka cluster deployment with automatic cross-DC partition rebalancing.

### Phase 3 (Long-term, Q4)

- Multimodal video analysis for IELTS Speaking (facial micro-expression and eye-contact tracking). **Flagged explicitly:** official IELTS Speaking assessment is defined entirely by the four linguistic criteria (Fluency and Coherence, Lexical Resource, Grammatical Range and Accuracy, Pronunciation) — facial expression and eye contact are not part of that construct. Using these signals as scoring inputs, rather than as a separate engagement/analytics signal kept out of the band calculation, would introduce a real construct-validity and fairness risk: cultural variation in eye-contact norms, camera angle and lighting effects unrelated to speaking ability, and potential bias against neurodivergent candidates are all plausible failure modes. This item should not proceed into the scoring pipeline without dedicated construct-validity research and Academic Board review specifically addressing that risk, independent of its technical feasibility.
- Automated self-calibrating prompt optimization (a DSPy-style pipeline tied to CUSUM drift detection). **Tension with an established principle:** CUSUM drift remediation and the calibration workflow (`CALIBRATION_GUIDE.md` Section 6) currently treat a scoring-rubric or prompt change as a pedagogical decision requiring human sign-off, deliberately not automated end-to-end. Full autonomous prompt/rubric rewriting in response to drift would remove that human gate. If pursued, this should be scoped to a constrained action space under the existing sign-off workflow — for example, automated *proposal* of candidate changes for QA Lead review, or bounded auto-tuning of already-reviewed numeric parameters (such as `criterionLeniencyAdjustment` within pre-approved limits) — rather than autonomous changes to prompts or rubric thresholds without the three-step sign-off gate.
