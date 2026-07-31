"""Offline optimization of pronunciation log-probability thresholds."""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.optimize import differential_evolution


THRESHOLD_KEYS = ("band_8", "band_7", "band_6", "band_5", "band_4")
OPTIMIZATION_BOUNDS = ((-1.5, 0.0),) * len(THRESHOLD_KEYS)


class AutoCalibrator:
    """Fit ordered pronunciation-band thresholds to examiner-labelled data."""

    @staticmethod
    def _sort_thresholds_descending(
        thresholds: Sequence[float],
    ) -> np.ndarray:
        ordered = np.sort(np.asarray(thresholds, dtype=float))[::-1].copy()
        if ordered.size != len(THRESHOLD_KEYS):
            raise ValueError(
                f"Exactly {len(THRESHOLD_KEYS)} thresholds are required"
            )
        if not np.all(np.isfinite(ordered)):
            raise ValueError("Thresholds must contain only finite values")

        # Sorting enforces order. nextafter makes that order strictly decreasing
        # even in the unlikely event that the optimizer returns equal values.
        for index in range(1, ordered.size):
            if ordered[index] >= ordered[index - 1]:
                ordered[index] = np.nextafter(
                    ordered[index - 1],
                    -np.inf,
                )
        return ordered

    def objective_function(
        self,
        thresholds: Sequence[float],
        X_logprobs: np.ndarray,
        y_true_bands: np.ndarray,
    ) -> float:
        """Return MAE for one candidate set of ordered thresholds."""
        ordered = self._sort_thresholds_descending(thresholds)
        X = np.asarray(X_logprobs, dtype=float)
        y = np.asarray(y_true_bands, dtype=float)
        if X.shape != y.shape:
            raise ValueError("X_logprobs and y_true_bands must have equal shapes")
        if X.size == 0:
            raise ValueError("Calibration arrays must not be empty")

        predicted_bands = np.select(
            [X > threshold for threshold in ordered],
            [8, 7, 6, 5, 4],
            default=3,
        )
        return float(np.mean(np.abs(predicted_bands - y)))

    def calibrate(self, corpus_data: list[dict[str, Any]]) -> dict[str, Any]:
        """Optimize thresholds from logprobs paired with human PR bands."""
        X, y = self._validate_corpus(corpus_data)
        result = differential_evolution(
            self.objective_function,
            OPTIMIZATION_BOUNDS,
            args=(X, y),
            strategy="best1bin",
            popsize=15,
            seed=42,
        )
        optimized = self._sort_thresholds_descending(result.x)

        config: dict[str, Any] = {
            key: float(value)
            for key, value in zip(THRESHOLD_KEYS, optimized)
        }
        config["updated_at"] = datetime.now(timezone.utc).isoformat()
        return config

    def save_calibration(
        self,
        config_data: Mapping[str, Any],
        filepath: str | os.PathLike[str] = "calibration_config.json",
    ) -> None:
        """Atomically persist a validated calibration as UTF-8 JSON."""
        payload = dict(config_data)
        self._validate_config(payload)

        destination = Path(filepath)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(
                    payload,
                    temporary_file,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            os.replace(temporary_path, destination)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _validate_corpus(
        corpus_data: list[dict[str, Any]],
    ) -> tuple[np.ndarray, np.ndarray]:
        if not corpus_data:
            raise ValueError("corpus_data must contain at least one sample")

        logprobs: list[float] = []
        human_bands: list[int] = []
        for index, sample in enumerate(corpus_data):
            if not isinstance(sample, dict):
                raise TypeError(f"Corpus sample {index} must be a dictionary")
            try:
                logprob = float(sample["logprob"])
                raw_band = sample["human_band"]
            except KeyError as exc:
                raise ValueError(
                    f"Corpus sample {index} is missing {exc.args[0]!r}"
                ) from exc
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Corpus sample {index} contains invalid numeric data"
                ) from exc

            if (
                isinstance(raw_band, bool)
                or not isinstance(raw_band, (int, float))
                or not float(raw_band).is_integer()
            ):
                raise ValueError(
                    f"Corpus sample {index} human_band must be an integer"
                )
            human_band = int(raw_band)
            if not math.isfinite(logprob):
                raise ValueError(
                    f"Corpus sample {index} logprob must be finite"
                )
            if not 1 <= human_band <= 9:
                raise ValueError(
                    f"Corpus sample {index} human_band must be within [1, 9]"
                )

            logprobs.append(logprob)
            human_bands.append(human_band)

        return (
            np.asarray(logprobs, dtype=float),
            np.asarray(human_bands, dtype=float),
        )

    @staticmethod
    def _validate_config(config_data: Mapping[str, Any]) -> None:
        try:
            thresholds = [float(config_data[key]) for key in THRESHOLD_KEYS]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "Calibration config must contain numeric band_8 through band_4"
            ) from exc

        if not all(math.isfinite(value) for value in thresholds):
            raise ValueError("Calibration thresholds must be finite")
        if not all(
            higher > lower
            for higher, lower in zip(thresholds, thresholds[1:])
        ):
            raise ValueError(
                "Calibration thresholds must be strictly decreasing"
            )


def main() -> None:
    """Calibrate a JSON corpus from the command line."""
    parser = argparse.ArgumentParser(
        description=(
            "Optimize pronunciation thresholds from examiner-labelled JSON"
        )
    )
    parser.add_argument(
        "corpus",
        type=Path,
        help="JSON list containing logprob and human_band objects",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("calibration_config.json"),
        help="Destination calibration JSON file",
    )
    args = parser.parse_args()

    with args.corpus.open("r", encoding="utf-8") as corpus_file:
        corpus_data = json.load(corpus_file)
    if not isinstance(corpus_data, list):
        raise ValueError("Calibration corpus JSON must contain a list")

    calibrator = AutoCalibrator()
    config = calibrator.calibrate(corpus_data)
    calibrator.save_calibration(config, args.output)
    print(json.dumps(config, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
