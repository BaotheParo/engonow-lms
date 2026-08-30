#!/usr/bin/env bash
# ==============================================================================
# scripts/provision_kafka_topics.sh
# Idempotent shell wrapper to provision Kafka topics for ENGONOW LMS.
# ==============================================================================
set -euo pipefail

BOOTSTRAP_SERVERS="${1:-localhost:9092}"
ENVIRONMENT="${2:-dev}"

echo "================================================================================"
echo " ENGONOW KAFKA TOPIC TOPOLOGY PROVISIONER"
echo " Bootstrap Servers : ${BOOTSTRAP_SERVERS}"
echo " Environment       : ${ENVIRONMENT}"
echo "================================================================================"

# Execute Python AdminClient provisioner
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo "ERROR: Python is required to run the Kafka AdminClient provisioner."
    exit 1
fi

${PYTHON_CMD} scripts/provision_kafka_topics.py --bootstrap-servers "${BOOTSTRAP_SERVERS}" --env "${ENVIRONMENT}"
