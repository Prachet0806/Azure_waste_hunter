"""Helpers for conservative Azure Monitor metric assessment."""

from __future__ import annotations

import math
import os
from typing import Any


def metric_values(metrics: Any) -> list[float]:
    """Return finite metric samples, preserving valid zero values."""
    values: list[float] = []
    for metric in getattr(metrics, "value", ()) or ():
        for series in getattr(metric, "timeseries", ()) or ():
            for point in getattr(series, "data", ()) or ():
                value = getattr(point, "average", None)
                if value is None:
                    continue
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(number):
                    values.append(number)
    return values


def coverage_status(values: list[float]) -> dict[str, Any]:
    """Assess whether a seven-day daily metric window has enough samples."""
    expected = 7
    minimum = int(os.getenv("MIN_METRIC_SAMPLES", "5"))
    minimum = min(max(minimum, 1), expected)
    count = len(values)
    return {
        "sample_count": count,
        "expected_samples": expected,
        "coverage": round(min(count / expected, 1.0), 3),
        "sufficient": count >= minimum,
        "minimum_samples": minimum,
    }
