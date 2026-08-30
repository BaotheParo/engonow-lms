#!/usr/bin/env bash
# ==============================================================================
# ENGONOW LMS - JMeter Stress Test Execution Script (200 Concurrent Threads)
# Phase 4.5 / 4.6 Stress Testing & Handover
# ==============================================================================
set -euo pipefail

echo "==> Configuring OS File Descriptor & Socket Limits..."

# 1. Raise File Descriptor Limit to prevent 'java.net.SocketException: Too many open files'
CURRENT_ULIMIT=$(ulimit -n)
TARGET_ULIMIT=65535

if [ "$CURRENT_ULIMIT" -lt "$TARGET_ULIMIT" ]; then
    ulimit -n "$TARGET_ULIMIT" 2>/dev/null || {
        echo "[WARNING] Could not raise ulimit -n to $TARGET_ULIMIT (current: $CURRENT_ULIMIT)."
        echo "          Ensure /etc/security/limits.conf or Docker container ulimits has: nofile 65535."
    }
fi
echo "==> Current open files limit: $(ulimit -n)"

# 2. Recommended Kernel socket tuning (Linux/CI runner)
# sysctl -w net.ipv4.tcp_tw_reuse=1 2>/dev/null || true
# sysctl -w net.ipv4.ip_local_port_range="1024 65535" 2>/dev/null || true

JMETER_PLAN="performance/jmeter_stress_test.jmx"
RESULTS_DIR="performance/results"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REPORT_DIR="${RESULTS_DIR}/dashboard_${TIMESTAMP}"
LOG_FILE="${RESULTS_DIR}/stress_test_${TIMESTAMP}.jtl"

mkdir -p "$RESULTS_DIR"

echo "==> Launching Headless JMeter Test with 200 Concurrent Users..."
echo "    Plan:       $JMETER_PLAN"
echo "    Results:    $LOG_FILE"
echo "    Dashboard:  $REPORT_DIR"

jmeter -n \
    -t "$JMETER_PLAN" \
    -l "$LOG_FILE" \
    -e -o "$REPORT_DIR" \
    -JHOST="${HOST:-localhost}" \
    -JPORT="${PORT:-8080}"

echo "==> Stress Test Completed Successfully. HTML Dashboard generated at: $REPORT_DIR"
