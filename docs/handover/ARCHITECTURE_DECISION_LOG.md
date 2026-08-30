# ENGONOW Smart LMS — Architecture Decision Record (ADR) Log

## ADR-001: Hybrid Relational + JSONB Storage Architecture

### Status
Accepted & Implemented (Sprint 1)

### Context
IELTS scoring requires querying structured scalar metrics (Overall Band, Criterion Bands 0.0–9.0, Evaluation Timestamp, Student ID) for analytics, indexing, and compliance, alongside deeply structured polymorphic diagnostic feedback (lexical suggestions, grammatical error spans, phonetic IPA alignments).

### Decision
Adopt a **Hybrid Relational + JSONB** PostgreSQL pattern:
- Core scalar scores, student identifiers, statuses, and audit timestamps are modeled as first-class SQL columns with B-Tree indexes.
- Granular error diagnostics, word-level annotations, and acoustic feature vectors are stored in `JSONB` columns with GIN indexing for flexible queryability without schema migration overhead.

### Consequences
- **Positive**: Strict relational constraints and foreign keys on business entities; schema evolution on AI diagnostic feedback without disruptive table migrations.
- **Negative**: Requires careful application-level schema validation via Avro/Pydantic before persisting JSONB blobs.

---

## ADR-002: Server-Sent Events (SSE) + Redis Pub/Sub over Full-Duplex WebSockets

### Status
Accepted & Implemented (Sprint 4)

### Context
Learners need real-time, low-latency scoring completion notifications. We evaluated WebSockets vs. Server-Sent Events (SSE) across horizontally scaled multi-instance clusters.

### Decision
Implement **Server-Sent Events (SSE)** with **Redis Pub/Sub** distributed fan-out:
- SSE operates over standard HTTP/1.1 and HTTP/2, natively traversing corporate firewalls, reverse proxies, and load balancers without protocol upgrade overhead.
- Redis Pub/Sub broadcasts completion events from Kafka consumer nodes to whichever specific application node holds the student's active HTTP SSE connection.
- Implemented **Immediate Current-State Replay**: On initial connection or reconnect, the server immediately queries PostgreSQL and emits current status prior to subscribing to Redis.

### Consequences
- **Positive**: Lightweight, unidirectional HTTP streaming; built-in browser reconnection; simple horizontal scaling via Redis channels.
- **Negative**: SSE is unidirectional (client-to-server messaging uses regular REST endpoints).

---

## ADR-003: Two-Sided Cumulative Sum (CUSUM) for Statistical Process Control

### Status
Accepted & Implemented (Sprint 3)

### Context
LLM providers silently update model checkpoints, potentially degrading scoring accuracy (target MAE $\le 0.50$). Static thresholding fails to detect subtle, cumulative drift over time.

### Decision
Implement pure mathematical **Two-Sided CUSUM Drift Detection** ($C^+$ Upper Arm for degradation, $C^-$ Lower Arm for anomaly/contamination) tracking each criterion independently:
$$C_t^+ = \max(0, C_{t-1}^+ + (z_t - k))$$
$$C_t^- = \min(0, C_{t-1}^- + (z_t + k))$$
where allowance $k = 0.50$ and decision threshold $h = 2.50$.
When $|C_t| \ge h$, the system emits a critical alert and automatically flags active drift hold in Redis.

### Consequences
- **Positive**: Detects gradual drift within 5–10 samples; prevents silent score inflation or deflation.
- **Negative**: Requires maintaining per-criterion CUSUM state and periodically checkpointing to database.

---

## ADR-004: Uncalibrated Model Governance & Fallback Routing

### Status
Accepted & Implemented (Sprint 4)

### Context
When primary LLM providers experience outages or quota exhaustion, fallback models (e.g. GPT-4o, Llama 3.3 70B) must step in. However, fallback models may not have validated MAE $\le 0.50$ psychometric calibration.

### Decision
Enforce a hard **Uncalibrated Model Governance Policy**:
- If an uncalibrated fallback model is selected, its evaluation result is explicitly tagged in the database with `evaluated_by = "AI_AUTO_UNCALIBRATED"` and `requires_human_review = True`.
- Such results are quarantined from affecting official learner records until reviewed by a certified human examiner.

### Consequences
- **Positive**: High platform availability without compromising Cambridge IELTS scoring integrity.
- **Negative**: Increased human examiner review queue during prolonged primary provider outages.

---

## ADR-005: Two-Layer Disfluency & G2P/GOP Phonetic Alignment

### Status
Accepted & Implemented (Sprint 4)

### Context
Accurately assessing IELTS Speaking Fluency and Pronunciation requires detecting natural pauses vs. disfluencies ("um", "uh") and IPA phoneme errors while ignoring technical audio dropouts.

### Decision
Implement a **Two-Layer Acoustic Engine**:
1. **Fluency & Continuity**:
   - Audio Continuity Gate inspects steep onset/offset cuts ($< 5\text{ms}$) into digital zero ($\text{RMS} < 10^{-5}$) to exclude network dropouts from cognitive pause penalties.
   - Reconciles Layer 1 (ASR transcript fillers) with Layer 2 (acoustic pitch autocorrelation periodicity $r_{\text{peak}} > 0.35$).
2. **Pronunciation & Stress**:
   - G2PEngine maps words to IPA and syllable stress patterns via CMUdict.
   - PronunciationEngine evaluates Goodness-of-Pronunciation (GOP) and syllable acoustic prominence ($0.40 \cdot \text{Dur}_z + 0.35 \cdot \text{RMS}_z + 0.25 \cdot \text{F0}_z$).

### Consequences
- **Positive**: Robust acoustic metrics resilient to Whisper transcription hallucination and VoIP packet loss.
- **Negative**: Requires frame-level signal processing on 16kHz audio waveforms.
