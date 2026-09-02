"""
providers/rounding.py
=====================
Authoritative, deterministic Cambridge IELTS half-band rounding utility.
Uses Python's Decimal arithmetic exclusively with ROUND_HALF_UP to prevent binary
floating-point precision inaccuracies at .25 and .75 boundary points.
"""

from decimal import Decimal, ROUND_HALF_UP
import math
from typing import Any, Optional, Union


def round_to_nearest_half_band(raw_score: Union[float, int, Decimal, str]) -> float:
    """
    Applies official Cambridge IELTS half-band rounding:
    - [0.00, 0.25) -> .0
    - [0.25, 0.75) -> .5
    - [0.75, 1.00) -> next integer .0

    Tie-breaking: values at exactly .25 and .75 round UP to the next half / whole band.
    """
    if raw_score is None:
        raise ValueError("raw_score cannot be None for Cambridge rounding")

    m = Decimal(str(raw_score))
    if m < Decimal("0.0"):
        return 0.0
    if m > Decimal("9.0"):
        return 9.0

    floor_val = Decimal(str(math.floor(float(m))))
    frac = m - floor_val

    quarter = Decimal("0.25")
    three_quarter = Decimal("0.75")
    one = Decimal("1.0")

    if frac < quarter:
        rounded = floor_val
    elif frac < three_quarter:
        rounded = floor_val + Decimal("0.5")
    else:
        rounded = floor_val + one

    res = min(Decimal("9.0"), max(Decimal("0.0"), rounded))
    return float(res.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def calculate_overall_band(
    fc: Optional[float] = None,
    lr: Optional[float] = None,
    gra: Optional[float] = None,
    pr: Optional[float] = None,
) -> Optional[float]:
    """
    Calculates the Cambridge IELTS overall band score from 4 criteria:
    - If all 4 criteria are present: computes arithmetic mean and applies Cambridge rounding.
    - If any criterion is None (partial acoustic exclusion): computes arithmetic mean
      across only the available scorable criteria and rounds with Cambridge rule.
    - If all criteria are None: returns None.
    """
    valid_scores = []
    for s in (fc, lr, gra, pr):
        if s is not None:
            if isinstance(s, float) and (math.isnan(s) or math.isinf(s)):
                continue
            valid_scores.append(Decimal(str(s)))

    if not valid_scores:
        return None

    mean_val = sum(valid_scores) / Decimal(len(valid_scores))
    return round_to_nearest_half_band(mean_val)


def is_legal_band_value(value: Any) -> bool:
    """
    Validates whether a value is an official legal IELTS band score:
    - Must be a number between 0.0 and 9.0 inclusive.
    - Must be in 0.5 step increments (0.0, 0.5, 1.0, ..., 8.5, 9.0).
    """
    if value is None:
        return False
    try:
        if isinstance(value, str):
            v_clean = value.strip()
            if not v_clean:
                return False
            v_float = float(v_clean)
        elif isinstance(value, (int, float, Decimal)):
            v_float = float(value)
        else:
            return False

        if math.isnan(v_float) or math.isinf(v_float):
            return False
        if not (0.0 <= v_float <= 9.0):
            return False
        return round(v_float * 2, 4) % 1.0 == 0.0
    except Exception:
        return False
