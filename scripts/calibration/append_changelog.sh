#!/usr/bin/env bash
# ==============================================================================
# scripts/calibration/append_changelog.sh
# Appends verified Gatekeeper MAE run results to the immutable calibration config changeLog.
# ==============================================================================
set -euo pipefail

CONFIG="calibration_config_writing.json"
REPORT="reports/gatekeeper-run-latest.json"
AUTHOR="${GIT_AUTHOR_NAME:-CI/CD Release Gatekeeper}"
PYTHON_BIN="${PYTHON_BIN:-python}"

for arg in "$@"; do
  case $arg in
    --config=*)
      CONFIG="${arg#*=}"
      shift
      ;;
    --report=*)
      REPORT="${arg#*=}"
      shift
      ;;
    --author=*)
      AUTHOR="${arg#*=}"
      shift
      ;;
  esac
done

if [ ! -f "$CONFIG" ]; then
  echo "❌ Error: Config file not found: $CONFIG" >&2
  exit 1
fi

if [ ! -f "$REPORT" ]; then
  echo "❌ Error: Report file not found: $REPORT" >&2
  exit 1
fi

echo "========================================================"
echo "📝 [CHANGELOG APPEND] Updating Calibration Ledger in ${CONFIG}"
echo "   Author: ${AUTHOR}"
echo "========================================================"

"$PYTHON_BIN" -m calibration.config_manager \
  --config="$CONFIG" \
  --report="$REPORT" \
  --author="$AUTHOR"

echo "✅ Immutable changeLog ledger updated successfully."
