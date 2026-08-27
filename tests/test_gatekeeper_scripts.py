"""
tests/test_gatekeeper_scripts.py
================================
Unit and integration tests for CI/CD MAE Gatekeeper shell scripts and threshold evaluations.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

def find_functional_bash() -> str:
    candidates = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        shutil.which("bash")
    ]
    for c in candidates:
        if c and os.path.exists(c):
            try:
                r = subprocess.run([c, "-c", "echo ok"], capture_output=True, text=True, timeout=2)
                if r.returncode == 0 and "ok" in r.stdout:
                    return c
            except Exception:
                pass
    return "bash"

class TestGatekeeperScripts(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.python_bin = sys.executable.replace("\\", "/")
        self.bash_bin = find_functional_bash()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_preconditions_script_fails_when_drift_hold_active(self):
        """
        Verifies that check_preconditions.sh exits with non-zero when drift_hold is active.
        """
        env = os.environ.copy()
        env["MOCK_DRIFT_HOLD"] = "true"
        env["MOCK_ICC"] = "0.85"

        script_path = "scripts/calibration/check_preconditions.sh"
        proc = subprocess.run(
            [self.bash_bin, script_path, "--dry-run"],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        self.assertNotEqual(proc.returncode, 0)
        output = (proc.stderr or "") + (proc.stdout or "")
        self.assertIn("CRITICAL drift hold", output)

    def test_preconditions_script_fails_when_icc_low(self):
        """
        Verifies that check_preconditions.sh exits with non-zero when rater pool ICC < 0.80.
        """
        env = os.environ.copy()
        env["MOCK_DRIFT_HOLD"] = "false"
        env["MOCK_ICC"] = "0.72"

        script_path = "scripts/calibration/check_preconditions.sh"
        proc = subprocess.run(
            [self.bash_bin, script_path, "--dry-run"],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        self.assertNotEqual(proc.returncode, 0)
        output = (proc.stderr or "") + (proc.stdout or "")
        self.assertIn("below the 0.80 reliability threshold", output)

    def test_preconditions_script_passes_when_all_preconditions_met(self):
        """
        Verifies that check_preconditions.sh succeeds when drift_hold is false and ICC >= 0.80.
        """
        env = os.environ.copy()
        env["MOCK_DRIFT_HOLD"] = "false"
        env["MOCK_ICC"] = "0.88"

        script_path = "scripts/calibration/check_preconditions.sh"
        proc = subprocess.run(
            [self.bash_bin, script_path, "--dry-run"],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        self.assertEqual(proc.returncode, 0)
        output = (proc.stderr or "") + (proc.stdout or "")
        self.assertIn("All preconditions satisfied", output)

    def test_evaluate_thresholds_fails_on_stratum_violation(self):
        """
        Verifies that evaluate_thresholds.sh fails when a single band stratum exceeds 0.50 MAE.
        """
        report_data = {
            "overall_mae": 0.45,
            "max_criterion_mae": 0.60,
            "worst_criterion": "TASK_RESPONSE",
            "per_stratum_metrics": {
                "4.0-4.5": {"overall_mae": 0.40, "passed": True},
                "5.0-5.5": {"overall_mae": 0.42, "passed": True},
                "6.0-6.5": {"overall_mae": 0.45, "passed": True},
                "7.0-7.5": {"overall_mae": 0.48, "passed": True},
                "8.0-8.5": {"overall_mae": 0.65, "passed": False}  # Failing stratum
            }
        }
        report_path = os.path.join(self.temp_dir, "failing_stratum_report.json").replace("\\", "/")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f)

        script_path = "scripts/calibration/evaluate_thresholds.sh"
        env = os.environ.copy()
        env["PYTHON_BIN"] = self.python_bin

        proc = subprocess.run(
            [
                self.bash_bin, script_path,
                f"--report={report_path}",
                "--overall-mae-max=0.50",
                "--criterion-mae-max=0.75",
                "--require-per-stratum-pass=true"
            ],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        self.assertEqual(proc.returncode, 1)
        output = (proc.stderr or "") + (proc.stdout or "")
        self.assertIn("Stratum '8.0-8.5' MAE 0.6500 > 0.5000", output)

    def test_evaluate_thresholds_passes_on_valid_report(self):
        """
        Verifies that evaluate_thresholds.sh succeeds on valid benchmark reports.
        """
        report_data = {
            "overall_mae": 0.42,
            "max_criterion_mae": 0.68,
            "worst_criterion": "COHERENCE_COHESION",
            "per_stratum_metrics": {
                "4.0-4.5": {"overall_mae": 0.38, "passed": True},
                "5.0-5.5": {"overall_mae": 0.40, "passed": True},
                "6.0-6.5": {"overall_mae": 0.42, "passed": True},
                "7.0-7.5": {"overall_mae": 0.44, "passed": True},
                "8.0-8.5": {"overall_mae": 0.46, "passed": True}
            }
        }
        report_path = os.path.join(self.temp_dir, "valid_report.json").replace("\\", "/")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f)

        script_path = "scripts/calibration/evaluate_thresholds.sh"
        env = os.environ.copy()
        env["PYTHON_BIN"] = self.python_bin

        proc = subprocess.run(
            [
                self.bash_bin, script_path,
                f"--report={report_path}",
                "--overall-mae-max=0.50",
                "--criterion-mae-max=0.75",
                "--require-per-stratum-pass=true"
            ],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        self.assertEqual(proc.returncode, 0)
        output = (proc.stderr or "") + (proc.stdout or "")
        self.assertIn("GATEKEEPER EVALUATION PASSED", output)

    def test_changelog_appending_workflow(self):
        """
        Verifies that append_changelog.sh updates the calibration configuration ledger atomically.
        """
        config_data = {
            "configVersion": "1.0.0",
            "subsystem": "WRITING",
            "promptTemplateRef": "providers/prompts/writing_v1.txt",
            "geminiModel": "gemini-2.5-flash",
            "corpusSnapshotId": "snap-001",
            "acceptanceThresholds": {
                "overallMae": 0.50,
                "maxCriterionMae": 0.75,
                "minRaterPoolIcc": 0.80
            },
            "fewShotAnchors": [],
            "criterionLeniencyAdjustment": {},
            "gatekeeperEvaluation": {"result": "PENDING"},
            "changeLog": []
        }
        config_path = os.path.join(self.temp_dir, "test_config.json").replace("\\", "/")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)

        report_data = {
            "overall_mae": 0.39,
            "max_criterion_mae": 0.62,
            "worst_criterion": "TASK_RESPONSE"
        }
        report_path = os.path.join(self.temp_dir, "test_report.json").replace("\\", "/")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)

        script_path = "scripts/calibration/append_changelog.sh"
        env = os.environ.copy()
        env["PYTHON_BIN"] = self.python_bin

        proc = subprocess.run(
            [
                self.bash_bin, script_path,
                f"--config={config_path}",
                f"--report={report_path}",
                "--author=Alice Examiner"
            ],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        self.assertEqual(proc.returncode, 0)

        with open(config_path, "r", encoding="utf-8") as f:
            updated_cfg = json.load(f)

        self.assertEqual(updated_cfg["configVersion"], "1.0.1")
        self.assertEqual(len(updated_cfg["changeLog"]), 1)
        self.assertEqual(updated_cfg["changeLog"][0]["author"], "Alice Examiner")
        self.assertEqual(updated_cfg["changeLog"][0]["gatekeeperMae"], 0.39)
        self.assertEqual(updated_cfg["gatekeeperEvaluation"]["result"], "PASSED")

if __name__ == "__main__":
    unittest.main()
