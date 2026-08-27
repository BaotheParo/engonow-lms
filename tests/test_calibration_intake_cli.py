import unittest
from scripts.calibration_intake_cli import validate_dataset, validate_item, CalibrationValidationError

class TestCalibrationIntakeCli(unittest.TestCase):

    def test_valid_writing_item(self):
        item = {
            "subsystem": "WRITING",
            "task_type": "TASK2",
            "prompt_text": "Discuss environmental impacts.",
            "essay_text": "Industrial manufacturing has severely impacted natural ecosystems...",
            "target_band_stratum": "6.0-6.5",
            "dataset_split": "TUNING",
            "status": "PENDING_RATING"
        }
        errors = validate_item(item, 0)
        self.assertEqual(errors, [])

    def test_valid_speaking_item(self):
        item = {
            "subsystem": "SPEAKING",
            "task_type": "PART_2",
            "prompt_text": "Describe a memorable journey.",
            "source_audio_url": "https://storage.example.com/audio/attempt-001.wav",
            "source_audio_duration_seconds": 120,
            "target_band_stratum": "7.0-7.5",
            "dataset_split": "GATEKEEPER",
            "status": "PENDING_RATING"
        }
        errors = validate_item(item, 0)
        self.assertEqual(errors, [])

    def test_writing_missing_essay_fails(self):
        item = {
            "subsystem": "WRITING",
            "task_type": "TASK2",
            "prompt_text": "Discuss environmental impacts.",
            "target_band_stratum": "6.0-6.5"
        }
        errors = validate_item(item, 0)
        self.assertTrue(any("Writing item missing mandatory 'essay_text'" in e for e in errors))

    def test_speaking_missing_audio_fails(self):
        item = {
            "subsystem": "SPEAKING",
            "task_type": "PART_1",
            "prompt_text": "Do you like music?",
            "target_band_stratum": "5.0-5.5"
        }
        errors = validate_item(item, 0)
        self.assertTrue(any("Speaking item missing mandatory 'source_audio_url'" in e for e in errors))

    def test_invalid_stratum_fails(self):
        item = {
            "subsystem": "WRITING",
            "task_type": "TASK2",
            "prompt_text": "Discuss technology.",
            "essay_text": "Some text here.",
            "target_band_stratum": "9.5-10.0"
        }
        errors = validate_item(item, 0)
        self.assertTrue(any("'target_band_stratum' must be one of" in e for e in errors))

    def test_invalid_subsystem_fails(self):
        item = {
            "subsystem": "READING",
            "task_type": "PASSAGE1",
            "prompt_text": "Sample text",
            "target_band_stratum": "6.0-6.5"
        }
        errors = validate_item(item, 0)
        self.assertTrue(any("'subsystem' must be one of" in e for e in errors))

    def test_empty_dataset_fails(self):
        items, errors = validate_dataset([])
        self.assertTrue(any("Dataset is empty" in e for e in errors))

    def test_not_a_list_fails(self):
        items, errors = validate_dataset({"subsystem": "WRITING"})
        self.assertTrue(any("Root JSON structure must be a list" in e for e in errors))

    def test_insert_items_handles_error_with_rollback(self):
        from unittest.mock import MagicMock, patch
        import sys
        import uuid

        mock_psycopg2 = MagicMock()
        mock_extras = MagicMock()
        mock_conn = MagicMock()
        mock_cur = MagicMock()

        mock_psycopg2.connect.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_extras.execute_values.side_effect = Exception("duplicate key value violates unique constraint 'uq_calibration_items_pkey'")
        mock_psycopg2.extras = mock_extras

        with patch.dict(sys.modules, {"psycopg2": mock_psycopg2, "psycopg2.extras": mock_extras}):
            from scripts.calibration_intake_cli import insert_items_postgres
            valid_item = {
                "subsystem": "WRITING",
                "task_type": "TASK2",
                "prompt_text": "Sample prompt",
                "essay_text": "Sample essay",
                "target_band_stratum": "6.0-6.5",
                "dataset_split": "TUNING"
            }
            with self.assertRaises(Exception) as ctx:
                insert_items_postgres([valid_item], "postgresql://user:pass@localhost:5432/db", uuid.uuid4())

            self.assertIn("duplicate key value violates unique constraint", str(ctx.exception))
            # Verify rollback and close were called
            mock_conn.rollback.assert_called_once()
            mock_conn.close.assert_called_once()

    def test_deduplicate_in_memory(self):
        from scripts.calibration_intake_cli import deduplicate_in_memory
        item1 = {
            "subsystem": "WRITING",
            "task_type": "TASK2",
            "prompt_text": "Same prompt",
            "essay_text": "Same essay",
            "target_band_stratum": "6.0-6.5"
        }
        item2 = {
            "subsystem": "WRITING",
            "task_type": "TASK2",
            "prompt_text": "Same prompt",
            "essay_text": "Same essay",
            "target_band_stratum": "6.0-6.5"
        }
        item3 = {
            "subsystem": "WRITING",
            "task_type": "TASK2",
            "prompt_text": "Different prompt",
            "essay_text": "Different essay",
            "target_band_stratum": "7.0-7.5"
        }
        deduped, dups = deduplicate_in_memory([item1, item2, item3])
        self.assertEqual(len(deduped), 2)
        self.assertEqual(dups, 1)

    def test_deduplicate_against_db_and_idempotent_insert(self):
        from unittest.mock import MagicMock, patch
        import sys
        import uuid
        from scripts.calibration_intake_cli import compute_content_hash

        mock_psycopg2 = MagicMock()
        mock_extras = MagicMock()
        mock_conn = MagicMock()
        mock_cur = MagicMock()

        mock_psycopg2.connect.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_psycopg2.extras = mock_extras

        existing_item = {
            "subsystem": "WRITING",
            "task_type": "TASK2",
            "prompt_text": "Existing prompt",
            "essay_text": "Existing essay",
            "target_band_stratum": "6.0-6.5"
        }
        existing_hash = compute_content_hash(existing_item)

        # Simulate existing DB item content hash
        mock_cur.fetchall.return_value = [(existing_hash,)]

        with patch.dict(sys.modules, {"psycopg2": mock_psycopg2, "psycopg2.extras": mock_extras}):
            from scripts.calibration_intake_cli import insert_items_postgres
            items = [
                existing_item,
                {
                    "subsystem": "WRITING",
                    "task_type": "TASK2",
                    "prompt_text": "New prompt",
                    "essay_text": "New essay",
                    "target_band_stratum": "7.0-7.5"
                }
            ]
            inserted, skipped = insert_items_postgres(items, "postgresql://user:pass@localhost:5432/db", uuid.uuid4())
            self.assertEqual(inserted, 1)
            self.assertEqual(skipped, 1)
            mock_conn.commit.assert_called_once()
            mock_conn.close.assert_called_once()

if __name__ == "__main__":
    unittest.main()
