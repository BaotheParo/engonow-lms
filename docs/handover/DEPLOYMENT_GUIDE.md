# DEPLOYMENT_GUIDE.md — ENGONOW Smart LMS

## 1. Prerequisites

| Tool | Minimum Version | Notes |
|---|---|---|
| Docker Engine | 25.x | Required for BuildKit-based multi-stage builds and `HEALTHCHECK` support used in both Dockerfiles |
| Docker Compose | v2 (CLI plugin) | Invoked as `docker compose`, not the legacy standalone `docker-compose` v1 binary |
| Git | 2.x | Repository checkout |

**Hardware — single-host deployment (all containers co-located):**

| Tier | vCPU | RAM | Disk |
|---|---|---|---|
| Minimum (staging / low-traffic) | 8 | 16 GB | 100 GB SSD |
| Recommended (production) | 16 | 32 GB | 250 GB SSD |

Kafka and PostgreSQL are the two most I/O-sensitive containers in this topology; provision SSD-backed storage, not network-attached spinning disk, for both volumes.

## 2. Architecture Topology

Containers provisioned by `docker-compose.prod.yml`, attached to the internal bridge network `engonow-net`:

| Container | Image / Build | Published Host Port | Container Port | Purpose / Role |
|---|---|---|---|---|
| `postgres` | `postgres:16-alpine` | `5432:5432` | 5432 | Primary relational store (LMS domain & Outbox/Inbox tables) |
| `redis` | `redis:7-alpine` | `6379:6379` | 6379 | In-memory cache, CUSUM drift state, and SSE pub/sub fan-out |
| `kafka` | `apache/kafka:3.8.0` (KRaft mode) | `9092:9092` | 9092 | Event broker executing asynchronous evaluation pipelines |
| `schema-registry` | `confluentinc/cp-schema-registry:7.7.0` | `8081:8081` | 8081 | Avro / JSON Schema governance registry |
| `lms-core` | Built from `Dockerfile.lms-core` | `8080:8080` | 8080 | Java Spring Boot LMS Core (Outbox Relay, REST, SSE, Actuator) |
| `ai-worker` | Built from `Dockerfile.ai-worker` | `8000:8000` | 8000 | Python AI Worker (Gunicorn/Uvicorn, Acoustic DSP, /health, /metrics) |
| `prometheus` | `prom/prometheus:v2.54.0` | `9090:9090` | 9090 | Prometheus metrics scraper (scrapes `lms-core:8080` and `ai-worker:8000`) |
| `grafana` | `grafana/grafana:11.2.0` | `3000:3000` | 3000 | Observability visualization & alert dashboards |

All containers communicate over `engonow-net` using service names (e.g. `postgres:5432`, `redis:6379`, `kafka:9092`, `lms-core:8080`, `ai-worker:8000`). While host ports are published in `docker-compose.prod.yml` for operator diagnostics, in production ingress environments external access should be restricted via security groups or reverse proxy (Nginx/Envoy).

## 3. Environment Variables Directory

All variables below are sourced from `.env` in the repository root (see `.env.example` for baseline template).

| Variable | Consumed By | Default / Fallback | Description |
|---|---|---|---|
| `POSTGRES_DB` | `postgres`, `lms-core`, `ai-worker` | `engonow_db` | Primary PostgreSQL database name |
| `POSTGRES_USER` | `postgres`, `lms-core`, `ai-worker` | `engonow_app` | Primary PostgreSQL username |
| `POSTGRES_PASSWORD` | `postgres`, `lms-core`, `ai-worker` | `engonow_secure_password` | Database password (secret) |
| `DATABASE_URL` | `ai-worker` | `postgresql://...` | Connection URI for asyncpg Python database pool |
| `REDIS_PASSWORD` | `redis`, `lms-core`, `ai-worker` | `engonow_redis_secret` | Redis authentication password (secret) |
| `REDIS_URL` | `ai-worker` | `redis://:...@redis:6379/0` | Async Redis connection URI for AI worker |
| `REDIS_HOST` | `lms-core` (fallback) | `redis` / `localhost` | Redis host when configured outside container network |
| `REDIS_PORT` | `lms-core` (fallback) | `6379` | Redis port |
| `KAFKA_BOOTSTRAP_SERVERS` | `lms-core`, `ai-worker` | `kafka:9092` / `localhost:9092` | Kafka bootstrap broker connection string |
| `GEMINI_API_KEY` | `ai-worker` | `""` | Primary Google Gemini LLM API Key (secret) |
| `GEMINI_API_KEYS` | `ai-worker` | Optional list | Comma-delimited Gemini API keys for quota round-robin |
| `GEMINI_MODEL` | `ai-worker` | `models/gemini-2.5-flash` | Gemini model resource path |
| `AI_MODEL_NAME` | `ai-worker` | `gemini-2.5-flash` | Canonical model identifier for provider routing |
| `GROQ_API_KEY` | `ai-worker` | `""` | Groq API Key for Whisper ASR and Llama 3.3 fallback (secret) |
| `WHISPER_API_KEY` | `ai-worker` | `""` | Alias fallback for Groq Whisper transcription |
| `AZURE_OPENAI_API_KEY` | `ai-worker` | `mock_key` | Azure OpenAI GPT-4o fallback key (secret) |
| `SPEAKING_AI_PROVIDER` | `ai-worker` | `GROQ_LOCAL` | Primary Speaking evaluation track (`GROQ_LOCAL` or `AZURE`) |
| `AZURE_SPEECH_KEY` | `ai-worker` | `NOT_CONFIGURED` | Azure Speech Services evaluation key |
| `AZURE_SPEECH_REGION` | `ai-worker` | `southeastasia` | Azure Speech Services region |
| `AZURE_SPEECH_LANGUAGE` | `ai-worker` | `en-US` | Azure Speech evaluation language |
| `WORD_CONFIDENCE_THRESHOLD` | `ai-worker` | `0.70` | Acoustic alignment confidence cutoff |
| `PAUSE_ANNOTATION_MIN_SEC` | `ai-worker` | `0.50` | Minimum silence duration (seconds) flagged as pause |
| `ENABLE_ACOUSTIC_DIAGNOSTICS`| `ai-worker` | `true` | Enables GOP, pause, and stress telemetry |
| `FALLBACK_SCORE_PR` | `ai-worker` | `4` | Fallback Pronunciation band score on sub-pipeline failure |
| `FALLBACK_SCORE_FC` | `ai-worker` | `4` | Fallback Fluency & Coherence band score |
| `FALLBACK_SCORE_GRA` | `ai-worker` | `4` | Fallback Grammar band score |
| `FALLBACK_SCORE_LR` | `ai-worker` | `4` | Fallback Lexical Resource band score |
| `BROKER_TYPE` | `lms-core`, `ai-worker` | `KAFKA` (prod) / `LOCAL` (test) | Event transport engine selector |
| `SPEAKING_REQUESTS_TOPIC` | `ai-worker` | `ielts-speaking-requests` | Ingestion topic for speaking evaluation requests |
| `SPEAKING_RESULTS_TOPIC` | `ai-worker` | `ielts-speaking-results` | Egress topic for completed speaking results |
| `WORKER_CONCURRENCY_LIMIT` | `ai-worker` | `5` | Semaphore max concurrency per worker process |
| `KAFKA_CONSUMER_GROUP` | `ai-worker` | `engonow-speaking-ai-workers` | Consumer group ID for AI worker fleet |
| `IELTS_WRITING_SYSTEM_PROMPT_PATH` | `ai-worker` | `providers/prompts/writing_system.txt` | File path to externalized IELTS Writing system prompt |
| `IELTS_WRITING_USER_PROMPT_PATH` | `ai-worker` | `providers/prompts/writing_user.txt` | File path to externalized IELTS Writing user prompt |
| `PROMETHEUS_MULTIPROC_DIR` | `ai-worker` | `/tmp/prometheus_multiproc` | Multi-worker metrics scratch directory |
| `GUNICORN_WORKERS` | `ai-worker` | `4` | Gunicorn worker concurrency for Uvicorn |
| `GRAFANA_ADMIN_USER` | `grafana` | `admin` | Grafana initial administrator username |
| `GRAFANA_ADMIN_PASSWORD` | `grafana` | `engonow_admin_secure` | Grafana administrator password (secret) |
| `CLOUDINARY_API_KEY` | `lms-core` | `fake-api-key-dev` | Cloudinary integration key for OMR image storage |
| `CLOUDINARY_API_SECRET` | `lms-core` | `fake-api-secret-dev` | Cloudinary API secret |

Secrets (all rows marked "secret" above) belong in a secrets manager (Vault, AWS/GCP Secrets Manager) in a hardened production environment; `.env` is the Docker Compose baseline mechanism, not the final word on secrets handling.

## 4. Database Migrations

Flyway migrations are located in `src/main/resources/db/migration/` and execute in strict numeric order (`V3` through `V7`), with baseline support enabled (`baseline-on-migrate: true`) for pre-existing tables:

| Migration File | Primary Tables & DDL Objects | Domain Purpose |
|---|---|---|
| `V3__create_writing_tables.sql` | `writing_submissions`, `writing_results` | IELTS Writing submissions, criteria scoring (TA, CC, LR, GRA), overall band, and JSONB `feedback_detail` |
| `V4__create_outbox_events_table.sql` | `outbox_events` | Transactional Outbox pattern table for reliable event dispatching via `OutboxRelayScheduler` |
| `V5__create_java_inbox_events_table.sql` | `inbox_events` | Transactional Inbox pattern table with unique `ux_java_inbox_idempotency_key` constraint |
| `V6__create_calibration_corpus_tables.sql` | `calibration_corpus_items`, `calibration_human_ratings`, `calibration_reference_scores` | Golden calibration corpus foundation, human rating pool, Cambridge consensus scores, and dataset split immutability locks |
| `V7__create_cusum_state_and_flags.sql` | `calibration_cusum_checkpoints`, `calibration_system_flags` | Real-time CUSUM drift checkpoints ($C^+, C^-$) and automated system `drift_hold` flags |

**Execution mechanism:** `lms-core` includes `flyway-core` with Spring Boot's auto-configuration active (`spring.flyway.enabled=true`). `FlywayMigrationInitializer` runs during `ApplicationContext` refresh before the server binds to port 8080:

```yaml
# src/main/resources/application.yml (relevant excerpt)
spring:
  flyway:
    enabled: true
    baseline-on-migrate: true
  datasource:
    url: ${SPRING_DATASOURCE_URL:jdbc:postgresql://localhost:5432/engonow_lms}
    username: ${SPRING_DATASOURCE_USERNAME:postgres}
    password: ${SPRING_DATASOURCE_PASSWORD:postgres}
```

If migration fails, context refresh fails, the container never becomes healthy, and the `HEALTHCHECK` directive in `Dockerfile.lms-core` (`wget -qO- http://localhost:8080/health || exit 1`) keeps it out of rotation.

## 5. Deployment Execution

```bash
# 1. Clone and configure
git clone <repository-url> engonow-lms
cd engonow-lms
cp .env.example .env
# populate .env per Section 3 before proceeding

# 2. Build images
docker compose -f docker-compose.prod.yml build lms-core ai-worker

# 3. Start infrastructure first, wait for health
docker compose -f docker-compose.prod.yml up -d postgres redis kafka schema-registry
docker compose -f docker-compose.prod.yml ps --format "table {{.Name}}\t{{.Status}}"
# confirm all four report (healthy) before proceeding

# 4. Start application and observability containers
docker compose -f docker-compose.prod.yml up -d lms-core ai-worker prometheus grafana

# 5. Confirm full stack health
docker compose -f docker-compose.prod.yml ps
```

`lms-core` and `ai-worker` both declare `depends_on` with `condition: service_healthy` against their infrastructure dependencies (`docker-compose.prod.yml`), so step 4 is safe to issue immediately after step 3 without a manual wait — Compose will not start either application container until Postgres, Redis, and Kafka report healthy.

## 6. QA & Smoke Testing

**Deep health check:**

```bash
# Spring Boot LMS Core Health
curl -s http://localhost:8080/actuator/health | jq .

# Python AI Worker Health (Gunicorn/Uvicorn runtime)
curl -s http://localhost:8000/health | jq .
```

Expected output:
- `lms-core`: `"status": "UP"` with database, redis, and disk space healthy.
- `ai-worker`: `{"status": "UP", "service": "engonow-ai-worker", "broker": "...", "provider": "..."}`.

**Kafka topic topology verification:**

```bash
# Verify topic creation via Kafka container CLI:
docker compose -f docker-compose.prod.yml exec kafka \
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```

Expected canonical topics provisioned by `scripts/provision_kafka_topics.py`:
- `engonow.writing.evaluation-requested.v1` (with `.dlq` and `.retry.30s`)
- `engonow.writing.evaluation-completed.v1` (with `.dlq`)
- `engonow.writing.evaluation-failed.v1` (with `.dlq`)
- `engonow.speaking.evaluation-requested.v1` (with `.dlq` and `.retry.30s`)
- `engonow.speaking.evaluation-completed.v1` (with `.dlq`)
- `engonow.speaking.evaluation-failed.v1` (with `.dlq`)

To provision or audit topics on-demand:
```bash
# Run topic topology provisioner script
python scripts/provision_kafka_topics.py --bootstrap-servers localhost:9092 --env prod
```

**SSE stream connectivity & Writing evaluation:**

```bash
# 1. Submit a test Writing evaluation
SUBMISSION_RESPONSE=$(curl -s -X POST http://localhost:8080/api/v1/writing/submissions/submit \
  -H "Authorization: Bearer $TEST_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "studentId": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    "taskType": "TASK2",
    "taskPrompt": "Some people believe that unpaid community service should be compulsory in high school. To what extent do you agree or disagree?",
    "essayText": "In contemporary society, the proposition of incorporating mandatory unpaid community service into high school curriculums has sparked considerable debate. Proponents contend that such initiatives foster civic responsibility and altruism, whereas opponents argue they place an undue burden on students already striving for academic excellence. This essay will examine both perspectives before presenting a reasoned conclusion."
  }')

SUBMISSION_ID=$(echo "$SUBMISSION_RESPONSE" | jq -r .submissionId)
echo "Submitted Writing ID: $SUBMISSION_ID"

# 2. Stream real-time status events (-N disables curl buffer)
curl -N -H "Authorization: Bearer $TEST_TOKEN" \
  "http://localhost:8080/api/v1/writing/submissions/${SUBMISSION_ID}/events"
```

Expected: an immediate `status: PENDING` or `status: PROCESSING` event on connect (current-state replay behavior), followed by a terminal `status: SCORED` or `status: FAILED` event once the AI worker publishes the evaluation result.

**Grafana dashboard population:**

```bash
curl -s -u admin:"$GRAFANA_ADMIN_PASSWORD" \
  http://localhost:3000/api/health
```

Then confirm in the Grafana UI that the three provisioned dashboards (Pipeline Health, MAE & Scoring Drift, Kafka/Outbox Lag) render non-empty panels within five minutes of the smoke-test traffic above.

## 7. Rollback Playbook

**Pre-deployment backup (execute before Step 2 of Section 5 on any production deployment):**

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U "$POSTGRES_USER" -F c -f /tmp/pre_deploy_backup.dump "$POSTGRES_DB"
docker compose -f docker-compose.prod.yml cp postgres:/tmp/pre_deploy_backup.dump ./backups/
```

**Application-only rollback (schema unaffected):**

```bash
docker compose -f docker-compose.prod.yml down lms-core ai-worker
docker compose -f docker-compose.prod.yml up -d --no-deps \
  lms-core:<previous-tag> ai-worker:<previous-tag>
```

**Full environment teardown:**

```bash
docker compose -f docker-compose.prod.yml down
# add -v only if volumes are also being discarded — this destroys
# postgres_data, redis_data, and kafka_data irreversibly
```

**Database restore (schema-breaking migration rollback):**

```bash
docker compose -f docker-compose.prod.yml exec postgres \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists \
  /tmp/pre_deploy_backup.dump
```

Flyway migrations in this project are forward-only — no `undo` migration exists for any of `V1`-`V7`. A schema-breaking migration is rolled back exclusively via the pre-deployment backup restore above, or via a new forward migration that reverses the change, never via a Flyway-native rollback command.
