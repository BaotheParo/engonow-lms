#!/usr/bin/env bash
# ==============================================================================
# scripts/calibration/evaluate_thresholds.sh
# Hard Statistical Gatekeeper Threshold Evaluator.
# Parses gatekeeper benchmark report and enforces zero-tolerance policy:
# - Overall Band MAE <= 0.50
# - Per-Stratum MAE <= 0.50 for all 5 band strata
# - Max Criterion MAE <= 0.75
# ==============================================================================
set -euo pipefail

REPORT="reports/gatekeeper-run-latest.json"
OVERALL_MAE_MAX="0.50"
CRITERION_MAE_MAX="0.75"
REQUIRE_STRATUM_PASS="true"
PYTHON_BIN="${PYTHON_BIN:-python}"

for arg in "$@"; do
  case $arg in
    --report=*)
      REPORT="${arg#*=}"
      shift
      ;;
    --overall-mae-max=*)
      OVERALL_MAE_MAX="${arg#*=}"
      shift
      ;;
    --criterion-mae-max=*)
      CRITERION_MAE_MAX="${arg#*=}"
      shift
      ;;
    --require-per-stratum-pass=*)
      REQUIRE_STRATUM_PASS="${arg#*=}"
      shift
      ;;
  esac
done

if [ ! -f "$REPORT" ]; then
  echo "Error: Report file not found: $REPORT" >&2
  exit 1
fi

echo "========================================================"
echo "[GATEKEEPER THRESHOLD EVALUATION]"
echo "   Report: ${REPORT}"
echo "   Max Overall MAE: ${OVERALL_MAE_MAX} | Max Criterion MAE: ${CRITERION_MAE_MAX}"
echo "========================================================"

# Evaluate using Python helper for robust floating-point math & JSON inspection
"$PYTHON_BIN" - <<EOF
import json
import sys

# Ensure UTF-8 stdout encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

with open("${REPORT}", "r", encoding="utf-8") as f:
    data = json.load(f)

overall_mae = float(data.get("overall_mae", data.get("overallMae", 0.0)))
max_crit_mae = float(data.get("max_criterion_mae", data.get("maxCriterionMae", 0.0)))
worst_crit = data.get("worst_criterion", data.get("worstCriterion", "NONE"))
per_stratum = data.get("per_stratum_metrics", data.get("perStratumMetrics", {}))
failures = []

overall_limit = float("${OVERALL_MAE_MAX}")
crit_limit = float("${CRITERION_MAE_MAX}")
req_stratum = "${REQUIRE_STRATUM_PASS}".lower() == "true"

print(f"[METRIC] Global Overall MAE: {overall_mae:.4f} (Threshold: <= {overall_limit:.4f})")
print(f"[METRIC] Worst Criterion MAE ({worst_crit}): {max_crit_mae:.4f} (Threshold: <= {crit_limit:.4f})")

if overall_mae > overall_limit:
    failures.append(f"Global Overall MAE {overall_mae:.4f} > {overall_limit:.4f}")

if max_crit_mae > crit_limit:
    failures.append(f"Worst Criterion '{worst_crit}' MAE {max_crit_mae:.4f} > {crit_limit:.4f}")

if req_stratum and per_stratum:
    print("\n[STRATIFIED BREAKDOWN]:")
    for stratum, sm in per_stratum.items():
        s_mae = float(sm.get("overall_mae", sm.get("overallMae", 0.0)))
        s_status = "[PASS]" if s_mae <= overall_limit else "[FAIL]"
        print(f"   - Stratum [{stratum}]: MAE = {s_mae:.4f} -> {s_status}")
        if s_mae > overall_limit:
            failures.append(f"Stratum '{stratum}' MAE {s_mae:.4f} > {overall_limit:.4f}")

print("\n" + "="*56)
if failures:
    print("[FAIL] GATEKEEPER EVALUATION FAILED:")
    for f in failures:
        print(f"   * {f}")
    sys.exit(1)
else:
    print("[PASS] GATEKEEPER EVALUATION PASSED: All psychometric accuracy thresholds satisfied.")
    sys.exit(0)
EOF

STATUS=$?
exit $STATUS
