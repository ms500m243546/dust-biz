"""Open-Meteo orchestrator tests (Phase L.M.1).

Covers the new pieces wired in L.M.1:
  - `build_url` shape (units, timezone, hourly variable list)
  - `parse_open_meteo_payload` round-trip on a captured 3-day fixture
  - `_persist_weather` writes the expected `WeatherReading` rows
  - `_run_one_open_meteo` resolves cache hits without calling out

Live HTTP is never hit from CI — the cache module is fed a
captured payload and the orchestrator is exercised in `--no-persist`
and persist modes against an in-memory SQLite.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine

from app.ingestion.public import cache as ingest_cache
from app.ingestion.public.open_meteo import SOURCE_NAME as OPEN_METEO_SOURCE
from app.ingestion.public.open_meteo import build_url
from app.storage.models import Base, WeatherReading
from scripts.seed_public_data import _persist_weather, _run_one_open_meteo

_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "open_meteo_cuncumen_3day.json"
)


def test_build_url_shape() -> None:
    url = build_url(
        latitude=-31.971,
        longitude=-70.701,
        window_from=datetime(2025, 5, 1),
        window_to=datetime(2025, 5, 3),
    )
    assert url.startswith("https://archive-api.open-meteo.com/v1/archive?")
    # Required units pinned; the parser does not convert.
    assert "wind_speed_unit=ms" in url
    assert "temperature_unit=celsius" in url
    assert "timezone=UTC" in url
    # Window dates are passed through as YYYY-MM-DD.
    assert "start_date=2025-05-01" in url
    assert "end_date=2025-05-03" in url
    # Hourly variable list includes wind speed/dir/gusts at minimum.
    assert "wind_speed_10m" in url
    assert "wind_direction_10m" in url
    assert "wind_gusts_10m" in url
    assert "cloud_cover" in url


def _load_fixture() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(
        _FIXTURE_PATH.read_text(encoding="utf-8")
    )
    return payload


def test_persist_weather_writes_rows(in_memory_db: Engine) -> None:
    payload = _load_fixture()
    from app.ingestion.public.open_meteo import parse_open_meteo_payload

    parsed = parse_open_meteo_payload(payload, zone_id=None)
    assert len(parsed) > 0
    written = _persist_weather(
        source=OPEN_METEO_SOURCE,
        parsed=parsed,
        zone_id=None,
        weather_target_id="lp-cuncumen-met",
        realtime_proxy=True,
    )
    assert written == len(parsed)

    # Verify the rows landed with the expected fields populated.
    from app.storage.database import session_scope

    with session_scope() as s:
        rows = list(s.execute(select(WeatherReading)).scalars())
        count = len(rows)
        sources = [r.source for r in rows]
        wind_present = any(r.wind_speed_ms is not None for r in rows)
    assert count == written
    assert all(src == OPEN_METEO_SOURCE for src in sources)
    # The fixture is a real response so wind_speed_ms is always
    # populated for this lat/lon.
    assert wind_present


def test_run_one_open_meteo_uses_cache_hit(
    tmp_path: Path, in_memory_db: Engine
) -> None:
    # Pre-populate the disk cache with the captured payload, then run
    # the orchestrator in dry-run mode (no live HTTP allowed).
    payload = _load_fixture()
    window_from = datetime(2025, 5, 1)
    window_to = datetime(2025, 5, 3)
    ingest_cache.put(
        payload=payload,
        source=OPEN_METEO_SOURCE,
        window_from=window_from,
        window_to=window_to,
        filters={"latitude": -31.971, "longitude": -70.701},
        cache_dir=tmp_path,
    )
    result = _run_one_open_meteo(
        latitude=-31.971,
        longitude=-70.701,
        window_from=window_from,
        window_to=window_to,
        cache_dir=tmp_path,
        dry_run=True,
        no_persist=True,
        zone_id=None,
        weather_target_id="lp-cuncumen-met",
    )
    assert result["status"].startswith("cache")
    assert result["records"] > 0


def test_run_one_open_meteo_dry_run_with_no_cache_returns_zero(
    tmp_path: Path,
) -> None:
    result = _run_one_open_meteo(
        latitude=-31.971,
        longitude=-70.701,
        window_from=datetime(2025, 5, 1),
        window_to=datetime(2025, 5, 3),
        cache_dir=tmp_path,
        dry_run=True,
        no_persist=True,
        zone_id=None,
        weather_target_id="lp-cuncumen-met",
    )
    assert result["status"] == "dry-run-no-cache"
    assert result["written"] == 0


@pytest.fixture
def in_memory_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    """Bind app.storage.database to an in-memory SQLite for this test."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    eng = create_engine("sqlite://", future=True)
    Base.metadata.create_all(eng)
    factory = sessionmaker(
        bind=eng, autoflush=False, autocommit=False, future=True
    )

    import app.storage.database as db_mod

    # The module caches a global engine + session factory; patch both
    # so `session_scope()` resolves to our in-memory engine.
    monkeypatch.setattr(db_mod, "_engine", eng)
    monkeypatch.setattr(db_mod, "_SessionLocal", factory)
    yield eng
