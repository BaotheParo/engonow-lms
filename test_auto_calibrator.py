"""Tests for automated pronunciation-threshold calibration."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from acoustic_engine import (
    DEFAULT_THRESHOLDS,
    ParsedWhisperOutput,
    WhisperSegment,
    compute_pronunciation_features,
    load_pr_thresholds,
)
from telemetry.auto_calibrator import AutoCalibrator, THRESHOLD_KEYS


class AutoCalibratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        rng = np.random.default_rng(2026)
        clusters = (
            (-0.10, 8),
            (-0.23, 7),
            (-0.35, 6),
            (-0.48, 5),
            (-0.80, 4),
        )
        cls.corpus = [
            {"logprob": float(logprob), "human_band": band}
            for center, band in clusters
            for logprob in rng.normal(center, 0.02, size=10)
        ]

    def test_calibration_optimizes_mae_and_saves_ordered_config(self) -> None:
        calibrator = AutoCalibrator()
        config = calibrator.calibrate(self.corpus)
        X = np.asarray(
            [sample["logprob"] for sample in self.corpus],
            dtype=float,
        )
        y = np.asarray(
            [sample["human_band"] for sample in self.corpus],
            dtype=float,
        )
        thresholds = [config[key] for key in THRESHOLD_KEYS]

        self.assertLessEqual(
            calibrator.objective_function(thresholds, X, y),
            0.6,
        )
        self.assertTrue(
            all(
                higher > lower
                for higher, lower in zip(thresholds, thresholds[1:])
            )
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "calibration_config.json"
            calibrator.save_calibration(config, config_path)

            with config_path.open("r", encoding="utf-8") as config_file:
                saved_config = json.load(config_file)

        self.assertTrue(set(THRESHOLD_KEYS).issubset(saved_config))
        saved_thresholds = [
            saved_config[key]
            for key in THRESHOLD_KEYS
        ]
        self.assertTrue(
            all(
                higher > lower
                for higher, lower in zip(
                    saved_thresholds,
                    saved_thresholds[1:],
                )
            )
        )

    def test_acoustic_fallback_uses_dynamic_thresholds(self) -> None:
        calibrated_thresholds = {
            "band_8": -0.40,
            "band_7": -0.50,
            "band_6": -0.60,
            "band_5": -0.70,
            "band_4": -0.90,
        }
        parsed = ParsedWhisperOutput(
            words=[],
            segments=[
                WhisperSegment(
                    segment_id=0,
                    start=0.0,
                    end=1.0,
                    text="test",
                    avg_logprob=-0.30,
                    no_speech_prob=0.0,
                    compression_ratio=1.0,
                )
            ],
            total_duration=1.0,
            total_words=0,
            raw_transcript="",
        )

        with patch(
            "acoustic_engine.load_pr_thresholds",
            return_value=calibrated_thresholds,
        ):
            features = compute_pronunciation_features(parsed)

        self.assertEqual(features.pr_band, 8)

    def test_loader_falls_back_for_missing_or_unordered_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing_path = Path(temporary_directory) / "missing.json"
            self.assertEqual(
                load_pr_thresholds(missing_path),
                DEFAULT_THRESHOLDS,
            )

            invalid_path = Path(temporary_directory) / "invalid.json"
            invalid_path.write_text(
                json.dumps(
                    {
                        "band_8": -0.30,
                        "band_7": -0.20,
                        "band_6": -0.40,
                        "band_5": -0.50,
                        "band_4": -0.60,
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                load_pr_thresholds(invalid_path),
                DEFAULT_THRESHOLDS,
            )


if __name__ == "__main__":
    unittest.main()
