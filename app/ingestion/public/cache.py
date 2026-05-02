"""Disk cache for public-source fetches (Phase L.1).

Caches raw API responses keyed by `(source, window, filter-hash)` so
re-runs don't hammer rate-limited public APIs. Cache directory is
`data_cache/<source>/` by default; configurable via
`Settings.data_cache_dir` for tests.

Cache files are JSON only — no parquet / pickle here. The connectors
parse the JSON into typed records each time they're read; the cache
is for raw-bytes economy, not for skipping deserialisation.

Layer rule: ingestion connectors import this; nothing else does.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _filter_hash(filters: dict[str, Any]) -> str:
    payload = json.dumps(filters, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def cache_key(
    *,
    source: str,
    window_from: datetime,
    window_to: datetime,
    filters: dict[str, Any] | None = None,
) -> str:
    """Stable filename for the (source, window, filters) tuple."""
    fhash = _filter_hash(filters or {})
    return (
        f"{source}/"
        f"{window_from.strftime('%Y%m%dT%H%M')}_"
        f"{window_to.strftime('%Y%m%dT%H%M')}_"
        f"{fhash}.json"
    )


def get(
    *,
    source: str,
    window_from: datetime,
    window_to: datetime,
    filters: dict[str, Any] | None = None,
    cache_dir: Path,
) -> Any | None:
    path = cache_dir / cache_key(
        source=source,
        window_from=window_from,
        window_to=window_to,
        filters=filters,
    )
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def put(
    *,
    payload: Any,
    source: str,
    window_from: datetime,
    window_to: datetime,
    filters: dict[str, Any] | None = None,
    cache_dir: Path,
) -> Path:
    path = cache_dir / cache_key(
        source=source,
        window_from=window_from,
        window_to=window_to,
        filters=filters,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, default=str), encoding="utf-8")
    return path


__all__ = ["cache_key", "get", "put"]
