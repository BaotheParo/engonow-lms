# ENGONOW Smart LMS — Known Limitations & Technical Trade-offs

## 1. Overview
This document provides a transparent, engineering-level breakdown of current platform limitations, algorithmic constraints, and planned roadmap items for future development sprints.

---

## 2. Technical Limitations & Algorithmic Constraints

### 1. Whisper Word-Level Alignment Precision Under Fast Speech
- **Constraint**: Faster-Whisper uses dynamic time warping (DTW) on cross-attention weights to estimate word timestamps. Under extremely rapid connected speech (> 180 WPM) or severe ambient background noise, word boundary timestamps can jitter by $\pm 50\text{ms}$.
- **Mitigation**: Pauses shorter than $0.25\text{s}$ are explicitly ignored in `FluencyEngine`, absorbing timestamp jitter and preventing false micro-pause penalties.
- **Roadmap Item**: Integrate dedicated CTC-forced aligners (e.g. Wav2Vec2 or Montreal Forced Aligner) for sub-10ms phoneme alignment precision in Phase 5.1.

---

### 2. Goodness-of-Pronunciation (GOP) Non-Native Accent Sensitivity
- **Constraint**: The rule-based GOP spectral classifier focuses on standard canonical Cambridge / General American / RP phonology. Certain legitimate regional accents (e.g. Scottish rhotic vowels, Australian broad diphthongs, Indian retroflex stops) may score lower on standard GOP acoustic heuristics.
- **Mitigation**: Final pronunciation scores are blended between acoustic GOP metrics and LLM multimodal phonetic analysis, dampening false-positive penalties.
- **Roadmap Item**: Train multi-accent acoustic acoustic models calibrated across diverse L1 language transfer corpora.

---

### 3. Redis Pub/Sub Fire-and-Forget Architecture
- **Constraint**: Redis standard Pub/Sub operates on a fire-and-forget delivery guarantee. If a network blip occurs during the exact millisecond a message is published, connected clients on that channel could theoretically miss the broadcast event.
- **Mitigation**: Implemented **Immediate Current-State Database Replay**. Upon reconnecting, the client immediately queries the database for current status. Furthermore, the standard REST `GET /result` endpoint remains fully operational as a permanent fallback.
- **Roadmap Item**: Upgrade to Redis Streams with consumer groups if persistent message acknowledgment becomes necessary.

---

### 4. Single-Node Kafka KRaft Deployment Profile in Compose
- **Constraint**: The `docker-compose.prod.yml` defines a single-node KRaft broker (`replication.factor = 1`) suitable for small-to-medium deployments or staging environments.
- **Mitigation**: Production enterprise deployments should deploy Kafka onto a multi-node Kubernetes / MSK cluster with replication factor 3 and `min.insync.replicas = 2`.

---

### 5. Multi-Process Metric File Cleanup on Abrupt SIGKILL
- **Constraint**: If an AI Worker process is terminated violently via `SIGKILL` (bypassing Gunicorn's `child_exit` hook), dead worker metric files in `PROMETHEUS_MULTIPROC_DIR` may linger until container restart.
- **Mitigation**: The directory is mounted on a temporary `/tmp/prometheus_multiproc` filesystem which resets on container restart.
