"""Disk cache tests (Phase L.1)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.ingestion.public.cache import cache_key, get, put


def test_cache_key_is_deterministic() -> None:
    k1 = cache_key(
        source="sinca",
        window_from=datetime(2026, 5, 1, 0, 0),
        window_to=datetime(2026, 5, 2, 0, 0),
        filters={"station": "EM05"},
    )
    k2 = cache_key(
        source="sinca",
        window_from=datetime(2026, 5, 1, 0, 0),
        window_to=datetime(2026, 5, 2, 0, 0),
        filters={"station": "EM05"},
    )
    assert k1 == k2


def test_cache_key_changes_when_filters_change() -> None:
    k1 = cache_key(
        source="sinca",
        window_from=datetime(2026, 5, 1, 0, 0),
        window_to=datetime(2026, 5, 2, 0, 0),
        filters={"station": "EM05"},
    )
    k2 = cache_key(
        source="sinca",
        window_from=datetime(2026, 5, 1, 0, 0),
        window_to=datetime(2026, 5, 2, 0, 0),
        filters={"station": "EM06"},
    )
    assert k1 != k2


def test_put_then_get_round_trip(tmp_path: Path) -> None:
    payload = {"records": [{"pm10": 120.0}, {"pm10": 95.0}]}
    put(
        payload=payload,
        source="sinca",
        window_from=datetime(2026, 5, 1, 0, 0),
        window_to=datetime(2026, 5, 2, 0, 0),
        cache_dir=tmp_path,
    )
    out = get(
        source="sinca",
        window_from=datetime(2026, 5, 1, 0, 0),
        window_to=datetime(2026, 5, 2, 0, 0),
        cache_dir=tmp_path,
    )
    assert out == payload


def test_cache_miss_returns_none(tmp_path: Path) -> None:
    out = get(
        source="sinca",
        window_from=datetime(2026, 5, 1, 0, 0),
        window_to=datetime(2026, 5, 2, 0, 0),
        cache_dir=tmp_path,
    )
    assert out is None
