"""StationThresholdOverride repository tests (Phase L.6)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.storage.models import Mine, Sensor, StationThresholdOverride
from app.storage.repositories.station_thresholds import (
    StationThresholdOverrideRepository,
)


def _seed_sensor(session: Session) -> None:
    session.add(Mine(mine_id="los-pelambres", name="Los Pelambres"))
    session.add(
        Sensor(
            sensor_id="EM05-CUNCUMEN",
            mine_id="los-pelambres",
            sensor_type="pm10",
        )
    )
    session.commit()


def test_add_and_get_for_sensor(session: Session) -> None:
    _seed_sensor(session)
    repo = StationThresholdOverrideRepository(session)
    repo.add(
        StationThresholdOverride(
            sensor_id="EM05-CUNCUMEN",
            site_id=None,
            pm10_breach_ugm3=120.0,
            pm10_warning_ugm3=80.0,
            rca_reference="RCA 38/1997",
            source_url="https://sea.gob.cl/example",
        )
    )
    session.commit()
    fetched = repo.get_for_sensor("EM05-CUNCUMEN")
    assert fetched is not None
    assert fetched.pm10_breach_ugm3 == 120.0


def test_upsert_overwrites_existing(session: Session) -> None:
    _seed_sensor(session)
    repo = StationThresholdOverrideRepository(session)
    repo.add(
        StationThresholdOverride(
            sensor_id="EM05-CUNCUMEN",
            pm10_breach_ugm3=120.0,
        )
    )
    session.commit()
    repo.upsert_for_sensor(
        StationThresholdOverride(
            sensor_id="EM05-CUNCUMEN",
            pm10_breach_ugm3=100.0,  # tightened
            rca_reference="RCA 050/2004 amendment",
        )
    )
    session.commit()
    fetched = repo.get_for_sensor("EM05-CUNCUMEN")
    assert fetched is not None
    assert fetched.pm10_breach_ugm3 == 100.0
    assert fetched.rca_reference == "RCA 050/2004 amendment"
