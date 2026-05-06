"""Phase BA.8 / BD.1 — dispersion-resolved cause-class tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.domain.dispersion_attribution import (
    latest_wind_state,
    resolve_cause_class_via_dispersion,
)
from app.models import registry
from app.models.dispersion.cfd_lookup_v0_1_0 import (
    CFD_LOOKUP_VERSION,
    CFDLookupDispersionModel,
)
from app.models.dispersion.distance_decay_baseline import (
    DistanceDecayDispersionModel,
)
from app.schemas.dispersion import DispersionMatrixSchema, RegimeGridSchema
from app.storage.models import Mine, WeatherReading, Zone


@pytest.fixture(autouse=True)
def _isolate_dispersion_registry():
    yield
    for kv in list(registry._models.keys()):
        if kv[0] == "dispersion":
            registry._models.pop(kv, None)
    registry._current.pop("dispersion", None)


def _seed_mine_with_zones(session: Session) -> None:
    session.add(Mine(mine_id="bd1-mine", name="BD1", default_automation_level="L1"))
    session.flush()
    session.add(
        Zone(
            zone_id="haul_W",
            mine_id="bd1-mine",
            zone_type="haul_road",
            operational_importance="primary",
            dust_generation_baseline="high",
        )
    )
    session.add(
        Zone(
            zone_id="crush_C",
            mine_id="bd1-mine",
            zone_type="crusher",
            operational_importance="primary",
            dust_generation_baseline="medium",
        )
    )
    session.flush()


def _matrix(*, haul_share: float, crusher_share: float) -> DispersionMatrixSchema:
    """4-direction x 1-speed grid; controlled per-source contributions."""
    return DispersionMatrixSchema(
        mine_id="bd1-mine",
        model_version=CFD_LOOKUP_VERSION,
        regime_grid=RegimeGridSchema(
            directions_deg=[0.0, 90.0, 180.0, 270.0],
            speeds_ms=[5.0],
            stability_classes=["neutral"],
        ),
        coefficients={
            "dir00_speed00_neutral": {
                "haul_W":  {"sensor-X": haul_share},
                "crush_C": {"sensor-X": crusher_share},
            },
        },
    )


def test_returns_none_when_no_dispersion_model_registered(session: Session) -> None:
    _seed_mine_with_zones(session)
    out = resolve_cause_class_via_dispersion(
        session, mine_id="bd1-mine", receptor_id="sensor-X",
        as_of=datetime(2026, 5, 6, 12, tzinfo=UTC),
    )
    assert out is None


def test_returns_none_when_no_wind_state(session: Session) -> None:
    _seed_mine_with_zones(session)
    registry.register(
        CFDLookupDispersionModel(_matrix(haul_share=0.6, crusher_share=0.2))
    )
    out = resolve_cause_class_via_dispersion(
        session, mine_id="bd1-mine", receptor_id="sensor-X",
        as_of=datetime(2026, 5, 6, 12, tzinfo=UTC),
    )
    assert out is None  # no WeatherReading rows in the lookback window


def test_picks_top_contributing_zone_type(session: Session) -> None:
    _seed_mine_with_zones(session)
    registry.register(
        CFDLookupDispersionModel(_matrix(haul_share=0.6, crusher_share=0.2))
    )
    now = datetime(2026, 5, 6, 12, 0, 0)
    session.add(
        WeatherReading(
            timestamp=now - timedelta(minutes=10),
            wind_direction_deg=0.0,
            wind_speed_ms=5.0,
            weather_target_id="x",
            source="test",
            realtime_proxy=True,
        )
    )
    session.flush()
    out = resolve_cause_class_via_dispersion(
        session, mine_id="bd1-mine", receptor_id="sensor-X", as_of=now,
    )
    assert out == "haul_road"  # haul_W dominates over crush_C under wind=0


def test_swap_ranks_when_other_zone_dominates(session: Session) -> None:
    _seed_mine_with_zones(session)
    registry.register(
        CFDLookupDispersionModel(_matrix(haul_share=0.1, crusher_share=0.7))
    )
    now = datetime(2026, 5, 6, 12, 0, 0)
    session.add(
        WeatherReading(
            timestamp=now - timedelta(minutes=10),
            wind_direction_deg=0.0,
            wind_speed_ms=5.0,
            weather_target_id="x",
            source="test",
            realtime_proxy=True,
        )
    )
    session.flush()
    out = resolve_cause_class_via_dispersion(
        session, mine_id="bd1-mine", receptor_id="sensor-X", as_of=now,
    )
    assert out == "crusher"


def test_baseline_distance_decay_still_resolves_when_promoted(session: Session) -> None:
    _seed_mine_with_zones(session)
    # Register the heuristic baseline; it doesn't accept the same
    # signature, so dispersion attribution should fall through to None
    # rather than crash. Documents the graceful-degradation contract.
    registry.register(DistanceDecayDispersionModel())
    now = datetime(2026, 5, 6, 12, 0, 0)
    session.add(
        WeatherReading(
            timestamp=now - timedelta(minutes=10),
            wind_direction_deg=0.0,
            wind_speed_ms=5.0,
            weather_target_id="x",
            source="test",
            realtime_proxy=True,
        )
    )
    session.flush()
    out = resolve_cause_class_via_dispersion(
        session, mine_id="bd1-mine", receptor_id="sensor-X", as_of=now,
    )
    # Baseline's predict signature differs (takes distance + bearing,
    # not source_zone_id). The safe-predict wrapper catches the
    # TypeError and treats every source as 0, so no winner is found.
    assert out is None


def test_returns_none_when_no_zones(session: Session) -> None:
    session.add(Mine(mine_id="empty-mine", name="empty", default_automation_level="L1"))
    session.flush()
    registry.register(
        CFDLookupDispersionModel(_matrix(haul_share=0.5, crusher_share=0.5))
    )
    now = datetime(2026, 5, 6, 12, 0, 0)
    session.add(
        WeatherReading(
            timestamp=now - timedelta(minutes=10),
            wind_direction_deg=0.0,
            wind_speed_ms=5.0,
            weather_target_id="x",
            source="test",
            realtime_proxy=True,
        )
    )
    session.flush()
    out = resolve_cause_class_via_dispersion(
        session, mine_id="empty-mine", receptor_id="sensor-X", as_of=now,
    )
    assert out is None


def test_latest_wind_state_respects_lookback(session: Session) -> None:
    now = datetime(2026, 5, 6, 12, 0, 0)
    # Outside lookback (2 hours ago).
    session.add(
        WeatherReading(
            timestamp=now - timedelta(hours=2),
            wind_direction_deg=180.0,
            wind_speed_ms=8.0,
            weather_target_id="x",
            source="test",
            realtime_proxy=True,
        )
    )
    session.flush()
    out = latest_wind_state(session, as_of=now, lookback_min=60)
    assert out is None
    # Inside lookback.
    session.add(
        WeatherReading(
            timestamp=now - timedelta(minutes=15),
            wind_direction_deg=180.0,
            wind_speed_ms=8.0,
            weather_target_id="x",
            source="test",
            realtime_proxy=True,
        )
    )
    session.flush()
    out = latest_wind_state(session, as_of=now, lookback_min=60)
    assert out == (180.0, 8.0)


def test_latest_wind_state_skips_after_as_of(session: Session) -> None:
    """Anti-hindsight: weather rows newer than as_of must be ignored."""
    now = datetime(2026, 5, 6, 12, 0, 0)
    # FUTURE row — would leak into the model if not filtered.
    session.add(
        WeatherReading(
            timestamp=now + timedelta(minutes=5),
            wind_direction_deg=270.0,
            wind_speed_ms=10.0,
            weather_target_id="x",
            source="test",
            realtime_proxy=True,
        )
    )
    # Older valid row.
    session.add(
        WeatherReading(
            timestamp=now - timedelta(minutes=10),
            wind_direction_deg=0.0,
            wind_speed_ms=5.0,
            weather_target_id="x",
            source="test",
            realtime_proxy=True,
        )
    )
    session.flush()
    out = latest_wind_state(session, as_of=now)
    # Must use the past row, not the future one.
    assert out == (0.0, 5.0)
