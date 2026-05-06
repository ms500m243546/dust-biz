"""Phase BB.1 — OSM mine geometry fetcher.

Queries the Overpass API for landuse=quarry / industrial=mine /
haul-road geometry inside a bounding box, parses via
`app.ingestion.public.osm_mine.parse_overpass_response`, and
saves both the raw Overpass JSON and a parsed summary under
`data_cache/osm/<mine-id>.{raw,parsed}.json`.

Persistence into the `zones` + `haul_road_segments` tables is the
operator's call (a follow-up `--persist` flag would do the upsert);
this script just produces the artifacts.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.ingestion.public.osm_mine import parse_overpass_response  # noqa: E402

OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"

LOS_PELAMBRES_BBOX = (-32.0, -71.0, -31.5, -70.4)  # (s, w, n, e) WGS84


def overpass_query(bbox: tuple[float, float, float, float]) -> str:
    """Build an Overpass QL query for mine pit + haul roads in a bbox."""
    s, w, n, e = bbox
    box = f"({s},{w},{n},{e})"
    return f"""
[out:json][timeout:60];
(
  way["landuse"="quarry"]{box};
  way["industrial"="mine"]{box};
  way["man_made"="mineshaft"]{box};
  way["highway"="service"]["service"="mine"]{box};
  way["highway"="track"]{box};
);
(._;>;);
out body;
""".strip()


def fetch_overpass(query: str, timeout: float = 90.0) -> dict:
    """Hit the Overpass API and return parsed JSON."""
    data = ("data=" + query).encode("utf-8")
    req = urllib.request.Request(
        OVERPASS_ENDPOINT,
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "DustOps-AI/0.1 (+osm geometry import)",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch OSM mine geometry via Overpass.")
    parser.add_argument("--mine-id", default="los-pelambres")
    parser.add_argument(
        "--bbox",
        default=",".join(str(x) for x in LOS_PELAMBRES_BBOX),
        help="south,west,north,east in WGS84 decimal degrees.",
    )
    parser.add_argument(
        "--out-dir", default=str(ROOT / "data_cache" / "osm"),
        help="Output directory for raw + parsed JSON.",
    )
    args = parser.parse_args(argv)

    bbox_parts = [float(x) for x in args.bbox.split(",")]
    if len(bbox_parts) != 4:
        parser.error("--bbox must be south,west,north,east (4 floats)")
    bbox = (bbox_parts[0], bbox_parts[1], bbox_parts[2], bbox_parts[3])

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Querying Overpass for {args.mine_id} bbox={bbox}...")
    query = overpass_query(bbox)
    raw = fetch_overpass(query)
    n_elements = len(raw.get("elements") or [])
    print(f"  raw response: {n_elements} elements")

    raw_path = out_dir / f"{args.mine_id}.raw.json"
    raw_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    print(f"  -> {raw_path}")

    parsed = parse_overpass_response(raw, mine_id=args.mine_id)
    print(f"  parsed: {len(parsed.zones)} zones, {len(parsed.haul_roads)} haul-road segments")
    parsed_summary = {
        "mine_id": args.mine_id,
        "bbox": list(bbox),
        "zones": parsed.zones,
        "haul_roads": parsed.haul_roads,
    }
    parsed_path = out_dir / f"{args.mine_id}.parsed.json"
    parsed_path.write_text(json.dumps(parsed_summary, indent=2), encoding="utf-8")
    print(f"  -> {parsed_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
