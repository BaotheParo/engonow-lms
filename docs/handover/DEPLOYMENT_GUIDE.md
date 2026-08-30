# ENGONOW Smart LMS — Production Deployment Guide

## 1. Executive Summary & Architecture Overview
This document provides the standard operating procedures for provisioning, configuring, migrating, verifying, and rolling back the ENGONOW Smart LMS ecosystem across containerized production environments.

The topology consists of 8 core services:
1. **PostgreSQL 16**: Primary relational storage with hybrid JSONB domain attributes.
2. **Redis 7**: Distributed state management, CUSUM drift checkpoints, and SSE dynamic Pub/Sub fan-out.
3. **Apache Kafka 3.8 (KRaft)**: Event broker executing the Transactional Outbox/Inbox asynchronous scoring pipeline.
4. **Confluent Schema Registry 7.7.0**: Avro schema governance and compatibility enforcement.
5. **Java LMS Core (Spring Boot 3.2, JDK 21)**: Domain logic, Outbox Relay, Security RBAC, SSE streaming, and Prometheus metrics.
6. **Python AI Worker (Python 3.12, Gunicorn)**: Multimodal acoustic engine (Fluency + GOP + Stress + Intonation), multi-provider resilience router, and CUSUM monitor.
7. **Prometheus 2.54**: Centralized metrics collection engine.
8. **Grafana 11.2**: Executive KPI, Acoustic DSP, and Psychometric Drift dashboards.

---

## 2. Environment Variables Catalog

| Variable Name | Component | Required | Default / Example | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `POSTGRES_DB` | Postgres / LMS / AI | Yes | `engonow_db` | Primary database name |
| `POSTGRES_USER` | Postgres / LMS / AI | Yes | `engonow_app` | Database username |
| `POSTGRES_PASSWORD` | Postgres / LMS / AI | Yes | `[SECURE_PASSWORD]` | Database password |
| `REDIS_PASSWORD` | Redis / LMS / AI | Yes | `[SECURE_PASSWORD]` | Redis authentication password |
| `KAFKA_BOOTSTRAP_SERVERS` | LMS Core / AI Worker | Yes | `kafka:9092` | Kafka cluster bootstrap URL |
| `GEMINI_API_KEY` | AI Worker | Yes | `AIzaSy...` | Primary Google Gemini LLM API Key |
| `AZURE_OPENAI_API_KEY` | AI Worker | Yes | `azure_secret...` | Fallback Azure OpenAI GPT-4o Key |
| `GROQ_API_KEY` | AI Worker | Optional | `gsk_...` | Low-latency Llama 3.3 70B Fallback Key |
| `PROMETHEUS_MULTIPROC_DIR` | AI Worker | Yes | `/tmp/prometheus_multiproc` | Multi-worker metric scratch directory |
| `GUNICORN_WORKERS` | AI Worker | Yes | `4` | Worker process concurrency |
| `GRAFANA_ADMIN_PASSWORD` | Grafana | Yes | `[SECURE_PASSWORD]` | Admin password for Grafana UI |

---

## 3. Database Migration Sequence (Flyway V1 - V7)

Database schema migrations are executed automatically on LMS startup via Flyway in strict sequential order:

- **`V1__init_schema.sql`**: Core user, role, authentication, and exam booking tables.
- **`V2__outbox_and_inbox.sql`**: Transactional Outbox and Inbox tables with atomic locking and idempotency tracking.
- **`V3__writing_domain.sql`**: `writing_submissions` and `writing_results` tables with hybrid JSONB `feedback_detail`.
- **`V4__speaking_domain.sql`**: `speaking_attempts` and `speaking_session_results` claim-check tables.
- **`V5__dlq_and_replay.sql`**: Dead Letter Queue audit trail and replay management.
- **`V6__calibration_golden_corpus.sql`**: Golden corpus items, human rating pool, Cambridge consensus reference scores, and immutability lock triggers.
- **`V7__realtime_sse_and_indexes.sql`**: Performance indexes for status lookups, audit timestamps, and SSE reconnect querying.

---

## 4. Production Deployment Procedure

### Step 1: Clone Repository and Prepare Configuration
```bash
git clone https://github.com/engonow/engonow-lms.git /opt/engonow-lms
cd /opt/engonow-lms
cp .env.example .env
# Edit .env and supply production secrets (API Keys, DB passwords)
chmod 600 .env
```

### Step 2: Build & Start Containerized Ecosystem
```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml build --no-cache
docker compose -f docker-compose.prod.yml up -d
```

### Step 3: Monitor Container Health and Startup Logs
```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f lms-core ai-worker
```

---

## 5. Smoke Testing & Verification

1. **Verify Tiered Deep Health Status**:
   ```bash
   curl -s http://localhost:8000/health | jq .
   # Expected output: { "status": "UP", "components": { "postgresql": "UP", "redis": "UP", "kafka": "UP", ... } }
   ```

2. **Verify Java LMS Metrics Endpoint**:
   ```bash
   curl -s http://localhost:8080/actuator/prometheus | grep "writing_result_overall_band"
   ```

3. **Verify AI Worker Multi-Process Metrics**:
   ```bash
   curl -s http://localhost:8000/metrics | grep "ai_worker_evaluations_total"
   ```

4. **Verify SSE Real-Time Streaming Stream**:
   ```bash
   # Connect to an existing writing submission events stream:
   curl -N -H "Accept: text/event-stream" -H "X-User-Role: ROLE_ADMIN" http://localhost:8080/api/v1/writing-submissions/<UUID>/events
   ```

---

## 6. Rollback Playbook

If a critical deployment failure or uncalibrated scoring regression occurs:

1. **Stop Application Containers**:
   ```bash
   docker compose -f docker-compose.prod.yml stop lms-core ai-worker
   ```

2. **Revert Git Release Tag to Prior Stable Commit**:
   ```bash
   git checkout tags/release-v0.9-stable
   ```

3. **Rebuild and Restart Stable Services**:
   ```bash
   docker compose -f docker-compose.prod.yml build lms-core ai-worker
   docker compose -f docker-compose.prod.yml up -d --no-deps lms-core ai-worker
   ```

4. **Validate Health**:
   ```bash
   curl -s http://localhost:8080/health
   curl -s http://localhost:8000/health
   ```
