"""Phase BC.2 — OSM cache -> DB upsert tests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.storage.models import HaulRoadSegment, Mine, Zone
from scripts.seed_public_data import cmd_osm_from_cache


def _stub_args(*, cache_dir: Path, mine_id: str, no_persist: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        cache_dir=str(cache_dir),
        mine_id=mine_id,
        no_persist=no_persist,
    )


def _write_parsed(
    cache_dir: Path,
    mine_id: str,
    *,
    zones: list[dict[str, object]] | None = None,
    haul_roads: list[dict[str, object]] | None = None,
) -> None:
    out = cache_dir / "osm" / f"{mine_id}.parsed.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({
            "mine_id": mine_id,
            "zones": zones or [],
            "haul_roads": haul_roads or [],
        }),
        encoding="utf-8",
    )


def test_osm_upsert_inserts_new_rows(
    tmp_path: Path, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "data_cache"
    _write_parsed(
        cache, "bc2-test-mine",
        zones=[
            {
                "zone_id": "bc2-test-mine-pit-1",
                "mine_id": "bc2-test-mine",
                "zone_type": "pit",
                "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
            },
        ],
        haul_roads=[
            {
                "segment_id": "bc2-test-mine-hrs-1",
                "mine_id": "bc2-test-mine",
                "from_node": "[0,0]",
                "to_node": "[10,10]",
                "length_m": 1500.0,
                "surface_type": "unpaved",
                "geometry": {"type": "LineString", "coordinates": [[0, 0], [10, 10]]},
            },
        ],
    )
    session.add(Mine(mine_id="bc2-test-mine", name="BC2", default_automation_level="L1"))
    session.commit()

    from contextlib import contextmanager

    @contextmanager
    def fake_scope():
        yield session

    import scripts.seed_public_data as sps
    monkeypatch.setattr(sps, "session_scope", fake_scope)

    rc = cmd_osm_from_cache(_stub_args(cache_dir=cache, mine_id="bc2-test-mine"))
    assert rc == 0
    assert session.get(Zone, "bc2-test-mine-pit-1") is not None
    seg = session.get(HaulRoadSegment, "bc2-test-mine-hrs-1")
    assert seg is not None
    assert seg.length_m == 1500.0


def test_osm_upsert_idempotent_on_rerun(
    tmp_path: Path, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "data_cache"
    _write_parsed(
        cache, "bc2-idemp",
        zones=[{
            "zone_id": "bc2-idemp-pit-1", "mine_id": "bc2-idemp",
            "zone_type": "pit",
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [0, 0]]]},
        }],
        haul_roads=[],
    )
    session.add(Mine(mine_id="bc2-idemp", name="BC2 idemp", default_automation_level="L1"))
    session.commit()

    from contextlib import contextmanager

    @contextmanager
    def fake_scope():
        yield session

    import scripts.seed_public_data as sps
    monkeypatch.setattr(sps, "session_scope", fake_scope)

    a = _stub_args(cache_dir=cache, mine_id="bc2-idemp")
    cmd_osm_from_cache(a)
    cmd_osm_from_cache(a)
    # Still exactly one zone row.
    rows = session.query(Zone).filter(Zone.mine_id == "bc2-idemp").count()
    assert rows == 1


def test_osm_no_persist_returns_zero_without_writing(
    tmp_path: Path, session: Session, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cache = tmp_path / "data_cache"
    _write_parsed(
        cache, "bc2-np",
        zones=[{
            "zone_id": "bc2-np-pit-1", "mine_id": "bc2-np",
            "zone_type": "pit",
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0]]]},
        }],
    )
    rc = cmd_osm_from_cache(
        _stub_args(cache_dir=cache, mine_id="bc2-np", no_persist=True)
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "no-persist" in captured.out


def test_osm_missing_cache_returns_error(tmp_path: Path) -> None:
    rc = cmd_osm_from_cache(_stub_args(cache_dir=tmp_path, mine_id="missing"))
    assert rc == 1
