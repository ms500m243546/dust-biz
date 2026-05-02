"""Public-source ingest connectors (Phase L).

Each connector implements the `Connector` protocol below: pure
fetcher, no DB access. Persistence is the orchestrator's job
(`scripts/seed_mock_data.py` extended in L.2). Connectors are
listed in `docs/data-source-registry.md` and the
`validate-data-sources` check enforces the registry/connector
mapping is in sync.

Connectors live in submodules per source — `sinca.py`,
`open_meteo.py`, `era5.py`, `osm_mine.py`, etc. — landing in their
respective sub-phases.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Connector(Protocol):
    """Pure fetcher contract.

    `source_name` is the discriminator that ends up in
    `raw_value["source"]` on persisted records (e.g. `"sinca"`,
    `"era5"`, `"open_meteo"`, `"operator_real"`).
    """

    source_name: str

    def fetch(
        self,
        *,
        window_from: datetime,
        window_to: datetime,
        **filters: object,
    ) -> Iterable[Mapping[str, object]]: ...


__all__ = ["Connector"]
