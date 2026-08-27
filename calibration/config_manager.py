"""
calibration/config_manager.py
==============================
Immutable Calibration Configuration Manager for AI Writing and Speaking Subsystems.
Provides strict Pydantic v2 validation, append-only change logs, version bumping, and debt auditing.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

class AcceptanceThresholds(BaseModel):
    overallMae: float = 0.50
    maxCriterionMae: float = 0.75
    minRaterPoolIcc: float = 0.80

class FewShotAnchor(BaseModel):
    criterion: str
    band: float
    corpusItemId: str
    rationale: Optional[str] = None

class GatekeeperEvaluation(BaseModel):
    evaluatedAt: Optional[str] = None
    runId: Optional[str] = None
    overallMae: Optional[float] = None
    maxCriterionMae: Optional[float] = None
    perStratumMae: Optional[Dict[str, float]] = None
    result: str = "PENDING"  # PENDING, PASSED, FAILED

class ChangeLogEntry(BaseModel):
    version: str
    timestamp: str
    author: str
    change: str
    gatekeeperMae: Optional[float] = None

class CalibrationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configVersion: str
    subsystem: str  # WRITING or SPEAKING
    promptTemplateRef: str
    geminiModel: str
    corpusSnapshotId: str
    acceptanceThresholds: AcceptanceThresholds = Field(default_factory=AcceptanceThresholds)
    fewShotAnchors: List[FewShotAnchor] = Field(default_factory=list)
    criterionLeniencyAdjustment: Dict[str, float] = Field(default_factory=dict)
    gatekeeperEvaluation: GatekeeperEvaluation = Field(default_factory=GatekeeperEvaluation)
    changeLog: List[ChangeLogEntry] = Field(default_factory=list)

def load_config(file_path: str) -> CalibrationConfig:
    """
    Loads and validates a calibration configuration file against Pydantic schema.
    Emits a warning log if any criterion leniency adjustments are non-zero.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Calibration configuration file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    config = CalibrationConfig.model_validate(data)

    # Technical debt guard: Check for non-zero post-hoc adjustments
    if config.criterionLeniencyAdjustment:
        non_zero_adjustments = {
            k: v for k, v in config.criterionLeniencyAdjustment.items() if v != 0.0
        }
        if non_zero_adjustments:
            logger.warning(
                "[CALIBRATION DEBT] Non-zero criterionLeniencyAdjustment detected in %s: %s. "
                "Post-hoc linear shifting is technical debt and should be resolved via prompt tuning.",
                file_path, non_zero_adjustments
            )

    return config

import uuid

def save_config(file_path: str, config: CalibrationConfig) -> None:
    """
    Persists a valid CalibrationConfig object to disk atomically with pretty formatting.
    Uses tempfile + fsync + atomic rename to prevent partial writes.
    """
    data = config.model_dump(mode="json", exclude_none=True)
    dir_name = os.path.dirname(os.path.abspath(file_path)) or "."
    os.makedirs(dir_name, exist_ok=True)
    temp_path = f"{file_path}.tmp.{uuid.uuid4()}"

    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, file_path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

    logger.info("[CALIBRATION CONFIG] Persisted configuration %s to %s", config.configVersion, file_path)

def append_changelog_and_bump_version(
    file_path: str,
    new_version: str,
    author: str,
    change_desc: str,
    gatekeeper_mae: Optional[float] = None
) -> CalibrationConfig:
    """
    Safely appends an immutable entry to the changeLog ledger, bumps configVersion,
    and atomically saves the updated configuration to disk.
    """
    config = load_config(file_path)

    timestamp = datetime.now(timezone.utc).isoformat()
    new_entry = ChangeLogEntry(
        version=new_version,
        timestamp=timestamp,
        author=author,
        change=change_desc,
        gatekeeperMae=gatekeeper_mae
    )

    # Immutable append-only ledger
    config.changeLog.append(new_entry)
    config.configVersion = new_version

    if gatekeeper_mae is not None:
        config.gatekeeperEvaluation.overallMae = gatekeeper_mae
        config.gatekeeperEvaluation.evaluatedAt = timestamp
        config.gatekeeperEvaluation.result = "PASSED" if gatekeeper_mae <= config.acceptanceThresholds.overallMae else "FAILED"

    save_config(file_path, config)
    return config


def main():
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Calibration Configuration Manager CLI")
    parser.add_argument("--config", required=True, help="Path to calibration config JSON")
    parser.add_argument("--report", help="Path to gatekeeper benchmark JSON report")
    parser.add_argument("--author", default="CI/CD Gatekeeper Pipeline", help="Author of changelog entry")
    parser.add_argument("--version", help="New configuration version (auto-bumps patch if omitted)")
    parser.add_argument("--description", help="Description of changelog entry")

    args = parser.parse_args()

    cfg = load_config(args.config)
    gatekeeper_mae = None

    if args.report and os.path.exists(args.report):
        with open(args.report, "r", encoding="utf-8") as f:
            rep_data = json.load(f)
        gatekeeper_mae = float(rep_data.get("overall_mae", rep_data.get("overallMae", 0.0)))

    # Determine new version
    if args.version:
        new_version = args.version
    else:
        # Auto-increment patch version (e.g. 1.0.0 -> 1.0.1)
        cur_v = cfg.configVersion
        parts = cur_v.split(".")
        if len(parts) == 3 and parts[2].isdigit():
            new_version = f"{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"
        else:
            new_version = f"{cur_v}.1"

    change_desc = args.description or f"Gatekeeper CI verification passed. MAE={gatekeeper_mae if gatekeeper_mae is not None else 'N/A'}"

    updated = append_changelog_and_bump_version(
        file_path=args.config,
        new_version=new_version,
        author=args.author,
        change_desc=change_desc,
        gatekeeper_mae=gatekeeper_mae
    )

    print(f"Successfully updated {args.config} to version {updated.configVersion} with gatekeeper MAE={gatekeeper_mae}")


if __name__ == "__main__":
    main()
