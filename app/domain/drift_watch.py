"""Drift watch — concept-drift detector over `model_performance_metrics`.

M.4.3 mitigation for B-12 (concept drift / regime change). The
realistic story for a 14-year backtest deployed in 2026 is that
yesterday's model is wrong tomorrow; this module surfaces metric
drift before it bites operators.

Approach: split the persisted metric rows for a given `model_version`
into a `baseline` window (oldest half) and a `recent` window (newest
half) and compare medians of the headline KPIs (mae_pm10,
breach_recall, ece, calibration_error). Per-metric absolute deltas
above the threshold table below emit a `DriftAlert`. Cheap, no
feature-distribution snapshots required, uses what we already store.

This is *metric drift*, not feature drift. Feature drift would catch
upstream sensor changes; metric drift catches downstream model decay
— good enough at single-station observational scale. Feature-drift
PSI/KL is post-M (needs feature distributions stored per row).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import median

# Per-metric absolute drift thresholds. Tuned conservatively — these
# are detection thresholds, not gates; a DriftAlert is informational,
# not a hard block. Operator response is part of the M.4.3 + post-M
# operational playbook.
DRIFT_THRESHOLDS: dict[str, float] = {
    # PM10 MAE in µg/m³ — 5 µg/m³ shift over the daily WHO threshold (45)
    # is ~11% relative. Big enough to matter, small enough to detect.
    "mae_pm10": 5.0,
    # Probability metrics — 10 percentage-points absolute is a regime
    # change you cannot ignore.
    "breach_recall": 0.10,
    "breach_precision": 0.10,
    "false_positive_rate": 0.10,
    "false_negative_rate": 0.10,
    # Calibration metrics — half the M.4.1 acceptance gate (0.05).
    "ece": 0.025,
    "calibration_error": 0.05,
}

MIN_SAMPLES_DEFAULT = 4


@dataclass(frozen=True)
class DriftAlert:
    """One detected per-metric drift between baseline and recent."""

    model_version: str
    metric_name: str
    baseline_value: float
    recent_value: float
    delta: float
    threshold: float
    baseline_sample_count: int
    recent_sample_count: int
    detected_at: datetime


def _extract(row: dict[str, object], key: str) -> float | None:
    """Return numeric metric value or None if missing/non-numeric."""
    value = row.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _median_or_none(values: list[float]) -> float | None:
    return median(values) if values else None


def compute_drift(
    rows: list[dict[str, object]],
    *,
    model_version: str,
    detected_at: datetime,
    min_samples: int = MIN_SAMPLES_DEFAULT,
) -> list[DriftAlert]:
    """Walk metric rows for one `model_version`; emit drift alerts.

    `rows` is a list of metric_payload dicts in evaluated_at-ascending
    order. We split the rows in half by index — the oldest half is the
    baseline, the newest half is the recent comparison set. Median is
    used over mean for robustness against single-row outliers.

    `min_samples` is the floor on each side before drift is computed.
    Below the floor we return [] — not enough data to claim drift.

    Returns one `DriftAlert` per metric whose `|recent_median -
    baseline_median| > DRIFT_THRESHOLDS[metric]`. Stable order:
    iteration order of `DRIFT_THRESHOLDS`.
    """
    if len(rows) < min_samples * 2:
        return []

    midpoint = len(rows) // 2
    baseline_rows = rows[:midpoint]
    recent_rows = rows[midpoint:]

    alerts: list[DriftAlert] = []
    for metric_name, threshold in DRIFT_THRESHOLDS.items():
        baseline_values = [
            v for r in baseline_rows
            if (v := _extract(r, metric_name)) is not None
        ]
        recent_values = [
            v for r in recent_rows
            if (v := _extract(r, metric_name)) is not None
        ]
        if len(baseline_values) < min_samples or len(recent_values) < min_samples:
            continue

        b_med = _median_or_none(baseline_values)
        r_med = _median_or_none(recent_values)
        if b_med is None or r_med is None:
            continue

        delta = abs(r_med - b_med)
        if delta > threshold:
            alerts.append(
                DriftAlert(
                    model_version=model_version,
                    metric_name=metric_name,
                    baseline_value=b_med,
                    recent_value=r_med,
                    delta=delta,
                    threshold=threshold,
                    baseline_sample_count=len(baseline_values),
                    recent_sample_count=len(recent_values),
                    detected_at=detected_at,
                )
            )
    return alerts


__all__ = [
    "DRIFT_THRESHOLDS",
    "MIN_SAMPLES_DEFAULT",
    "DriftAlert",
    "compute_drift",
]
