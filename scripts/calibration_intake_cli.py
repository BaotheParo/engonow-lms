#!/usr/bin/env python3
"""
scripts/calibration_intake_cli.py
==================================
CLI Intake Tool for the Golden Calibration Corpus Foundation.
Validates and ingests ground-truth IELTS Writing & Speaking items into PostgreSQL.

Usage:
    python scripts/calibration_intake_cli.py --file data/golden_corpus_writing_init.json --db-url postgresql://postgres:postgres@localhost:5432/engonow_lms
    python scripts/calibration_intake_cli.py --file data/golden_corpus_writing_init.json --dry-run
"""

import argparse
import hashlib
import json
import os
import sys
import uuid
from typing import Any, Dict, List, Optional, Tuple

VALID_SUBSYSTEMS = {"WRITING", "SPEAKING"}
VALID_STRATA = {"4.0-4.5", "5.0-5.5", "6.0-6.5", "7.0-7.5", "8.0-8.5"}
VALID_SPLITS = {"TUNING", "GATEKEEPER", "UNASSIGNED"}
VALID_STATUSES = {
    "PENDING_RATING",
    "RATING_IN_PROGRESS",
    "DISCORDANT_PENDING_ADJUDICATION",
    "ADJUDICATED",
    "ACTIVE",
    "RETIRED",
}

class CalibrationValidationError(Exception):
    """Raised when one or more items in the calibration dataset fail validation."""
    pass

def validate_item(item: Dict[str, Any], index: int) -> List[str]:
    """
    Validates a single calibration corpus item against domain constraints.
    Returns a list of error strings (empty if valid).
    """
    errors = []
    
    # 1. Subsystem check
    subsystem = item.get("subsystem")
    if not subsystem or subsystem not in VALID_SUBSYSTEMS:
        errors.append(f"Item #{index}: 'subsystem' must be one of {sorted(VALID_SUBSYSTEMS)}, got '{subsystem}'")

    # 2. Task Type
    task_type = item.get("task_type")
    if not task_type or not str(task_type).strip():
        errors.append(f"Item #{index}: 'task_type' must be non-empty string")

    # 3. Prompt Text
    prompt_text = item.get("prompt_text")
    if not prompt_text or not str(prompt_text).strip():
        errors.append(f"Item #{index}: 'prompt_text' must be non-empty string")

    # 4. Domain Check Constraints (Writing vs Speaking)
    if subsystem == "WRITING":
        essay_text = item.get("essay_text")
        if not essay_text or not str(essay_text).strip():
            errors.append(f"Item #{index}: Writing item missing mandatory 'essay_text'")
    elif subsystem == "SPEAKING":
        source_audio_url = item.get("source_audio_url")
        if not source_audio_url or not str(source_audio_url).strip():
            errors.append(f"Item #{index}: Speaking item missing mandatory 'source_audio_url'")

    # 5. Target Band Stratum
    stratum = item.get("target_band_stratum")
    if not stratum or stratum not in VALID_STRATA:
        errors.append(f"Item #{index}: 'target_band_stratum' must be one of {sorted(VALID_STRATA)}, got '{stratum}'")

    # 6. Optional dataset_split validation
    dataset_split = item.get("dataset_split", "UNASSIGNED")
    if dataset_split not in VALID_SPLITS:
        errors.append(f"Item #{index}: 'dataset_split' must be one of {sorted(VALID_SPLITS)}, got '{dataset_split}'")

    # 7. Optional status validation
    status = item.get("status", "PENDING_RATING")
    if status not in VALID_STATUSES:
        errors.append(f"Item #{index}: 'status' must be one of {sorted(VALID_STATUSES)}, got '{status}'")

    return errors

def validate_dataset(data: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Validates the entire calibration dataset loaded from JSON.
    Returns (items, all_errors).
    """
    if not isinstance(data, list):
        return [], ["Root JSON structure must be a list of corpus item objects"]

    if len(data) == 0:
        return [], ["Dataset is empty, at least 1 item is required"]

    all_errors = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            all_errors.append(f"Item #{idx} is not a valid JSON object")
            continue
        item_errors = validate_item(item, idx)
        all_errors.extend(item_errors)

    return data, all_errors

def load_and_validate_file(filepath: str) -> List[Dict[str, Any]]:
    """
    Reads a JSON file from disk and performs full validation.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise CalibrationValidationError(f"Invalid JSON syntax in {filepath}: {str(e)}")

    items, errors = validate_dataset(data)
    if errors:
        error_summary = "\n  - ".join(errors)
        raise CalibrationValidationError(f"Validation failed with {len(errors)} error(s):\n  - {error_summary}")

    return items

def compute_content_hash(item: Dict[str, Any]) -> str:
    """
    Computes a deterministic SHA-256 content hash for O(1) deduplication.
    """
    subsystem = str(item.get("subsystem", "")).strip()
    task_type = str(item.get("task_type", "")).strip()
    prompt_text = str(item.get("prompt_text", "")).strip()
    essay_or_audio = str(item.get("essay_text") or item.get("source_audio_url") or "").strip()
    content = f"{subsystem}:{task_type}:{prompt_text}:{essay_or_audio}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def deduplicate_in_memory(items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """
    Removes duplicate items within the incoming dataset in-memory using content_hash.
    Returns (deduped_items, duplicate_count).
    """
    seen = set()
    deduped = []
    duplicates = 0
    for item in items:
        h = item.get("content_hash") or compute_content_hash(item)
        item["content_hash"] = h
        if h in seen:
            duplicates += 1
        else:
            seen.add(h)
            deduped.append(item)
    return deduped, duplicates

def deduplicate_against_db(cur, items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """
    Checks for existing items in PostgreSQL using content_hash and returns (new_items, skipped_count).
    """
    if not items:
        return [], 0

    cur.execute(
        "SELECT content_hash FROM calibration_corpus_items WHERE content_hash IS NOT NULL"
    )
    existing_hashes = {row[0] for row in cur.fetchall() if row[0]}

    new_items = []
    skipped = 0
    for item in items:
        h = item.get("content_hash") or compute_content_hash(item)
        item["content_hash"] = h
        if h not in existing_hashes:
            new_items.append(item)
            existing_hashes.add(h)
        else:
            skipped += 1

    return new_items, skipped

def insert_items_postgres(items: List[Dict[str, Any]], db_url: str, batch_id: uuid.UUID) -> Tuple[int, int]:
    """
    Inserts validated items into PostgreSQL calibration_corpus_items table idempotently.
    Returns (inserted_count, skipped_count).
    """
    deduped_items, mem_skipped = deduplicate_in_memory(items)

    try:
        import psycopg2
        from psycopg2.extras import execute_values
    except ImportError:
        try:
            import psycopg
            return _insert_items_psycopg3(deduped_items, db_url, batch_id, mem_skipped)
        except ImportError:
            raise RuntimeError(
                "Neither 'psycopg2' nor 'psycopg' is installed. "
                "Please run: pip install psycopg2-binary or pip install psycopg"
            )

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            insertable_items, db_skipped = deduplicate_against_db(cur, deduped_items)
            total_skipped = mem_skipped + db_skipped

            if not insertable_items:
                return 0, total_skipped

            insert_query = """
                INSERT INTO calibration_corpus_items (
                    id, subsystem, task_type, prompt_text, essay_text,
                    source_audio_url, source_audio_duration_seconds, source_transcript,
                    calibration_hold_until, target_band_stratum, dataset_split,
                    split_assigned_at, split_locked_at, intake_batch_id, content_hash,
                    status, version
                ) VALUES %s
            """
            records = []
            for item in insertable_items:
                records.append((
                    item.get("id", str(uuid.uuid4())),
                    item["subsystem"],
                    item["task_type"],
                    item["prompt_text"],
                    item.get("essay_text"),
                    item.get("source_audio_url"),
                    item.get("source_audio_duration_seconds"),
                    item.get("source_transcript"),
                    item.get("calibration_hold_until"),
                    item["target_band_stratum"],
                    item.get("dataset_split", "UNASSIGNED"),
                    item.get("split_assigned_at"),
                    item.get("split_locked_at"),
                    str(batch_id),
                    item.get("content_hash") or compute_content_hash(item),
                    item.get("status", "PENDING_RATING"),
                    0
                ))

            execute_values(cur, insert_query, records)
            conn.commit()
            return len(records), total_skipped
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        raise exc
    finally:
        conn.close()

def _insert_items_psycopg3(items: List[Dict[str, Any]], db_url: str, batch_id: uuid.UUID, mem_skipped: int = 0) -> Tuple[int, int]:
    import psycopg
    with psycopg.connect(db_url) as conn:
        try:
            with conn.cursor() as cur:
                insertable_items, db_skipped = deduplicate_against_db(cur, items)
                total_skipped = mem_skipped + db_skipped

                if not insertable_items:
                    return 0, total_skipped

                insert_query = """
                    INSERT INTO calibration_corpus_items (
                        id, subsystem, task_type, prompt_text, essay_text,
                        source_audio_url, source_audio_duration_seconds, source_transcript,
                        calibration_hold_until, target_band_stratum, dataset_split,
                        split_assigned_at, split_locked_at, intake_batch_id, content_hash,
                        status, version
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s
                    )
                """
                for item in insertable_items:
                    cur.execute(insert_query, (
                        item.get("id", str(uuid.uuid4())),
                        item["subsystem"],
                        item["task_type"],
                        item["prompt_text"],
                        item.get("essay_text"),
                        item.get("source_audio_url"),
                        item.get("source_audio_duration_seconds"),
                        item.get("source_transcript"),
                        item.get("calibration_hold_until"),
                        item["target_band_stratum"],
                        item.get("dataset_split", "UNASSIGNED"),
                        item.get("split_assigned_at"),
                        item.get("split_locked_at"),
                        str(batch_id),
                        item.get("content_hash") or compute_content_hash(item),
                        item.get("status", "PENDING_RATING"),
                        0
                    ))
                conn.commit()
                return len(insertable_items), total_skipped
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            raise exc

def main():
    parser = argparse.ArgumentParser(
        description="Intake CLI tool for Golden Calibration Corpus Foundation."
    )
    parser.add_argument(
        "--file", "-f",
        required=True,
        help="Path to JSON dataset fixture file containing calibration items."
    )
    parser.add_argument(
        "--db-url", "-d",
        default=os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/engonow_lms"),
        help="PostgreSQL connection string (defaults to DATABASE_URL or localhost:5432/engonow_lms)."
    )
    parser.add_argument(
        "--batch-id", "-b",
        default=None,
        help="Optional UUID batch identifier. If omitted, a fresh UUID4 will be generated."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform strict schema and domain validation without connecting to PostgreSQL."
    )

    args = parser.parse_args()

    print("=" * 70)
    print("[ENGONOW AI LMS] Golden Calibration Corpus Intake Tool")
    print("=" * 70)
    print(f"Input File: {args.file}")

    # Generate or parse Batch ID
    if args.batch_id:
        try:
            batch_id = uuid.UUID(args.batch_id)
        except ValueError:
            print(f"[ERROR] Provided --batch-id '{args.batch_id}' is not a valid UUID", file=sys.stderr)
            sys.exit(1)
    else:
        batch_id = uuid.uuid4()

    print(f"Batch ID:   {batch_id}")

    try:
        items = load_and_validate_file(args.file)
        print(f"[SUCCESS] Validation passed: {len(items)} item(s) strictly conform to schema.")
    except Exception as e:
        print(f"[ERROR] Ingestion aborted due to validation failure:\n{str(e)}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("[DRY RUN] Dry-run mode active. Zero database mutations executed.")
        sys.exit(0)

    print(f"Connecting to database: {args.db_url.split('@')[-1] if '@' in args.db_url else args.db_url}")
    try:
        inserted, skipped = insert_items_postgres(items, args.db_url, batch_id)
        if skipped > 0:
            print(f"[SUCCESS] Ingested {inserted} new calibration corpus item(s) into database ({skipped} duplicate(s) skipped)!")
        else:
            print(f"[SUCCESS] Ingested {inserted} calibration corpus item(s) into database!")
        print("=" * 70)
    except Exception as e:
        error_msg = str(e)
        if any(keyword in error_msg.lower() for keyword in ["unique", "duplicate", "integrity", "uq_"]):
            print(f"[ERROR] Database unique constraint collision or duplicate item detected:\n{error_msg}", file=sys.stderr)
        else:
            print(f"[ERROR] Database ingestion failed: {error_msg}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
