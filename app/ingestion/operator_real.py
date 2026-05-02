"""Operator-real ingest adapter (Phase L.5).

Thin adapter that takes operator-format records (dispatch system
exports, telematics CSVs, watering-truck logs) and emits the same
typed `RawSensorReadingSchema` / `RawWeatherReadingSchema` /
`RawEquipmentActivitySchema` records as the public connectors. This
is the slot where Los Pelambres insider data lands.

The adapter is **format-agnostic by design**: it accepts dicts shaped
the way an operator's source system already produces them, mapped
through a small per-source `FieldMap` that names the timestamp,
identifier, and parameter columns. Adding a new operator (or even a
new source system at the same operator) means writing one FieldMap
entry, not a new connector.

Source discriminator is `"operator_real"` regardless of which
operator — downstream consumers (S6 forecasting, S14 join) treat
operator-real records as ground-truth quality (`source_quality_hint
=1.0`).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.schemas.equipment import RawEquipmentActivitySchema
from app.schemas.sensor import RawSensorReadingSchema
from app.schemas.weather import RawWeatherReadingSchema

SOURCE_NAME = "operator_real"


@dataclass(frozen=True)
class FieldMap:
    """Names the columns the adapter pulls from per-row dicts.

    All fields are column names (or dotted paths through a nested
    JSON object) in the operator's source format. Default values
    cover the most common Modular Dispatch / Wenco / MineStar
    exports; per-operator overrides land alongside the partnership
    setup.
    """

    timestamp: str = "timestamp"
    sensor_id: str = "sensor_id"
    equipment_id: str = "equipment_id"
    activity_type: str = "activity"
    pm10_ugm3: str = "pm10_ugm3"
    pm25_ugm3: str = "pm25_ugm3"
    speed_kmh: str = "speed_kmh"
    tonnage: str = "tonnage"
    zone_id: str = "zone_id"
    wind_speed_ms: str = "wind_speed_ms"
    wind_direction_deg: str = "wind_direction_deg"
    temperature_c: str = "temperature_c"
    humidity_pct: str = "humidity_pct"


def _get(row: Mapping[str, Any], key: str) -> Any:
    """Dotted-path lookup so adapters can read nested operator JSON."""
    if "." not in key:
        return row.get(key)
    cur: Any = row
    for part in key.split("."):
        if not isinstance(cur, Mapping):
            return None
        cur = cur.get(part)
    return cur


def _parse_ts(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def to_sensor_readings(
    rows: Iterable[Mapping[str, Any]],
    *,
    field_map: FieldMap | None = None,
) -> Iterable[RawSensorReadingSchema]:
    """Map operator-format PM rows to RawSensorReading."""
    if field_map is None:
        field_map = _DEFAULT_FIELD_MAP
    for row in rows:
        ts = _parse_ts(_get(row, field_map.timestamp))
        sensor_id = _get(row, field_map.sensor_id)
        if ts is None or not isinstance(sensor_id, str):
            continue
        raw_value: dict[str, Any] = {"source": SOURCE_NAME}
        pm10 = _get(row, field_map.pm10_ugm3)
        pm25 = _get(row, field_map.pm25_ugm3)
        if isinstance(pm10, int | float) and not isinstance(pm10, bool):
            raw_value["pm10_ugm3"] = float(pm10)
        if isinstance(pm25, int | float) and not isinstance(pm25, bool):
            raw_value["pm25_ugm3"] = float(pm25)
        if "pm10_ugm3" not in raw_value and "pm25_ugm3" not in raw_value:
            continue
        yield RawSensorReadingSchema(
            sensor_id=sensor_id,
            timestamp=ts,
            raw_value=raw_value,
            source_quality_hint=1.0,
        )


def to_weather_readings(
    rows: Iterable[Mapping[str, Any]],
    *,
    field_map: FieldMap | None = None,
) -> Iterable[RawWeatherReadingSchema]:
    if field_map is None:
        field_map = _DEFAULT_FIELD_MAP
    for row in rows:
        ts = _parse_ts(_get(row, field_map.timestamp))
        if ts is None:
            continue
        kwargs: dict[str, Any] = {
            "source": SOURCE_NAME,
            "timestamp": ts,
            "zone_id": _get(row, field_map.zone_id),
        }
        for src_key, dst_key in (
            (field_map.wind_speed_ms, "wind_speed_ms"),
            (field_map.wind_direction_deg, "wind_direction_deg"),
            (field_map.temperature_c, "temperature_c"),
            (field_map.humidity_pct, "humidity_pct"),
        ):
            v = _get(row, src_key)
            if isinstance(v, int | float) and not isinstance(v, bool):
                kwargs[dst_key] = float(v)
        yield RawWeatherReadingSchema(**kwargs)


def to_equipment_activity(
    rows: Iterable[Mapping[str, Any]],
    *,
    field_map: FieldMap | None = None,
) -> Iterable[RawEquipmentActivitySchema]:
    if field_map is None:
        field_map = _DEFAULT_FIELD_MAP
    for row in rows:
        ts = _parse_ts(_get(row, field_map.timestamp))
        equipment_id = _get(row, field_map.equipment_id)
        activity = _get(row, field_map.activity_type)
        if ts is None or not isinstance(equipment_id, str) or not isinstance(activity, str):
            continue
        kwargs: dict[str, Any] = {
            "equipment_id": equipment_id,
            "timestamp": ts,
            "activity_type": activity,
            "zone_id": _get(row, field_map.zone_id),
        }
        speed = _get(row, field_map.speed_kmh)
        if isinstance(speed, int | float) and not isinstance(speed, bool):
            kwargs["speed_kmh"] = float(speed)
        tonnage = _get(row, field_map.tonnage)
        if isinstance(tonnage, int | float) and not isinstance(tonnage, bool):
            kwargs["tonnage"] = float(tonnage)
        yield RawEquipmentActivitySchema(**kwargs)


_DEFAULT_FIELD_MAP = FieldMap()


__all__ = [
    "SOURCE_NAME",
    "FieldMap",
    "to_equipment_activity",
    "to_sensor_readings",
    "to_weather_readings",
]
