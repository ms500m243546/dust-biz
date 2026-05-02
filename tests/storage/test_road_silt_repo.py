"""HaulRoadSegmentSilt repository tests (Phase L.7)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.storage.models import HaulRoadSegment, HaulRoadSegmentSilt, Mine
from app.storage.repositories.road_silt import HaulRoadSegmentSiltRepository


def _seed(session: Session) -> None:
    session.add(Mine(mine_id="los-pelambres", name="Los Pelambres"))
    session.add(
        HaulRoadSegment(
            segment_id="HRS-LP-01",
            mine_id="los-pelambres",
            from_node="A",
            to_node="B",
            length_m=1200.0,
            surface_type="gravel",
        )
    )
    session.commit()


def test_add_and_latest_returns_most_recent(session: Session) -> None:
    _seed(session)
    repo = HaulRoadSegmentSiltRepository(session)
    repo.add(
        HaulRoadSegmentSilt(
            segment_id="HRS-LP-01",
            sampled_at=datetime(2026, 1, 15),
            silt_content_pct=8.4,
            sampling_method="ASTM C136 sieve",
            sampled_by="env-team",
        )
    )
    repo.add(
        HaulRoadSegmentSilt(
            segment_id="HRS-LP-01",
            sampled_at=datetime(2026, 4, 15),
            silt_content_pct=11.2,
            sampling_method="ASTM C136 sieve",
            sampled_by="env-team",
        )
    )
    session.commit()

    latest = repo.latest_for_segment("HRS-LP-01")
    assert latest is not None
    assert latest.silt_content_pct == 11.2


def test_for_segment_filters_by_since(session: Session) -> None:
    _seed(session)
    repo = HaulRoadSegmentSiltRepository(session)
    repo.add(
        HaulRoadSegmentSilt(
            segment_id="HRS-LP-01",
            sampled_at=datetime(2025, 11, 1),
            silt_content_pct=6.0,
        )
    )
    repo.add(
        HaulRoadSegmentSilt(
            segment_id="HRS-LP-01",
            sampled_at=datetime(2026, 4, 1),
            silt_content_pct=10.0,
        )
    )
    session.commit()
    rows = repo.for_segment(
        "HRS-LP-01", since=datetime(2026, 1, 1) - timedelta(days=1)
    )
    assert len(rows) == 1
    assert rows[0].silt_content_pct == 10.0
