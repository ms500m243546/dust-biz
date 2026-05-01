"""Heuristic dust forecasting baseline (S6 first implementation).

Implements `DustForecastModel` per docs/model-contracts.md:
"recent PM trend + wind alignment + surface dryness penalty".
Coefficients are intentionally simple and uncalibrated; this is the
fallback / cold-start model. Trained variants (GBM, neural) plug
into the same Protocol later.

Confidence application (Guardrail 4): callers pass an
`input_data_quality_score`; the model multiplies its raw confidence
by this score so forecasts derived from degraded sensors carry
proportionally lower confidence.

Fallback (Guardrail 11): if required PM features are missing the
model returns a low-confidence forecast flagged
`source = "heuristic_fallback"` rather than raising.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.schemas.features import FeatureRecordSchema
from app.schemas.forecasts import (
    DustForecastSchema,
    ForecastHorizon,
    ForecastTargetSchema,
)

HEURISTIC_VERSION = "dust_forecast_heuristic_v0.1.0"

# Horizon → minutes ahead. Used only for the "main_risk_window" string.
_HORIZON_MINUTES: dict[ForecastHorizon, int] = {
    "15min": 15,
    "30min": 30,
    "60min": 60,
    "120min": 120,
    "24h": 24 * 60,
}

# Coarse breach thresholds (μg/m³). Site-specific thresholds belong in
# site_config; the baseline uses generic values until the site-config
# threshold field is wired (Phase H).
_PM10_BREACH = 150.0


class HeuristicBaselineForecaster:
    """First implementation of `DustForecastModel`.

    `model_kind` is typed `str` (not `Literal["dust_forecast"]`) for
    Protocol-compatibility with the registry's structural type;
    docs/model-contracts.md declares the Literal at the Protocol
    level, while implementations narrow at runtime via the assigned
    string value.
    """

    model_kind: str = "dust_forecast"

    def __init__(self, model_version: str = HEURISTIC_VERSION) -> None:
        self.model_version = model_version

    def predict(
        self,
        *,
        features: FeatureRecordSchema,
        target: ForecastTargetSchema,
        horizon: ForecastHorizon,
        input_data_quality_score: float = 1.0,
        data_quality_warnings: list[str] | None = None,
        input_record_ids: list[str] | None = None,
        now: datetime | None = None,
    ) -> DustForecastSchema:
        warnings = list(data_quality_warnings or [])
        record_ids = list(input_record_ids or [])
        issued_at = now or datetime.now(UTC)

        payload = features.feature_payload
        pm10_recent = _coerce_float(payload.get("pm.pm10_avg_15min"))
        pm25_recent = _coerce_float(payload.get("pm.pm25_avg_15min"))
        pm10_trend = _coerce_float(payload.get("pm.pm10_trend_per_min")) or 0.0
        pm25_trend = _coerce_float(payload.get("pm.pm25_trend_per_min")) or 0.0
        wind_speed = _coerce_float(payload.get("wind.speed_ms")) or 0.0
        humidity = _coerce_float(payload.get("wind.humidity_pct"))

        if pm10_recent is None or pm25_recent is None:
            return self._fallback(
                features=features,
                target=target,
                horizon=horizon,
                issued_at=issued_at,
                input_data_quality_score=input_data_quality_score,
                data_quality_warnings=warnings + ["pm_features_missing"],
                input_record_ids=record_ids,
            )

        horizon_min = _HORIZON_MINUTES[horizon]
        # Linear projection of recent trend, scaled by horizon. Capped
        # against runaway extrapolation: a 60-min projection beyond
        # 3x the recent average is treated as 3x.
        projected_pm10 = _clip(
            pm10_recent + pm10_trend * horizon_min,
            lo=0.0,
            hi=max(pm10_recent * 3.0, 50.0),
        )
        projected_pm25 = _clip(
            pm25_recent + pm25_trend * horizon_min,
            lo=0.0,
            hi=max(pm25_recent * 3.0, 25.0),
        )

        # Wind alignment / dryness penalty: high wind exposure + low
        # humidity bumps PM10 by up to 25% (haul-road + dry-surface
        # heuristic from docs/mining-domain.md).
        dryness_factor = 1.0
        wind_exposure = payload.get("state.wind_exposure")
        if wind_exposure == "high":
            dryness_factor *= 1.15
        if humidity is not None and humidity < 30.0:
            dryness_factor *= 1.10
        dust_potential = payload.get("state.dust_generation_potential")
        if dust_potential == "high":
            dryness_factor *= 1.10
        projected_pm10 *= dryness_factor
        projected_pm25 *= dryness_factor

        breach_prob = _breach_probability(projected_pm10, _PM10_BREACH)

        # Raw confidence: stronger when we have a clear trend signal,
        # near-stationary readings, and recent weather. Sliding scale.
        raw_conf = 0.55
        if "weather_readings_missing" not in features.missing_inputs:
            raw_conf += 0.15
        if "pm10_readings_missing" not in features.missing_inputs:
            raw_conf += 0.10
        if abs(pm10_trend) < 1.0 and wind_speed < 7.0:
            raw_conf += 0.10
        raw_conf = _clip(raw_conf, lo=0.0, hi=0.9)

        # G4: downstream consumers must apply the data-quality
        # multiplier. We accept it scaled into our own confidence.
        confidence = round(raw_conf * input_data_quality_score, 3)

        risk_window = _risk_window(issued_at, horizon_min)
        uncertainty = _uncertainty_note(
            wind_speed=wind_speed,
            missing=features.missing_inputs,
            trend=pm10_trend,
        )

        return DustForecastSchema(
            issued_at=issued_at,
            target_kind=target.target_kind,
            target_id=target.target_id,
            forecast_horizon=horizon,
            predicted_pm10=round(projected_pm10, 1),
            predicted_pm25=round(projected_pm25, 1),
            breach_probability=round(breach_prob, 3),
            confidence=confidence,
            main_risk_window=risk_window,
            main_uncertainty=uncertainty,
            model_version=self.model_version,
            feature_pipeline_version=features.feature_pipeline_version,
            input_data_quality_score=round(input_data_quality_score, 3),
            data_quality_warnings=warnings,
            source="model",
            input_record_ids=record_ids,
        )

    def _fallback(
        self,
        *,
        features: FeatureRecordSchema,
        target: ForecastTargetSchema,
        horizon: ForecastHorizon,
        issued_at: datetime,
        input_data_quality_score: float,
        data_quality_warnings: list[str],
        input_record_ids: list[str],
    ) -> DustForecastSchema:
        # Conservative default: predict a "moderately elevated"
        # baseline so the operator is alerted to a data gap rather
        # than seeing a fabricated all-clear.
        return DustForecastSchema(
            issued_at=issued_at,
            target_kind=target.target_kind,
            target_id=target.target_id,
            forecast_horizon=horizon,
            predicted_pm10=80.0,
            predicted_pm25=30.0,
            breach_probability=0.3,
            confidence=round(0.2 * input_data_quality_score, 3),
            main_risk_window="unknown - insufficient PM data",
            main_uncertainty="PM features missing; heuristic fallback engaged",
            model_version=self.model_version,
            feature_pipeline_version=features.feature_pipeline_version,
            input_data_quality_score=round(input_data_quality_score, 3),
            data_quality_warnings=data_quality_warnings,
            source="heuristic_fallback",
            input_record_ids=input_record_ids,
        )


def _coerce_float(v: object) -> float | None:
    if isinstance(v, int | float) and not isinstance(v, bool):
        return float(v)
    return None


def _clip(x: float, *, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _breach_probability(predicted_pm10: float, threshold: float) -> float:
    """Smooth ramp around the threshold.

    < 60% of threshold:  ~0.05
    at threshold:        0.5
    >= 1.5x threshold:   ~0.95
    """
    if threshold <= 0:
        return 0.0
    ratio = predicted_pm10 / threshold
    if ratio <= 0.6:
        return 0.05
    if ratio >= 1.5:
        return 0.95
    # Linear between (0.6 -> 0.05) and (1.5 -> 0.95).
    return 0.05 + (ratio - 0.6) * (0.9 / 0.9)


def _risk_window(issued_at: datetime, horizon_minutes: int) -> str:
    start = issued_at.replace(microsecond=0)
    end = start + timedelta(minutes=horizon_minutes)
    return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"


def _uncertainty_note(*, wind_speed: float, missing: list[str], trend: float) -> str:
    notes: list[str] = []
    if wind_speed >= 7.0:
        notes.append("high wind variability")
    if abs(trend) >= 2.0:
        notes.append("steep PM trend")
    for m in missing:
        if m.startswith("weather"):
            notes.append("weather signal degraded")
            break
    if not notes:
        return "low - inputs stable"
    return ", ".join(notes)
