"""
tests/test_benchmark_engine.py
==============================
Unit and integration test suite for Benchmark Evaluation Engine and Calibration Config Manager.
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock
from calibration.benchmark_engine import (
    WritingBenchmarkRunner,
    apply_cambridge_rounding,
    BenchmarkReport
)
from calibration.config_manager import (
    CalibrationConfig,
    load_config,
    save_config,
    append_changelog_and_bump_version
)

class MockFeedbackCriterion:
    def __init__(self, criterion: str, score: float):
        self.criterion = criterion
        self.bandScore = score

class MockFeedbackDetail:
    def __init__(self, overall_band: float, criteria: list):
        self.overallBand = overall_band
        self.criteria = criteria

class TestBenchmarkEngine(unittest.IsolatedAsyncioTestCase):

    def test_cambridge_rounding_logic(self):
        self.assertEqual(apply_cambridge_rounding(6.25), 6.5)
        self.assertEqual(apply_cambridge_rounding(6.125), 6.5)
        self.assertEqual(apply_cambridge_rounding(6.75), 7.0)
        self.assertEqual(apply_cambridge_rounding(6.625), 7.0)
        self.assertEqual(apply_cambridge_rounding(6.375), 6.5)
        self.assertEqual(apply_cambridge_rounding(6.875), 7.0)
        self.assertEqual(apply_cambridge_rounding(6.0), 6.0)
        self.assertEqual(apply_cambridge_rounding(6.5), 6.5)

    async def test_mae_calculation_exactness_with_synthetic_matrix(self):
        # 5 items, one per stratum
        corpus_items = [
            {
                "id": "item-1",
                "task_type": "TASK2",
                "prompt_text": "Prompt 1",
                "essay_text": "Essay 1",
                "target_band_stratum": "4.0-4.5",
                "reference_scores": {"TASK_RESPONSE": 4.0, "COHERENCE_COHESION": 4.5, "LEXICAL_RESOURCE": 4.0, "GRAMMATICAL_RANGE_ACCURACY": 4.5},
                "reference_overall_band": 4.5
            },
            {
                "id": "item-2",
                "task_type": "TASK2",
                "prompt_text": "Prompt 2",
                "essay_text": "Essay 2",
                "target_band_stratum": "5.0-5.5",
                "reference_scores": {"TASK_RESPONSE": 5.0, "COHERENCE_COHESION": 5.5, "LEXICAL_RESOURCE": 5.0, "GRAMMATICAL_RANGE_ACCURACY": 5.5},
                "reference_overall_band": 5.5
            },
            {
                "id": "item-3",
                "task_type": "TASK2",
                "prompt_text": "Prompt 3",
                "essay_text": "Essay 3",
                "target_band_stratum": "6.0-6.5",
                "reference_scores": {"TASK_RESPONSE": 6.0, "COHERENCE_COHESION": 6.5, "LEXICAL_RESOURCE": 6.0, "GRAMMATICAL_RANGE_ACCURACY": 6.5},
                "reference_overall_band": 6.5
            },
            {
                "id": "item-4",
                "task_type": "TASK2",
                "prompt_text": "Prompt 4",
                "essay_text": "Essay 4",
                "target_band_stratum": "7.0-7.5",
                "reference_scores": {"TASK_RESPONSE": 7.0, "COHERENCE_COHESION": 7.5, "LEXICAL_RESOURCE": 7.0, "GRAMMATICAL_RANGE_ACCURACY": 7.5},
                "reference_overall_band": 7.5
            },
            {
                "id": "item-5",
                "task_type": "TASK2",
                "prompt_text": "Prompt 5",
                "essay_text": "Essay 5",
                "target_band_stratum": "8.0-8.5",
                "reference_scores": {"TASK_RESPONSE": 8.0, "COHERENCE_COHESION": 8.5, "LEXICAL_RESOURCE": 8.0, "GRAMMATICAL_RANGE_ACCURACY": 8.5},
                "reference_overall_band": 8.5
            }
        ]

        # Mock Provider outputs:
        # Item 1: AI Overall = 4.5 (err 0.0), TR=4.5 (err 0.5), CC=4.5 (err 0.0), LR=4.0 (err 0.0), GRA=4.5 (err 0.0)
        # Item 2: AI Overall = 5.0 (err 0.5), TR=5.0 (err 0.0), CC=5.0 (err 0.5), LR=5.0 (err 0.0), GRA=5.0 (err 0.5)
        # Item 3: AI Overall = 6.5 (err 0.0), TR=6.0 (err 0.0), CC=6.5 (err 0.0), LR=6.5 (err 0.5), GRA=6.5 (err 0.0)
        # Item 4: AI Overall = 7.0 (err 0.5), TR=7.0 (err 0.0), CC=7.0 (err 0.5), LR=7.0 (err 0.0), GRA=7.0 (err 0.5)
        # Item 5: AI Overall = 8.5 (err 0.0), TR=8.5 (err 0.5), CC=8.5 (err 0.0), LR=8.0 (err 0.0), GRA=8.5 (err 0.0)
        # Overall errors = [0.0, 0.5, 0.0, 0.5, 0.0] -> Mean = 1.0 / 5 = 0.20
        # TR errors = [0.5, 0.0, 0.0, 0.0, 0.5] -> Mean = 1.0 / 5 = 0.20
        # CC errors = [0.0, 0.5, 0.0, 0.5, 0.0] -> Mean = 1.0 / 5 = 0.20
        # LR errors = [0.0, 0.0, 0.5, 0.0, 0.0] -> Mean = 0.5 / 5 = 0.10
        # GRA errors = [0.0, 0.5, 0.0, 0.5, 0.0] -> Mean = 1.0 / 5 = 0.20

        mock_responses = [
            MockFeedbackDetail(4.5, [
                MockFeedbackCriterion("TASK_RESPONSE", 4.5),
                MockFeedbackCriterion("COHERENCE_COHESION", 4.5),
                MockFeedbackCriterion("LEXICAL_RESOURCE", 4.0),
                MockFeedbackCriterion("GRAMMATICAL_RANGE_ACCURACY", 4.5)
            ]),
            MockFeedbackDetail(5.0, [
                MockFeedbackCriterion("TASK_RESPONSE", 5.0),
                MockFeedbackCriterion("COHERENCE_COHESION", 5.0),
                MockFeedbackCriterion("LEXICAL_RESOURCE", 5.0),
                MockFeedbackCriterion("GRAMMATICAL_RANGE_ACCURACY", 5.0)
            ]),
            MockFeedbackDetail(6.5, [
                MockFeedbackCriterion("TASK_RESPONSE", 6.0),
                MockFeedbackCriterion("COHERENCE_COHESION", 6.5),
                MockFeedbackCriterion("LEXICAL_RESOURCE", 6.5),
                MockFeedbackCriterion("GRAMMATICAL_RANGE_ACCURACY", 6.5)
            ]),
            MockFeedbackDetail(7.0, [
                MockFeedbackCriterion("TASK_RESPONSE", 7.0),
                MockFeedbackCriterion("COHERENCE_COHESION", 7.0),
                MockFeedbackCriterion("LEXICAL_RESOURCE", 7.0),
                MockFeedbackCriterion("GRAMMATICAL_RANGE_ACCURACY", 7.0)
            ]),
            MockFeedbackDetail(8.5, [
                MockFeedbackCriterion("TASK_RESPONSE", 8.5),
                MockFeedbackCriterion("COHERENCE_COHESION", 8.5),
                MockFeedbackCriterion("LEXICAL_RESOURCE", 8.0),
                MockFeedbackCriterion("GRAMMATICAL_RANGE_ACCURACY", 8.5)
            ])
        ]

        provider = MagicMock()
        provider.evaluate_essay = AsyncMock(side_effect=mock_responses)

        runner = WritingBenchmarkRunner(provider)
        report = await runner.run_benchmark(corpus_items)

        self.assertAlmostEqual(report.overall_mae, 0.20, places=4)
        self.assertAlmostEqual(report.criterion_mae["TASK_RESPONSE"], 0.20, places=4)
        self.assertAlmostEqual(report.criterion_mae["COHERENCE_COHESION"], 0.20, places=4)
        self.assertAlmostEqual(report.criterion_mae["LEXICAL_RESOURCE"], 0.10, places=4)
        self.assertAlmostEqual(report.criterion_mae["GRAMMATICAL_RANGE_ACCURACY"], 0.20, places=4)
        self.assertTrue(report.is_acceptable)
        self.assertEqual(len(report.failure_reasons), 0)

    async def test_central_tendency_bias_failure_gate(self):
        # 5 items across 5 strata
        # Stratum 8.0-8.5 has severe under-scoring (e.g. AI gives 7.0 for an 8.5 essay -> err 1.5)
        corpus_items = [
            {"id": "1", "task_type": "TASK2", "prompt_text": "P", "essay_text": "E", "target_band_stratum": "4.0-4.5", "reference_overall_band": 4.5, "reference_scores": {"TASK_RESPONSE": 4.5}},
            {"id": "2", "task_type": "TASK2", "prompt_text": "P", "essay_text": "E", "target_band_stratum": "5.0-5.5", "reference_overall_band": 5.5, "reference_scores": {"TASK_RESPONSE": 5.5}},
            {"id": "3", "task_type": "TASK2", "prompt_text": "P", "essay_text": "E", "target_band_stratum": "6.0-6.5", "reference_overall_band": 6.5, "reference_scores": {"TASK_RESPONSE": 6.5}},
            {"id": "4", "task_type": "TASK2", "prompt_text": "P", "essay_text": "E", "target_band_stratum": "7.0-7.5", "reference_overall_band": 7.5, "reference_scores": {"TASK_RESPONSE": 7.5}},
            {"id": "5", "task_type": "TASK2", "prompt_text": "P", "essay_text": "E", "target_band_stratum": "8.0-8.5", "reference_overall_band": 8.5, "reference_scores": {"TASK_RESPONSE": 8.5}}
        ]

        # Overall errors = [0.0, 0.0, 0.0, 0.0, 1.5] -> Mean Overall MAE = 1.5 / 5 = 0.30 (Passing < 0.50)
        # But Stratum 8.0-8.5 MAE = 1.50 > 0.50 (Failing Gatekeeper)
        mock_responses = [
            MockFeedbackDetail(4.5, [MockFeedbackCriterion("TASK_RESPONSE", 4.5)]),
            MockFeedbackDetail(5.5, [MockFeedbackCriterion("TASK_RESPONSE", 5.5)]),
            MockFeedbackDetail(6.5, [MockFeedbackCriterion("TASK_RESPONSE", 6.5)]),
            MockFeedbackDetail(7.5, [MockFeedbackCriterion("TASK_RESPONSE", 7.5)]),
            MockFeedbackDetail(7.0, [MockFeedbackCriterion("TASK_RESPONSE", 7.0)])
        ]

        provider = MagicMock()
        provider.evaluate_essay = AsyncMock(side_effect=mock_responses)

        runner = WritingBenchmarkRunner(provider)
        report = await runner.run_benchmark(corpus_items)

        self.assertFalse(report.is_acceptable)
        self.assertTrue(any("8.0-8.5" in r for r in report.failure_reasons))

    async def test_worst_criterion_mae_gate_trigger(self):
        corpus_items = [
            {"id": "1", "task_type": "TASK2", "prompt_text": "P", "essay_text": "E", "target_band_stratum": "6.0-6.5", "reference_overall_band": 6.5, "reference_scores": {"TASK_RESPONSE": 6.5, "LEXICAL_RESOURCE": 6.5}},
            {"id": "2", "task_type": "TASK2", "prompt_text": "P", "essay_text": "E", "target_band_stratum": "6.0-6.5", "reference_overall_band": 6.5, "reference_scores": {"TASK_RESPONSE": 6.5, "LEXICAL_RESOURCE": 6.5}}
        ]

        # Overall Band is accurate, but LEXICAL_RESOURCE has MAE = 1.0 (> 0.75)
        mock_responses = [
            MockFeedbackDetail(6.5, [MockFeedbackCriterion("TASK_RESPONSE", 6.5), MockFeedbackCriterion("LEXICAL_RESOURCE", 5.5)]),
            MockFeedbackDetail(6.5, [MockFeedbackCriterion("TASK_RESPONSE", 6.5), MockFeedbackCriterion("LEXICAL_RESOURCE", 7.5)])
        ]

        provider = MagicMock()
        provider.evaluate_essay = AsyncMock(side_effect=mock_responses)

        runner = WritingBenchmarkRunner(provider)
        report = await runner.run_benchmark(corpus_items)

        self.assertFalse(report.is_acceptable)
        self.assertEqual(report.worst_criterion, "LEXICAL_RESOURCE")
        self.assertAlmostEqual(report.max_criterion_mae, 1.0, places=4)
        self.assertTrue(any("LEXICAL_RESOURCE" in r for r in report.failure_reasons))

    def test_config_manager_append_only_immutability(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "test_config.json")

            initial_config = {
                "configVersion": "2026.09.01-v1",
                "subsystem": "WRITING",
                "promptTemplateRef": "providers/prompts/writing_system.txt",
                "geminiModel": "gemini-2.5-flash",
                "corpusSnapshotId": "snap-001",
                "acceptanceThresholds": {"overallMae": 0.5, "maxCriterionMae": 0.75, "minRaterPoolIcc": 0.8},
                "fewShotAnchors": [],
                "criterionLeniencyAdjustment": {"LEXICAL_RESOURCE": 0.0},
                "gatekeeperEvaluation": {"result": "PENDING"},
                "changeLog": [
                    {
                        "version": "2026.09.01-v1",
                        "timestamp": "2026-08-25T00:00:00Z",
                        "author": "Initial Author",
                        "change": "Baseline config"
                    }
                ]
            }

            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(initial_config, f, indent=2)

            # Bump 1
            cfg1 = append_changelog_and_bump_version(
                config_path, "2026.09.01-v2", "Dev A", "Added few-shot anchor", gatekeeper_mae=0.48
            )
            self.assertEqual(len(cfg1.changeLog), 2)
            self.assertEqual(cfg1.configVersion, "2026.09.01-v2")
            self.assertEqual(cfg1.gatekeeperEvaluation.result, "PASSED")

            # Bump 2
            cfg2 = append_changelog_and_bump_version(
                config_path, "2026.09.01-v3", "Dev B", "Adjusted prompt tuning", gatekeeper_mae=0.45
            )
            self.assertEqual(len(cfg2.changeLog), 3)
            self.assertEqual(cfg2.configVersion, "2026.09.01-v3")

            # Bump 3
            cfg3 = append_changelog_and_bump_version(
                config_path, "2026.09.01-v4", "Dev C", "Refined rubrics", gatekeeper_mae=0.55
            )
            self.assertEqual(len(cfg3.changeLog), 4)
            self.assertEqual(cfg3.configVersion, "2026.09.01-v4")
            self.assertEqual(cfg3.gatekeeperEvaluation.result, "FAILED")

            # Reload directly from disk to verify persistence and ordering
            reloaded = load_config(config_path)
            self.assertEqual(len(reloaded.changeLog), 4)
            self.assertEqual(reloaded.changeLog[0].version, "2026.09.01-v1")
            self.assertEqual(reloaded.changeLog[0].author, "Initial Author")
            self.assertEqual(reloaded.changeLog[1].version, "2026.09.01-v2")
            self.assertEqual(reloaded.changeLog[2].version, "2026.09.01-v3")
            self.assertEqual(reloaded.changeLog[3].version, "2026.09.01-v4")

    async def test_defensive_criterion_score_extraction_with_abbreviations_and_dict(self):
        corpus_items = [
            {
                "id": "item-abbrev-1",
                "task_type": "TASK2",
                "prompt_text": "P",
                "essay_text": "E",
                "target_band_stratum": "6.0-6.5",
                "reference_scores": {"TR": 6.5, "CC": 6.5, "LR": 6.0, "GRA": 6.0},
                "reference_overall_band": 6.5
            }
        ]

        # AI returns criteria with abbreviation names TR, CC, LR, GRA
        mock_response = {
            "overallBand": 6.5,
            "criteria": [
                {"criterion": "TR", "bandScore": 6.5},
                {"criterion": "CC", "bandScore": 6.5},
                {"criterion": "LR", "bandScore": 6.0},
                {"criterion": "GRA", "bandScore": 6.0}
            ]
        }

        provider = MagicMock()
        provider.evaluate_essay = AsyncMock(return_value=mock_response)

        runner = WritingBenchmarkRunner(provider)
        report = await runner.run_benchmark(corpus_items)

        self.assertEqual(report.total_items, 1)
        self.assertAlmostEqual(report.overall_mae, 0.0, places=4)
        self.assertAlmostEqual(report.criterion_mae["TASK_RESPONSE"], 0.0, places=4)
        self.assertAlmostEqual(report.criterion_mae["COHERENCE_COHESION"], 0.0, places=4)
        self.assertAlmostEqual(report.criterion_mae["LEXICAL_RESOURCE"], 0.0, places=4)
        self.assertAlmostEqual(report.criterion_mae["GRAMMATICAL_RANGE_ACCURACY"], 0.0, places=4)
        self.assertTrue(report.is_acceptable)

    async def test_missing_criterion_records_diagnostic_without_crashing_batch(self):
        corpus_items = [
            {
                "id": "item-incomplete",
                "task_type": "TASK2",
                "prompt_text": "P",
                "essay_text": "E",
                "target_band_stratum": "6.0-6.5",
                "reference_scores": {"TASK_RESPONSE": 6.5, "COHERENCE_COHESION": 6.5, "LEXICAL_RESOURCE": 6.0, "GRAMMATICAL_RANGE_ACCURACY": 6.0},
                "reference_overall_band": 6.5
            }
        ]

        # AI response is missing GRAMMATICAL_RANGE_ACCURACY
        mock_response = {
            "overallBand": 6.5,
            "criteria": [
                {"criterion": "TASK_RESPONSE", "bandScore": 6.5},
                {"criterion": "COHERENCE_COHESION", "bandScore": 6.5},
                {"criterion": "LEXICAL_RESOURCE", "bandScore": 6.0}
            ]
        }

        provider = MagicMock()
        provider.evaluate_essay = AsyncMock(return_value=mock_response)

        runner = WritingBenchmarkRunner(provider)
        report = await runner.run_benchmark(corpus_items)

        # Batch completes successfully without crash
        self.assertEqual(report.total_items, 1)
        self.assertTrue(any("GRAMMATICAL_RANGE_ACCURACY" in d for d in report.diagnostics))

    def test_atomic_file_write_save_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "atomic_config.json")
            config = CalibrationConfig(
                configVersion="2026.09.01-v1",
                subsystem="WRITING",
                promptTemplateRef="providers/prompts/writing_system.txt",
                geminiModel="gemini-2.5-flash",
                corpusSnapshotId="snap-001"
            )

            save_config(config_path, config)
            self.assertTrue(os.path.exists(config_path))
            loaded = load_config(config_path)
            self.assertEqual(loaded.configVersion, "2026.09.01-v1")

if __name__ == "__main__":
    unittest.main()
