"""ERA5 stub orchestrator tests (Phase L.M.1).

L.M.1 only ships the payload-mode ERA5 path: the orchestrator reads
a pre-extracted JSON file, runs it through the existing parser, and
persists. Full CDS-API live mode is L.M.2.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine

from app.ingestion.public.era5 import SOURCE_NAME as ERA5_SOURCE
from app.storage.models import Base, WeatherReading
from scripts.seed_public_data import cmd_era5_from_payload

_PAYLOAD = {
    "time": [
        "2025-05-01T00:00",
        "2025-05-01T01:00",
        "2025-05-01T02:00",
    ],
    "u10": [3.4, 4.1, 5.0],
    "v10": [-1.2, -0.8, 0.3],
    "t2m": [10.5, 9.8, 8.2],
    "sp": [851.0, 851.5, 852.0],
    "tp": [0.0, 0.0, 0.1],
    "ssrd": [0, 0, 50],
    "rh2m": [40, 38, 35],
}


def test_era5_payload_mode_persists_rows(
    tmp_path: Path, in_memory_db: Engine
) -> None:
    payload_path = tmp_path / "era5_test.json"
    payload_path.write_text(json.dumps(_PAYLOAD), encoding="utf-8")
    args = argparse.Namespace(
        era5_payload=str(payload_path),
        zone_id=None,
        no_persist=False,
        weather_target_id="lp-cuncumen-met-era5",
    )
    rc = cmd_era5_from_payload(args)
    assert rc == 0

    from app.storage.database import session_scope

    with session_scope() as s:
        rows = list(s.execute(select(WeatherReading)).scalars())
        count = len(rows)
        sources = [r.source for r in rows]
        first_wind_speed = rows[0].wind_speed_ms
        first_wind_dir = rows[0].wind_direction_deg
    assert count == 3
    assert all(src == ERA5_SOURCE for src in sources)
    # Wind speed/direction derived from u/v in the parser.
    assert first_wind_speed is not None
    assert first_wind_dir is not None


def test_era5_missing_payload_returns_2(tmp_path: Path) -> None:
    args = argparse.Namespace(
        era5_payload=None,
        zone_id=None,
        no_persist=True,
        weather_target_id=None,
    )
    assert cmd_era5_from_payload(args) == 2

    args = argparse.Namespace(
        era5_payload=str(tmp_path / "does_not_exist.json"),
        zone_id=None,
        no_persist=True,
        weather_target_id=None,
    )
    assert cmd_era5_from_payload(args) == 2


def test_era5_no_persist_returns_zero_without_writing(
    tmp_path: Path, in_memory_db: Engine
) -> None:
    payload_path = tmp_path / "era5_test.json"
    payload_path.write_text(json.dumps(_PAYLOAD), encoding="utf-8")
    args = argparse.Namespace(
        era5_payload=str(payload_path),
        zone_id=None,
        no_persist=True,
        weather_target_id=None,
    )
    rc = cmd_era5_from_payload(args)
    assert rc == 0

    from app.storage.database import session_scope

    with session_scope() as s:
        count = s.execute(select(WeatherReading)).all()
    assert count == []


@pytest.fixture
def in_memory_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    eng = create_engine("sqlite://", future=True)
    Base.metadata.create_all(eng)
    factory = sessionmaker(
        bind=eng, autoflush=False, autocommit=False, future=True
    )

    import app.storage.database as db_mod

    monkeypatch.setattr(db_mod, "_engine", eng)
    monkeypatch.setattr(db_mod, "_SessionLocal", factory)
    yield eng
