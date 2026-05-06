"""Equirectangular projection at a fixed centroid.

Matches the projection used by `scripts/cfd/dem_to_stl.py` so that
zone polygons / receptor coordinates rendered into OpenFOAM
dictionaries land in the same Cartesian frame as the terrain STL.

The projection is intentionally simple (flat-Earth at the centroid)
because the OpenFOAM domain is ~10-20 km on a side; the eccentricity
introduced by a sphere over that scale is < 1 m. UTM would buy us
nothing and add a non-trivial dependency.

Centroid choice for Los Pelambres: the `mine_centroid` declared in
`data_seed/los_pelambres.yaml` — (-70.5208, -31.7300). Aligned with
the bbox centroid the BB.2 STL build used.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_M = 6_378_137.0


@dataclass(frozen=True)
class CentroidProjection:
    """Local-Cartesian frame: east = +x, north = +y, up = +z."""

    centroid_lon: float
    centroid_lat: float

    def __post_init__(self) -> None:
        if not (-180.0 <= self.centroid_lon <= 180.0):
            raise ValueError(f"centroid_lon out of range: {self.centroid_lon}")
        if not (-90.0 <= self.centroid_lat <= 90.0):
            raise ValueError(f"centroid_lat out of range: {self.centroid_lat}")

    def project(
        self,
        lon: float,
        lat: float,
        elevation_m: float = 0.0,
    ) -> tuple[float, float, float]:
        """(lon, lat, elev) -> (x_east_m, y_north_m, z_up_m)."""
        deg_to_rad = math.pi / 180.0
        m_per_deg_lat = EARTH_RADIUS_M * deg_to_rad
        m_per_deg_lon = m_per_deg_lat * math.cos(self.centroid_lat * deg_to_rad)
        x = (lon - self.centroid_lon) * m_per_deg_lon
        y = (lat - self.centroid_lat) * m_per_deg_lat
        return x, y, elevation_m


# Pilot mine centroid; matches data_seed/los_pelambres.yaml.
LOS_PELAMBRES_CENTROID = CentroidProjection(
    centroid_lon=-70.5208,
    centroid_lat=-31.7300,
)


__all__ = ["CentroidProjection", "EARTH_RADIUS_M", "LOS_PELAMBRES_CENTROID"]
