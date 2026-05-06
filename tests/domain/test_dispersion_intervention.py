"""Phase BA.9 / BD.2 — dispersion uplift tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.domain.dispersion_intervention import (
    MAX_UPLIFT,
    MIN_UPLIFT,
    REFERENCE_COUPLING,
    apply_dispersion_uplift,
    compute_dispersion_uplift,
)
from app.models import registry
from app.models.dispersion.cfd_lookup_v0_1_0 import (
    CFD_LOOKUP_VERSION,
    CFDLookupDispersionModel,
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


def _seed_one_zone(session: Session) -> None:
    session.add(Mine(mine_id="bd2-mine", name="BD2", default_automation_level="L1"))
    session.flush()
    session.add(Zone(
        zone_id="src-1", mine_id="bd2-mine",
        zone_type="haul_road",
        operational_importance="primary", dust_generation_baseline="high",
    ))
    session.flush()


def _matrix(*, share: float) -> DispersionMatrixSchema:
    return DispersionMatrixSchema(
        mine_id="bd2-mine",
        model_version=CFD_LOOKUP_VERSION,
        regime_grid=RegimeGridSchema(
            directions_deg=[0.0],
            speeds_ms=[5.0],
            stability_classes=["neutral"],
        ),
        coefficients={
            "dir00_speed00_neutral": {"src-1": {"rec-A": share}},
        },
    )


def _add_wind(session: Session, ts: datetime) -> None:
    session.add(WeatherReading(
        timestamp=ts, wind_direction_deg=0.0, wind_speed_ms=5.0,
        weather_target_id="x", source="test", realtime_proxy=True,
    ))
    session.flush()


def test_apply_uplift_passthrough_when_uplift_is_none() -> None:
    red, after = apply_dispersion_uplift(
        predicted_pm10_reduction=10.0,
        breach_probability_before=0.7,
        breach_probability_after=0.4,
        uplift=None,
    )
    assert red == 10.0
    assert after == 0.4


def test_apply_uplift_scales_reduction_and_breach_delta() -> None:
    red, after = apply_dispersion_uplift(
        predicted_pm10_reduction=10.0,
        breach_probability_before=0.7,
        breach_probability_after=0.5,
        uplift=1.5,
    )
    # Reduction: 10 * 1.5 = 15.
    assert red == 15.0
    # delta = 0.7 - 0.5 = 0.2; scaled to 0.3 -> after = 0.4.
    assert after == pytest.approx(0.4, abs=1e-9)


def test_apply_uplift_clamps_breach_to_zero() -> None:
    red, after = apply_dispersion_uplift(
        predicted_pm10_reduction=10.0,
        breach_probability_before=0.5,
        breach_probability_after=0.4,
        uplift=10.0,  # absurd uplift
    )
    # delta scaled to 1.0; after would be 0.5 - 1.0 = -0.5 -> clamped 0.
    assert after == 0.0


def test_compute_uplift_none_when_no_dispersion_model(session: Session) -> None:
    _seed_one_zone(session)
    out = compute_dispersion_uplift(
        session, mine_id="bd2-mine", receptor_id="rec-A",
        as_of=datetime(2026, 5, 6, 12, tzinfo=UTC),
    )
    assert out is None


def test_compute_uplift_scaled_against_reference_coupling(session: Session) -> None:
    _seed_one_zone(session)
    registry.register(CFDLookupDispersionModel(_matrix(share=REFERENCE_COUPLING)))
    now = datetime(2026, 5, 6, 12, 0, 0)
    _add_wind(session, now - timedelta(minutes=5))
    out = compute_dispersion_uplift(
        session, mine_id="bd2-mine", receptor_id="rec-A", as_of=now,
    )
    # Share == REFERENCE_COUPLING -> uplift = 1.0.
    assert out == pytest.approx(1.0, abs=1e-9)


def test_compute_uplift_clamps_high(session: Session) -> None:
    _seed_one_zone(session)
    # Share 10x the reference -> raw uplift 10, clamped to MAX_UPLIFT.
    registry.register(CFDLookupDispersionModel(_matrix(share=REFERENCE_COUPLING * 10.0)))
    now = datetime(2026, 5, 6, 12, 0, 0)
    _add_wind(session, now - timedelta(minutes=5))
    out = compute_dispersion_uplift(
        session, mine_id="bd2-mine", receptor_id="rec-A", as_of=now,
    )
    assert out == MAX_UPLIFT


def test_compute_uplift_clamps_low(session: Session) -> None:
    _seed_one_zone(session)
    registry.register(CFDLookupDispersionModel(_matrix(share=REFERENCE_COUPLING * 0.1)))
    now = datetime(2026, 5, 6, 12, 0, 0)
    _add_wind(session, now - timedelta(minutes=5))
    out = compute_dispersion_uplift(
        session, mine_id="bd2-mine", receptor_id="rec-A", as_of=now,
    )
    assert out == MIN_UPLIFT


def test_compute_uplift_none_when_no_wind(session: Session) -> None:
    _seed_one_zone(session)
    registry.register(CFDLookupDispersionModel(_matrix(share=REFERENCE_COUPLING)))
    out = compute_dispersion_uplift(
        session, mine_id="bd2-mine", receptor_id="rec-A",
        as_of=datetime(2026, 5, 6, 12, tzinfo=UTC),
    )
    assert out is None


def test_compute_uplift_none_when_no_zones(session: Session) -> None:
    session.add(Mine(mine_id="empty-bd2", name="empty", default_automation_level="L1"))
    session.flush()
    registry.register(CFDLookupDispersionModel(_matrix(share=REFERENCE_COUPLING)))
    now = datetime(2026, 5, 6, 12, 0, 0)
    _add_wind(session, now - timedelta(minutes=5))
    out = compute_dispersion_uplift(
        session, mine_id="empty-bd2", receptor_id="rec-A", as_of=now,
    )
    assert out is None
