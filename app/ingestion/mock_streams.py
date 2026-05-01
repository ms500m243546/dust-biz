"""Mock data stream generators.

Reproducible synthetic data for sensor / weather / equipment streams.
Operationally shaped: diurnal patterns, parameterized noise, occasional
spikes - not pretty curves. Real models trained on this would still
overfit, so production swaps these out for real adapters; Phase J
shows a "DEMO DATA" badge whenever the meta endpoint reports
`mock_mode=True`.

Functions return Pydantic schemas (the wire/contract format), not ORM
rows. Callers (the seed CLI, integration tests) decide whether to POST
them through the API or write directly via repositories.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from app.schemas.equipment import RawEquipmentActivitySchema
from app.schemas.sensor import RawSensorReadingSchema
from app.schemas.weather import RawWeatherReadingSchema


def _diurnal_factor(t: datetime, peak_hour: int = 14) -> float:
    """0.5..1.5 sine wave peaking at `peak_hour` (default mid-afternoon).

    Mining activity, dryness, and resulting dust generation all tend to
    peak in mid-afternoon; 06:00 is the trough.
    """
    phase = (t.hour + t.minute / 60 - peak_hour) / 24 * 2 * math.pi
    return 1.0 + 0.5 * math.cos(phase)


def generate_sensor_readings(
    sensor_id: str,
    start: datetime,
    duration: timedelta,
    *,
    interval_seconds: int = 60,
    pm10_baseline: float = 80.0,
    pm10_noise_sigma: float = 10.0,
    spike_probability: float = 0.02,
    spike_magnitude: tuple[float, float] = (50.0, 150.0),
    seed: int = 42,
) -> Iterator[RawSensorReadingSchema]:
    """Yield PM10 readings shaped by a diurnal curve plus Gaussian noise.

    Spikes simulate dust events; their probability and magnitude are
    parameterised so tests can make them deterministic and the demo CLI
    can dial them up for visible behavior.
    """
    rng = random.Random(seed)
    end = start + duration
    t = start
    while t < end:
        diurnal = _diurnal_factor(t)
        pm10 = pm10_baseline * diurnal + rng.gauss(0.0, pm10_noise_sigma)
        if rng.random() < spike_probability:
            pm10 += rng.uniform(*spike_magnitude)
        pm10 = max(0.0, pm10)
        yield RawSensorReadingSchema(
            sensor_id=sensor_id,
            timestamp=t,
            raw_value={"pm10_ugm3": round(pm10, 2)},
            source_quality_hint=0.9,
        )
        t += timedelta(seconds=interval_seconds)


def generate_weather_readings(
    source: str,
    start: datetime,
    duration: timedelta,
    *,
    interval_seconds: int = 300,
    zone_id: str | None = None,
    wind_speed_baseline_ms: float = 6.0,
    wind_direction_drift_deg_per_hour: float = 15.0,
    seed: int = 43,
) -> Iterator[RawWeatherReadingSchema]:
    rng = random.Random(seed)
    end = start + duration
    t = start
    direction = rng.uniform(0.0, 360.0)
    while t < end:
        diurnal = _diurnal_factor(t, peak_hour=15)
        wind = max(0.0, wind_speed_baseline_ms * diurnal + rng.gauss(0.0, 1.5))
        gust = wind + max(0.0, rng.gauss(2.0, 1.0))
        # slow random walk in direction
        elapsed_hours = (t - start).total_seconds() / 3600
        direction = (
            direction + rng.gauss(0.0, wind_direction_drift_deg_per_hour) * elapsed_hours / 24
        ) % 360.0
        humidity = max(10.0, min(95.0, 55.0 - 20.0 * (diurnal - 1.0) + rng.gauss(0.0, 5.0)))
        temperature = 18.0 + 8.0 * (diurnal - 1.0) + rng.gauss(0.0, 1.0)
        yield RawWeatherReadingSchema(
            source=source,
            zone_id=zone_id,
            timestamp=t,
            wind_speed_ms=round(wind, 2),
            wind_direction_deg=round(direction, 1),
            gust_speed_ms=round(gust, 2),
            humidity_pct=round(humidity, 1),
            temperature_c=round(temperature, 1),
        )
        t += timedelta(seconds=interval_seconds)


def generate_equipment_activity(
    equipment_id: str,
    start: datetime,
    duration: timedelta,
    *,
    interval_seconds: int = 120,
    zone_id: str | None = "Haul_Road_C",
    activity_choices: tuple[str, ...] = ("hauling", "loading", "idle"),
    seed: int = 44,
) -> Iterator[RawEquipmentActivitySchema]:
    rng = random.Random(seed)
    end = start + duration
    t = start
    while t < end:
        diurnal = _diurnal_factor(t)
        # fewer idle samples mid-shift
        weights = [diurnal, diurnal * 0.6, max(0.2, 2.0 - diurnal)]
        activity = rng.choices(activity_choices, weights=weights, k=1)[0]
        speed = (
            round(rng.uniform(20.0, 40.0) * diurnal, 1)
            if activity == "hauling"
            else (round(rng.uniform(0.0, 5.0), 1) if activity == "loading" else 0.0)
        )
        tonnage = round(rng.uniform(180.0, 240.0), 1) if activity == "hauling" else None
        yield RawEquipmentActivitySchema(
            equipment_id=equipment_id,
            timestamp=t,
            activity_type=activity,  # type: ignore[arg-type]
            zone_id=zone_id,
            speed_kmh=speed,
            tonnage=tonnage,
        )
        t += timedelta(seconds=interval_seconds)


def utc_now() -> datetime:
    """Wrapper so callers don't have to import datetime + UTC themselves."""
    return datetime.now(UTC)
