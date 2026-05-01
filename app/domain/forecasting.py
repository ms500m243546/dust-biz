"""Forecast orchestration (S5 -> registry -> S6 -> audit).

`issue_forecast` composes the four moving parts of an issued
forecast:
  1. Compute the zone's MineState (S4).
  2. Score the contributing PM sensors' health (S2).
  3. Build a FeatureRecord (S5) and persist it.
  4. Resolve the current DustForecastModel from the registry,
     call predict() with the data-quality multiplier (G4) and
     audit fields (G5, G15).
  5. Persist the resulting DustForecastSchema as a DustPrediction
     row keyed `PRED-YYYYMMDD-NNNN` (data-contracts.md line 132).

The function is sync + session-bound to match the rest of the
Domain layer. It does NOT decide which model to use - the registry
does. That keeps shadow-evaluation (Phase K) a registry-only swap.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.data_quality import SensorHealthScorer
from app.domain.features import build_feature_record
from app.domain.mine_state import compute_zone_state
from app.models import registry
from app.schemas.features import FeatureRecordSchema
from app.schemas.forecasts import (
    DustForecastSchema,
    ForecastHorizon,
    ForecastTargetSchema,
)
from app.storage.models import (
    DustPrediction,
    EquipmentActivity,
    FeatureRecord,
    Sensor,
    SensorReading,
    WeatherReading,
    Zone,
)
from app.storage.repositories.features import FeatureRepository
from app.storage.repositories.forecasts import DustPredictionRepository
from app.storage.repositories.sensor_readings import SensorReadingRepository
from app.storage.repositories.zones import ZoneRepository


class TargetNotFoundError(LookupError):
    """Raised when the orchestrator can't resolve the requested target."""


def issue_forecast(
    *,
    session: Session,
    target: ForecastTargetSchema,
    horizon: ForecastHorizon,
    window_minutes: int = 60,
    now: datetime | None = None,
) -> DustForecastSchema:
    """Compose features + model + audit for one (target, horizon).

    `target.target_kind` of "zone" is the MVP path. "sensor" targets
    will be wired in Phase J once the dashboard surfaces compliance
    stations directly; today they resolve to the sensor's zone for
    feature build, then the forecast is keyed back to the sensor.
    """

    issued_at = (now or datetime.now(UTC)).replace(microsecond=0)

    zone = _resolve_zone(session, target)
    since = issued_at - timedelta(minutes=window_minutes)

    activity = _recent_activity_for_zone(session, zone.zone_id, since)
    weather = _recent_weather_for_mine(session, zone.mine_id, since)
    downwind_candidates = ZoneRepository(session).get_for_mine(zone.mine_id)

    zone_state = compute_zone_state(
        zone=zone,
        now=issued_at.replace(tzinfo=None),
        window_minutes=window_minutes,
        recent_activity=activity,
        recent_weather=weather,
        downwind_candidates=downwind_candidates,
    )

    pm_sensors = _pm_sensors_for_zone(session, zone.zone_id)
    pm_readings = _recent_pm_readings(session, [s.sensor_id for s in pm_sensors], since)
    quality_score, quality_warnings = _score_pm_quality(session, pm_sensors, issued_at)

    feature_record = build_feature_record(
        zone_state=zone_state,
        pm_readings=pm_readings,
        weather_readings=weather,
        as_of=issued_at.replace(tzinfo=None),
        lookback_minutes=window_minutes,
    )
    _persist_feature_record(session, feature_record)

    # The registry's structural Protocol covers (model_kind, model_version)
    # only; the per-kind predict() signature is owned by docs/model-contracts.md
    # (DustForecastModel). Declared Any here so the orchestrator does not
    # silently couple to a single concrete forecaster class.
    model: Any = registry.get_current("dust_forecast")
    forecast: DustForecastSchema = model.predict(
        features=feature_record,
        target=target,
        horizon=horizon,
        input_data_quality_score=quality_score,
        data_quality_warnings=quality_warnings,
        input_record_ids=_collect_record_ids(pm_readings, weather),
        now=issued_at,
    )

    _persist_forecast(session, forecast)
    return forecast


def _resolve_zone(session: Session, target: ForecastTargetSchema) -> Zone:
    repo = ZoneRepository(session)
    if target.target_kind == "zone":
        zone = repo.get(target.target_id)
        if zone is None:
            raise TargetNotFoundError(f"zone not found: {target.target_id}")
        return zone

    sensor = session.get(Sensor, target.target_id)
    if sensor is None or sensor.zone_id is None:
        raise TargetNotFoundError(
            f"sensor target requires a sensor with assigned zone: {target.target_id}"
        )
    zone = repo.get(sensor.zone_id)
    if zone is None:
        raise TargetNotFoundError(f"sensor's zone not found: {sensor.zone_id}")
    return zone


def _recent_activity_for_zone(
    session: Session, zone_id: str, since: datetime
) -> list[EquipmentActivity]:
    stmt = (
        select(EquipmentActivity)
        .where(EquipmentActivity.zone_id == zone_id)
        .where(EquipmentActivity.timestamp >= since.replace(tzinfo=None))
        .order_by(EquipmentActivity.timestamp.desc())
    )
    return list(session.execute(stmt).scalars())


def _recent_weather_for_mine(
    session: Session, mine_id: str, since: datetime
) -> list[WeatherReading]:
    mine_zone_ids = list(
        session.execute(select(Zone.zone_id).where(Zone.mine_id == mine_id)).scalars()
    )
    stmt = (
        select(WeatherReading)
        .where(WeatherReading.timestamp >= since.replace(tzinfo=None))
        .where(
            (WeatherReading.zone_id.is_(None))
            | (WeatherReading.zone_id.in_(mine_zone_ids))
        )
        .order_by(WeatherReading.timestamp.desc())
    )
    return list(session.execute(stmt).scalars())


def _pm_sensors_for_zone(session: Session, zone_id: str) -> list[Sensor]:
    stmt = (
        select(Sensor)
        .where(Sensor.zone_id == zone_id)
        .where(Sensor.sensor_type.in_(("pm10", "pm25", "multi")))
    )
    return list(session.execute(stmt).scalars())


def _recent_pm_readings(
    session: Session, sensor_ids: list[str], since: datetime
) -> list[SensorReading]:
    if not sensor_ids:
        return []
    stmt = (
        select(SensorReading)
        .where(SensorReading.sensor_id.in_(sensor_ids))
        .where(SensorReading.timestamp >= since.replace(tzinfo=None))
        .order_by(SensorReading.timestamp.desc())
    )
    return list(session.execute(stmt).scalars())


def _score_pm_quality(
    session: Session, sensors: list[Sensor], now: datetime
) -> tuple[float, list[str]]:
    """Average sensor health multiplier across the zone's PM sensors.

    Empty sensor set -> score 0.5 with a `no_pm_sensors_for_zone`
    warning. Mirrors the spirit of Guardrail 5 (warn, don't fabricate)
    while still letting the forecast issue with low confidence.
    """
    if not sensors:
        return 0.5, ["no_pm_sensors_for_zone"]

    scorer = SensorHealthScorer(SensorReadingRepository(session))
    multipliers: list[float] = []
    warnings: list[str] = []
    for sensor in sensors:
        report = scorer.score(sensor.sensor_id, now=now)
        multipliers.append(report.downstream_confidence_multiplier)
        if report.status != "healthy":
            warnings.append(f"{sensor.sensor_id}:{report.status}")
    avg = sum(multipliers) / len(multipliers)
    return round(avg, 3), warnings


def _collect_record_ids(
    pm_readings: list[SensorReading], weather: list[WeatherReading]
) -> list[str]:
    ids: list[str] = []
    ids.extend(f"sr-{r.reading_id}" for r in pm_readings if r.reading_id is not None)
    ids.extend(f"wr-{r.reading_id}" for r in weather if r.reading_id is not None)
    return ids


def _persist_feature_record(session: Session, schema: FeatureRecordSchema) -> None:
    row = FeatureRecord(
        timestamp=schema.timestamp,
        zone_id=schema.zone_id,
        feature_pipeline_version=schema.feature_pipeline_version,
        feature_payload=dict(schema.feature_payload),
        missing_inputs=list(schema.missing_inputs),
    )
    FeatureRepository(session).add(row)


def _persist_forecast(session: Session, forecast: DustForecastSchema) -> DustPrediction:
    repo = DustPredictionRepository(session)
    pid = repo.next_prediction_id(on_date=forecast.issued_at.date())
    row = DustPrediction(
        prediction_id=pid,
        issued_at=forecast.issued_at.replace(tzinfo=None),
        target_kind=forecast.target_kind,
        target_id=forecast.target_id,
        forecast_horizon=forecast.forecast_horizon,
        predicted_pm10=forecast.predicted_pm10,
        predicted_pm25=forecast.predicted_pm25,
        breach_probability=forecast.breach_probability,
        confidence=forecast.confidence,
        main_risk_window=forecast.main_risk_window,
        main_uncertainty=forecast.main_uncertainty,
        model_version=forecast.model_version,
        feature_pipeline_version=forecast.feature_pipeline_version,
        input_data_quality_score=forecast.input_data_quality_score,
        data_quality_warnings=list(forecast.data_quality_warnings),
        source=forecast.source,
        input_record_ids=list(forecast.input_record_ids),
    )
    return repo.add(row)
