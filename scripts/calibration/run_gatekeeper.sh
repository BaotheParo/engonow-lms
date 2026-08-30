#!/usr/bin/env bash
# ==============================================================================
# scripts/calibration/run_gatekeeper.sh
# Executes candidate prompts/configs against the held-out GATEKEEPER dataset.
# ==============================================================================
set -euo pipefail

SUBSYSTEM="WRITING"
SPLIT="GATEKEEPER"
SNAPSHOT="snap-gatekeeper-v1"
CONFIG="calibration_config_writing.json"
CORPUS="data/golden_corpus_writing_init.json"
OUTPUT="reports/gatekeeper-run-latest.json"
MARKDOWN="reports/gatekeeper-run-latest.md"
PYTHON_BIN="${PYTHON_BIN:-python}"

for arg in "$@"; do
  case $arg in
    --subsystem=*)
      SUBSYSTEM="${arg#*=}"
      shift
      ;;
    --split=*)
      SPLIT="${arg#*=}"
      shift
      ;;
    --snapshot=*)
      SNAPSHOT="${arg#*=}"
      shift
      ;;
    --config=*)
      CONFIG="${arg#*=}"
      shift
      ;;
    --corpus=*)
      CORPUS="${arg#*=}"
      shift
      ;;
    --output=*)
      OUTPUT="${arg#*=}"
      shift
      ;;
    --markdown=*)
      MARKDOWN="${arg#*=}"
      shift
      ;;
  esac
done

echo "========================================================"
echo "🎯 [GATEKEEPER RUN] Executing Benchmark on ${SUBSYSTEM} (${SPLIT})"
echo "   Snapshot: ${SNAPSHOT} | Config: ${CONFIG}"
echo "========================================================"

mkdir -p "$(dirname "$OUTPUT")"
mkdir -p "$(dirname "$MARKDOWN")"

# Execute benchmark engine
"$PYTHON_BIN" -m calibration.benchmark_engine \
  --subsystem="$SUBSYSTEM" \
  --split="$SPLIT" \
  --snapshot="$SNAPSHOT" \
  --config="$CONFIG" \
  --corpus="$CORPUS" \
  --output="$OUTPUT" \
  --markdown="$MARKDOWN"

echo "✅ Gatekeeper execution completed. Report emitted to ${OUTPUT}"
