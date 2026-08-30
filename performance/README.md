# ENGONOW LMS - Performance & Stress Testing Guide (Phase 4.5 / 4.6)

This directory contains load and stress test suites for the ENGONOW AI Writing & Speaking evaluation pipeline.

---

## 1. File Descriptor & Socket Limit Configuration

When executing high-concurrency benchmarks (e.g. **200 concurrent threads** across SSE streams and essay submissions in `jmeter_stress_test.jmx`), the default Linux file descriptor limit (`ulimit -n 1024`) will quickly cause socket exhaustion errors:
```text
java.net.SocketException: Too many open files
```

### Host/CI Runner Tuning
Before running JMeter, increase the file descriptor limits:
```bash
# In shell session
ulimit -n 65535

# Or persist in /etc/security/limits.conf
*    soft    nofile    65535
*    hard    nofile    65535
```

### Docker Container Configuration
If running JMeter or the application inside Docker containers, configure container `ulimits` in `docker-compose.yml`:
```yaml
services:
  app:
    # ...
    ulimits:
      nofile:
        soft: 65535
        hard: 65535
```

---

## 2. Running the JMeter Stress Test

Run the automated test script (which checks and applies `ulimit -n 65535`):
```bash
chmod +x performance/run_stress_test.sh
./performance/run_stress_test.sh
```

Or run JMeter directly in headless CLI mode:
```bash
ulimit -n 65535
jmeter -n \
  -t performance/jmeter_stress_test.jmx \
  -l performance/results/results.jtl \
  -e -o performance/results/dashboard
```

---

## 3. Metrics & Key SLA Thresholds

- **Acceptance SLA**: Response time $P95 < 2000\text{ ms}$ for `/api/v1/writing/submissions/submit` (HTTP 202).
- **Error Rate**: $0.00\%$ HTTP 5xx errors under 200 concurrent users.
- **SSE Stream Survival**: 100% of SSE connections survive without dropping thanks to the 25-second heartbeat ping (`: ping\n\n`) and non-blocking `ThreadPoolTaskScheduler`.
