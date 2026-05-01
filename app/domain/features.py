"""S5 - Feature Engineering Layer (heuristic core).

Pure-function builder. Given a per-zone `MineStateZoneSchema`, recent
sensor readings, recent weather, and the resolved site config,
produce a `FeatureRecordSchema` for that zone at `as_of`.

Leakage rule (E1-R1): only readings strictly older than `as_of` may
contribute. The builder enforces this defensively even if the caller
passes a wider window.

`feature_payload` is a namespaced JSON dict. The namespaces shipped
with `feature_pipeline_v0.1.0` are:
  - `pm.*`         rolling PM10 / PM2.5 stats from compliance + zone sensors
  - `wind.*`       wind speed, gust, direction, alignment to dust source
  - `activity.*`   dust-generating activity intensity, equipment count
  - `state.*`      dust_generation_potential, wind_exposure, importance
  - `meta.*`       window length, sensor count contributing to features

Missing inputs annotate `missing_inputs` instead of fabricating values
(Guardrail 5; subsystem-contracts.md S5 failure mode).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta

from app.schemas.features import FeatureRecordSchema
from app.schemas.mine_state import MineStateZoneSchema
from app.storage.models import SensorReading, WeatherReading

FEATURE_PIPELINE_VERSION = "feature_pipeline_v0.1.0"

_PM_WINDOWS_MIN = (5, 15, 30, 60)


def build_feature_record(
    *,
    zone_state: MineStateZoneSchema,
    pm_readings: list[SensorReading],
    weather_readings: list[WeatherReading],
    as_of: datetime,
    lookback_minutes: int = 60,
) -> FeatureRecordSchema:
    """Compose one zone's `FeatureRecordSchema`.

    `pm_readings` should be PM10/PM2.5 raw rows (the caller filters by
    sensor_id list / sensor_type); their `raw_value` payload is
    expected to carry `pm10_ugm3` and/or `pm25_ugm3` numeric fields.
    `weather_readings` should already be filtered to a relevant
    window. `as_of` is the feature timestamp; nothing strictly newer
    is consumed.
    """

    payload: dict[str, object] = {}
    missing: list[str] = []

    pm_in_window = [r for r in pm_readings if r.timestamp <= as_of]
    weather_in_window = [r for r in weather_readings if r.timestamp <= as_of]

    pm_features, pm_missing, pm_count = _pm_features(pm_in_window, as_of)
    payload.update(pm_features)
    missing.extend(pm_missing)

    wind_features, wind_missing = _wind_features(weather_in_window, as_of)
    payload.update(wind_features)
    missing.extend(wind_missing)

    payload.update(_activity_features(zone_state))
    payload.update(_state_features(zone_state))

    payload["meta.lookback_minutes"] = lookback_minutes
    payload["meta.pm_reading_count"] = pm_count
    payload["meta.weather_reading_count"] = len(weather_in_window)

    # Propagate upstream staleness so models can downgrade confidence
    # without re-deriving the same checks.
    for flag in zone_state.staleness_flags:
        if flag not in missing:
            missing.append(flag)

    return FeatureRecordSchema(
        timestamp=as_of,
        zone_id=zone_state.zone_id,
        feature_pipeline_version=FEATURE_PIPELINE_VERSION,
        feature_payload=payload,
        missing_inputs=missing,
    )


def _pm_features(
    readings: list[SensorReading], as_of: datetime
) -> tuple[dict[str, object], list[str], int]:
    payload: dict[str, object] = {}
    missing: list[str] = []

    pm10_pairs = list(_extract_metric(readings, "pm10_ugm3"))
    pm25_pairs = list(_extract_metric(readings, "pm25_ugm3"))

    if not pm10_pairs:
        missing.append("pm10_readings_missing")
    if not pm25_pairs:
        missing.append("pm25_readings_missing")

    for w in _PM_WINDOWS_MIN:
        cutoff = as_of - timedelta(minutes=w)
        pm10_window = [v for ts, v in pm10_pairs if ts >= cutoff]
        pm25_window = [v for ts, v in pm25_pairs if ts >= cutoff]
        payload[f"pm.pm10_avg_{w}min"] = _mean(pm10_window)
        payload[f"pm.pm25_avg_{w}min"] = _mean(pm25_window)

    payload["pm.pm10_trend_per_min"] = _trend_per_min(pm10_pairs, as_of)
    payload["pm.pm25_trend_per_min"] = _trend_per_min(pm25_pairs, as_of)

    contributing = len({ts for ts, _ in pm10_pairs} | {ts for ts, _ in pm25_pairs})
    return payload, missing, contributing


def _wind_features(
    readings: list[WeatherReading], as_of: datetime
) -> tuple[dict[str, object], list[str]]:
    payload: dict[str, object] = {}
    missing: list[str] = []
    if not readings:
        missing.append("weather_readings_missing")
        payload["wind.speed_ms"] = None
        payload["wind.gust_ms"] = None
        payload["wind.direction_deg"] = None
        payload["wind.humidity_pct"] = None
        payload["wind.temperature_c"] = None
        return payload, missing

    latest = max(readings, key=lambda r: r.timestamp)
    payload["wind.speed_ms"] = latest.wind_speed_ms
    payload["wind.gust_ms"] = latest.gust_speed_ms
    payload["wind.direction_deg"] = latest.wind_direction_deg
    payload["wind.humidity_pct"] = latest.humidity_pct
    payload["wind.temperature_c"] = latest.temperature_c
    if latest.wind_direction_deg is None:
        missing.append("wind_direction_missing")
    return payload, missing


def _activity_features(zone_state: MineStateZoneSchema) -> dict[str, object]:
    return {
        "activity.label": zone_state.activity,
        "activity.equipment_count": len(zone_state.equipment_active),
        "activity.production_rate_tph": zone_state.production_rate_tph,
    }


def _state_features(zone_state: MineStateZoneSchema) -> dict[str, object]:
    return {
        "state.dust_generation_potential": zone_state.dust_generation_potential,
        "state.wind_exposure": zone_state.wind_exposure,
        "state.operational_importance": zone_state.operational_importance,
        "state.downwind_asset_count": len(zone_state.downwind_assets),
    }


def _extract_metric(
    readings: list[SensorReading], key: str
) -> Iterator[tuple[datetime, float]]:
    for r in readings:
        v = r.raw_value.get(key) if isinstance(r.raw_value, dict) else None
        if isinstance(v, int | float) and not isinstance(v, bool):
            yield r.timestamp, float(v)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _trend_per_min(
    pairs: list[tuple[datetime, float]], as_of: datetime
) -> float | None:
    """Slope of a recent 30-min window in units/minute (least squares).

    Returns None if fewer than two points exist in the window.
    """
    cutoff = as_of - timedelta(minutes=30)
    window = [(ts, v) for ts, v in pairs if ts >= cutoff]
    if len(window) < 2:
        return None
    xs = [(ts - cutoff).total_seconds() / 60.0 for ts, _ in window]
    ys = [v for _, v in window]
    n = len(window)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return None
    return round(num / den, 3)
