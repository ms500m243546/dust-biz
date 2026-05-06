"""Phase BC.1 — render OpenFOAM cloud blocks from OSM zones + INE receptors.

Fills the three placeholder markers the orchestrator patches into a
campaign run:

* `__PARTICLE_INJECTION_SITES__` (in constant/cloudProperties) -- one
  `coneInjection` per dust-generating source zone (omnidirectional,
  centroid-anchored, parcel rate tuned for source-receptor matrix
  reduction).

* `__RECEPTOR_SAMPLERS__` (in constant/cloudProperties) -- a single
  `voidFraction` cloudFunction that writes the parcel-volume-fraction
  Eulerian field at every write step. Per-receptor concentrations are
  recovered post-run by averaging over receptor cellZones.

* `__RECEPTOR_CELLZONES__` (in system/topoSetDict) -- one `cellSet` +
  `cellZoneSet` per receptor, defining a 200 m-radius x 30 m-tall
  cylinder around each receptor's projected coordinates.

Inputs (defaults to BB.1 + BB.7 outputs):
  data_cache/osm/los-pelambres.parsed.json
  data_cache/ine/los_pelambres_receptors.json

Outputs:
  data_cache/cfd/los_pelambres_injection_sites.txt
  data_cache/cfd/los_pelambres_receptor_samplers.txt
  data_cache/cfd/los_pelambres_topo_set_cellzones.txt

Haul-road policy: 312 OSM haul-road segments are too many for
individual injection blocks (parcel count blowup + dictionary churn).
Default policy: take the top-N longest segments and inject from each
segment's midpoint as a separate `haul_<id>` source. Default N=12,
override with `--haul-road-top-n`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.cfd.projection import (  # noqa: E402
    LOS_PELAMBRES_CENTROID,
    CentroidProjection,
)

DEFAULT_RECEPTOR_RADIUS_M = 200.0
DEFAULT_RECEPTOR_HEIGHT_M = 30.0
DEFAULT_RECEPTOR_BASE_AGL_M = 2.0
DEFAULT_HAUL_ROAD_TOP_N = 12

# Per-zone injection knobs. parcelsPerSecond * duration must be high
# enough that statistical noise is negligible at the receptor scale,
# but not so high that wall-clock blows up. 50 pps * 2000 simpleFoam
# pseudo-seconds = 100k parcels per zone source. Tuned for the
# ~5M-cell mesh on a 12-core box.
DEFAULT_PARCELS_PER_SECOND = 50.0
DEFAULT_INJECTION_DURATION_S = 2000.0
DEFAULT_PARTICLE_DIAMETER_M = 5.0e-6   # 5 micron PM10
DEFAULT_INJECTION_HEIGHT_AGL_M = 5.0


def _polygon_centroid(coords: list[list[float]]) -> tuple[float, float]:
    """Naive average of the unique vertex coordinates.

    OSM rings repeat the first vertex at the end (GeoJSON RFC 7946);
    drop that before averaging so the centroid isn't biased.
    """
    if not coords:
        raise ValueError("empty polygon")
    if coords[0] == coords[-1] and len(coords) > 1:
        coords = coords[:-1]
    lon = sum(c[0] for c in coords) / len(coords)
    lat = sum(c[1] for c in coords) / len(coords)
    return lon, lat


def _line_midpoint(coords: list[list[float]]) -> tuple[float, float]:
    """Midpoint of a LineString by vertex index."""
    if not coords:
        raise ValueError("empty linestring")
    mid = coords[len(coords) // 2]
    return float(mid[0]), float(mid[1])


def render_injection_sites(
    *,
    zones: list[dict[str, Any]],
    haul_roads: list[dict[str, Any]],
    proj: CentroidProjection,
    haul_road_top_n: int = DEFAULT_HAUL_ROAD_TOP_N,
    parcels_per_second: float = DEFAULT_PARCELS_PER_SECOND,
    duration_s: float = DEFAULT_INJECTION_DURATION_S,
    particle_diameter_m: float = DEFAULT_PARTICLE_DIAMETER_M,
    injection_height_agl_m: float = DEFAULT_INJECTION_HEIGHT_AGL_M,
) -> str:
    """Render the `__PARTICLE_INJECTION_SITES__` content.

    Output is OpenFOAM dictionary syntax slotted *inside* the
    `injectionModels { ... }` braces in cloudProperties. Each entry
    is a `coneInjection` with thetaOuter = 180 (omnidirectional),
    fixed parcel diameter, anchored at the source feature's centroid
    (or mid-point) projected into the local Cartesian frame.
    """
    lines: list[str] = []
    sources: list[tuple[str, float, float]] = []

    for z in zones:
        zid = str(z.get("zone_id"))
        geom = z.get("geometry") or {}
        rings = geom.get("coordinates") or []
        if not rings:
            continue
        outer = rings[0]
        try:
            lon, lat = _polygon_centroid(outer)
        except ValueError:
            continue
        sources.append((zid, lon, lat))

    if haul_roads:
        sortable: list[tuple[float, dict[str, Any]]] = []
        for hr in haul_roads:
            length = float(hr.get("length_m") or 0.0)
            sortable.append((length, hr))
        sortable.sort(key=lambda t: t[0], reverse=True)
        for _, hr in sortable[:haul_road_top_n]:
            seg_id = str(hr.get("segment_id"))
            geom = hr.get("geometry") or {}
            coords = geom.get("coordinates") or []
            if not coords:
                continue
            try:
                lon, lat = _line_midpoint(coords)
            except ValueError:
                continue
            sources.append((seg_id, lon, lat))

    for zid, lon, lat in sources:
        x, y, _ = proj.project(lon=lon, lat=lat, elevation_m=0.0)
        # Sanitise the OpenFOAM dictionary key: alphanumerics + underscore.
        key = "src_" + "".join(ch if ch.isalnum() else "_" for ch in zid)
        block = f"""    {key}
    {{
        type             coneInjection;
        SOI              0;
        duration         {duration_s:.1f};
        parcelBasisType  fixed;
        nParticle        1;
        parcelsPerSecond {parcels_per_second:.1f};
        flowRateProfile  constant 1;
        massTotal        0;
        position         ({x:.2f} {y:.2f} {injection_height_agl_m:.2f});
        direction        (0 0 1);
        Umag             constant 0.5;
        thetaInner       constant 0.0;
        thetaOuter       constant 180.0;
        sizeDistribution
        {{
            type            fixedValue;
            fixedValueDistribution
            {{
                value {particle_diameter_m:.2e};
            }}
        }}
    }}"""
        lines.append(block)

    return "\n".join(lines)


def render_receptor_samplers() -> str:
    """`__RECEPTOR_SAMPLERS__` -- single voidFraction cloudFunction.

    Per-receptor concentrations are recovered post-run by averaging
    voidFraction over the cellZones rendered separately.
    """
    return (
        "    voidFraction1\n"
        "    {\n"
        "        type voidFraction;\n"
        "    }"
    )


def render_topo_set_cellzones(
    *,
    receptors: list[dict[str, Any]],
    proj: CentroidProjection,
    radius_m: float = DEFAULT_RECEPTOR_RADIUS_M,
    base_agl_m: float = DEFAULT_RECEPTOR_BASE_AGL_M,
    height_m: float = DEFAULT_RECEPTOR_HEIGHT_M,
) -> str:
    """`__RECEPTOR_CELLZONES__` -- topoSet actions building one cellZone
    per receptor as a 200 m-radius x 30 m-tall cylinder."""
    lines: list[str] = []
    for r in receptors:
        rid = str(r.get("place_id") or r.get("id") or "unknown")
        lon = r.get("longitude")
        lat = r.get("latitude")
        if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
            continue
        x, y, _ = proj.project(lon=float(lon), lat=float(lat), elevation_m=0.0)
        z_lo = base_agl_m
        z_hi = base_agl_m + height_m
        key = "rcv_" + "".join(ch if ch.isalnum() else "_" for ch in rid)
        # cylinderToCell requires (p1, p2, radius) where p1->p2 is the axis.
        block = f"""    {{
        name    {key}_set;
        type    cellSet;
        action  new;
        source  cylinderToCell;
        sourceInfo
        {{
            p1      ({x:.2f} {y:.2f} {z_lo:.2f});
            p2      ({x:.2f} {y:.2f} {z_hi:.2f});
            radius  {radius_m:.2f};
        }}
    }}
    {{
        name    {key};
        type    cellZoneSet;
        action  new;
        source  setToCellZone;
        sourceInfo
        {{
            set {key}_set;
        }}
    }}"""
        lines.append(block)
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render OpenFOAM cloud blocks.")
    parser.add_argument(
        "--osm-parsed",
        default=str(ROOT / "data_cache" / "osm" / "los-pelambres.parsed.json"),
    )
    parser.add_argument(
        "--receptors",
        default=str(ROOT / "data_cache" / "ine" / "los_pelambres_receptors.json"),
    )
    parser.add_argument(
        "--out-dir",
        default=str(ROOT / "data_cache" / "cfd"),
    )
    parser.add_argument(
        "--mine-id", default="los-pelambres",
    )
    parser.add_argument(
        "--haul-road-top-n", type=int, default=DEFAULT_HAUL_ROAD_TOP_N,
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    osm_path = Path(args.osm_parsed)
    rcv_path = Path(args.receptors)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    osm = json.loads(osm_path.read_text(encoding="utf-8"))
    rcv_doc = json.loads(rcv_path.read_text(encoding="utf-8"))
    receptors = rcv_doc.get("places") if isinstance(rcv_doc, dict) else rcv_doc

    proj = LOS_PELAMBRES_CENTROID  # pilot scope

    inj = render_injection_sites(
        zones=osm.get("zones") or [],
        haul_roads=osm.get("haul_roads") or [],
        proj=proj,
        haul_road_top_n=args.haul_road_top_n,
    )
    samp = render_receptor_samplers()
    cz = render_topo_set_cellzones(receptors=receptors or [], proj=proj)

    inj_path = out_dir / f"{args.mine_id}_injection_sites.txt"
    samp_path = out_dir / f"{args.mine_id}_receptor_samplers.txt"
    cz_path = out_dir / f"{args.mine_id}_topo_set_cellzones.txt"
    inj_path.write_text(inj, encoding="utf-8")
    samp_path.write_text(samp, encoding="utf-8")
    cz_path.write_text(cz, encoding="utf-8")

    n_zones = len(osm.get("zones") or [])
    n_hr = min(args.haul_road_top_n, len(osm.get("haul_roads") or []))
    n_rcv = len(receptors or [])
    print(f"injection: {n_zones} zones + {n_hr} haul-road segments -> {inj_path}")
    print(f"samplers : voidFraction (single field) -> {samp_path}")
    print(f"cellzones: {n_rcv} receptor cylinders -> {cz_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
