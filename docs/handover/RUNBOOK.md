# ENGONOW Smart LMS — Production Runbook & Incident Response

## 1. Overview
This Runbook defines standard operating procedures for on-call Site Reliability Engineers (SREs) and MLOps Engineers responding to operational incidents, statistical drift alerts, and infrastructure failures in the ENGONOW Smart LMS platform.

---

## 2. Incident Response Playbooks

### Playbook 1: CUSUM Drift Alert & Automatic Drift Hold (`drift_hold = True`)

#### Symptoms:
- Prometheus alert: `CusumDriftAlert` firing.
- Kafka alert published on topic: `calibration.alerts.v1`.
- System state: `drift_hold = True` in Redis key `cusum:drift_hold`.
- Automated AI scoring halted or routed to `AI_AUTO_UNCALIBRATED` pending manual examiner adjudication.

#### Root Causes:
1. **$C^+$ Upper Arm Breach ($C^+ \ge 2.50$)**: Model accuracy degradation or prompt drifting (scoring higher or lower than ground-truth benchmark).
2. **$C^-$ Lower Arm Breach ($C^- \le -2.50$)**: Upstream data corruption, missing rubric criteria, or sudden formatting changes.

#### Resolution Steps:
1. **Inspect Active CUSUM Drift State**:
   ```bash
   docker exec -it engonow-redis redis-cli -a $REDIS_PASSWORD HGETALL cusum:state:WRITING:TASK_ACHIEVEMENT
   ```
2. **Review Recent Scoring Discrepancies**:
   Query the Golden Calibration Corpus benchmark evaluation to identify discordant criterion:
   ```bash
   python scripts/calibration/run_benchmark.py --split TUNING --subsystem WRITING
   ```
3. **Calibrate or Update Model Baseline**:
   - If model output has systematically shifted, compute new offset calibration parameters via `AutoCalibrator`.
   - Update `calibration_config_writing.json` and generate an updated configuration hash.
4. **Clear Drift Hold State**:
   ```bash
   docker exec -it engonow-redis redis-cli -a $REDIS_PASSWORD SET cusum:drift_hold "false"
   ```

---

### Playbook 2: All AI Providers Circuit Breaker `OPEN` (Failover Exhaustion)

#### Symptoms:
- `/health` endpoint returns `{"status": "DOWN", "components": {"aiProviders": {"overallStatus": "DOWN"}}}`.
- Application error logged: `RuntimeError("ALL_PROVIDERS_UNAVAILABLE")`.
- Submissions accumulate in `PENDING` status.

#### Root Causes:
1. Upstream outage or quota exhaustion across both Google Gemini and Azure OpenAI / Groq.
2. Expired API tokens or firewall egress blocking.

#### Resolution Steps:
1. **Check Circuit Breaker States & Failure Counters**:
   Inspect logs for `[CIRCUIT BREAKER]` and `[SELECTOR EXHAUSTION]`:
   ```bash
   docker compose -f docker-compose.prod.yml logs --tail=100 ai-worker | grep "CIRCUIT"
   ```
2. **Verify Upstream Cloud Status & Quota**:
   - Verify Google AI Studio / Vertex AI quota allocation.
   - Verify Azure OpenAI deployment quotas and endpoint availability.
3. **Force Canary Probe Test**:
   The circuit breaker automatically schedules synthetic canary probes on exponential backoff (30s $\rightarrow$ 60s $\rightarrow$ 120s $\rightarrow$ 300s). Once upstream recovers, the canary probe transitions the provider to `HALF_OPEN` and ramps traffic (10% $\rightarrow$ 50% $\rightarrow$ 100%).
4. **Emergency Key Rotation**:
   Update `.env` with emergency backup credentials and reload the container:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --no-deps ai-worker
   ```

---

### Playbook 3: Outbox Event Relay Backlog Growth

#### Symptoms:
- Metric `outbox_events_pending_total` continuously increasing.
- Learner submissions remain in `PENDING` state and do not progress to `PROCESSING`.

#### Root Causes:
1. Kafka broker connection failure or partition leader unavailable.
2. Outbox relay scheduler stalled or encountering locking contention.

#### Resolution Steps:
1. **Verify Kafka Broker Health**:
   ```bash
   docker exec -it engonow-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
   ```
2. **Inspect Outbox Table for Stalled Locked Events**:
   ```sql
   SELECT status, COUNT(*) FROM outbox_events GROUP BY status;
   -- Identify events stuck in IN_FLIGHT
   SELECT id, aggregate_id, retry_count, last_error FROM outbox_events WHERE status = 'FAILED' LIMIT 10;
   ```
3. **Trigger Manual Outbox Relay Flush**:
   Restart the LMS Core scheduler or invoke the admin flush endpoint:
   ```bash
   docker compose -f docker-compose.prod.yml restart lms-core
   ```

---

### Playbook 4: SSE Client Connection Dropouts & Proxy Buffering

#### Symptoms:
- Frontend client receives initial status event but misses terminal `SCORED` event.
- Client repeatedly reconnects every few seconds.

#### Root Causes:
1. Upstream reverse proxy (Nginx, Cloudflare, AWS ALB) buffering HTTP responses instead of streaming.
2. Network timeout dropping idle TCP connections.

#### Resolution Steps:
1. **Verify Response Headers**:
   Ensure `X-Accel-Buffering: no` and `Cache-Control: no-cache, no-transform` headers are present:
   ```bash
   curl -i -N http://localhost:8080/api/v1/writing-submissions/<UUID>/events
   ```
2. **Verify Scheduled Heartbeat Pings**:
   Verify that `sendKeepAlivePings()` emits `: ping\n\n` comments every 25 seconds in `lms-core` logs.
3. **Verify Redis Pub/Sub Subscriptions**:
   ```bash
   docker exec -it engonow-redis redis-cli -a $REDIS_PASSWORD PUBSUB CHANNELS "sse:submission:*"
   ```
