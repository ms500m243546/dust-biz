"""DispersionMatrix schemas (Phase BA.5).

Persisted source-receptor lookup table reduced from a SimScale /
OpenFOAM campaign. One row per (mine_id, model_version). Realtime
path snaps current wind to the nearest regime grid cell and reads
the per-(source_zone, receptor) concentration coefficient.

Coefficients are normalised: 1 unit of dust emission at the source
zone produces `coefficient` concentration at the receptor under that
regime. The intervention-impact path multiplies by the AP-42 source
emission rate to recover absolute µg/m³.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RegimeGridSchema(BaseModel):
    """The discrete grid the matrix was trained on.

    Realtime lookup snaps to the nearest direction bin and linearly
    interpolates between speed bins. Stability classes off the grid
    are handled via Pasquill-Gifford analytic rescaling at inference
    time.
    """

    directions_deg: list[float] = Field(default_factory=list)
    speeds_ms: list[float] = Field(default_factory=list)
    stability_classes: list[str] = Field(default_factory=lambda: ["neutral"])


class DispersionMatrixSchema(BaseModel):
    """One persisted matrix.

    `coefficients` is keyed by `regime_id` (the orchestrator's
    `dirNN_speedMM_<stability>` form). Inside each regime, the
    nested dict is `{source_zone_id: {receptor_id: coefficient}}`.
    """

    model_config = ConfigDict(from_attributes=True)

    matrix_id: str | None = None
    mine_id: str
    model_version: str
    regime_grid: RegimeGridSchema
    coefficients: dict[str, dict[str, dict[str, float]]] = Field(
        default_factory=dict
    )
    source_run_dir: str | None = None
    notes: str | None = None
    created_at: datetime | None = None

    def receptors(self) -> list[str]:
        """Distinct receptor IDs surfaced anywhere in the matrix."""
        out: set[str] = set()
        for sources in self.coefficients.values():
            for recs in sources.values():
                out.update(recs.keys())
        return sorted(out)

    def source_zones(self) -> list[str]:
        """Distinct source-zone IDs surfaced anywhere in the matrix."""
        out: set[str] = set()
        for sources in self.coefficients.values():
            out.update(sources.keys())
        return sorted(out)

    def to_storage_dict(self) -> dict[str, Any]:
        """JSON-friendly form for the `coefficients` storage column."""
        return {
            "regime_grid": self.regime_grid.model_dump(),
            "coefficients": self.coefficients,
            "source_run_dir": self.source_run_dir,
            "notes": self.notes,
        }
