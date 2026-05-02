"""Fleet specifications calibrated to public OEM data sheets (Phase L.5).

Equipment-activity numbers are otherwise impossible to ground-truth
without insider partner data. These specifications come from
publicly-available OEM data sheets (Caterpillar Performance Handbook,
Komatsu spec PDFs) and are used to calibrate the synthetic equipment
stream in `app/ingestion/mock_streams.py` so the generator produces
plausible tonnages, speeds, and cycle times even before real
Los Pelambres data flows.

When real `operator_real` data lands via
`app/ingestion/operator_real.py`, these specs become irrelevant for
the supplied fleet — but they remain the calibration target for
mines without partner data.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FleetSpec:
    """Calibration parameters for one equipment class.

    Phase L.7 additions: `empty_weight_tonnes`, `tire_contact_area_m2`,
    and `engine_tier` are required inputs to the EPA AP-42 unpaved-
    haul-road emission factor and to the diesel-exhaust PM
    decomposition. Without empty weight, total vehicle weight (and
    hence fugitive-dust generation) cannot be computed; without
    engine tier, fugitive vs combustion PM cannot be separated.
    """

    model: str
    payload_tonnes: float
    empty_weight_tonnes: float
    nominal_haul_speed_kmh: tuple[float, float]  # (loaded, empty)
    cycle_time_minutes: tuple[float, float]  # (typical, max)
    fuel_burn_l_per_hr: float
    tire_contact_area_m2: float  # combined contact patch across all tyres
    engine_tier: int  # EPA Tier 1-4 or equivalent EU Stage
    source_url: str  # citation for the spec sheet


# Caterpillar 793F — workhorse haul truck at most large Chilean
# copper mines (Chuquicamata, Los Pelambres rolling fleet, Escondida
# secondary). Payload 240 short tons (~218 t), empty weight ~161 t
# per Cat data sheet, six 40.00R57 tyres ~0.5 m² contact patch each
# (loaded). Tier 2 on most pre-2015 fleets; Tier 4 on rebuilds.
CATERPILLAR_793F = FleetSpec(
    model="cat-793f",
    payload_tonnes=218.0,
    empty_weight_tonnes=161.0,
    nominal_haul_speed_kmh=(20.0, 40.0),
    cycle_time_minutes=(20.0, 35.0),
    fuel_burn_l_per_hr=240.0,
    tire_contact_area_m2=3.0,
    engine_tier=2,
    source_url="https://www.cat.com/en_US/products/new/equipment/off-highway-trucks/mining-trucks.html",
)

# Komatsu 930E-4 — ultra-class truck, used at Escondida + Collahuasi
# + parts of Codelco fleet. Empty ~200 t, six 53/80R63 tyres,
# Tier 2 diesel-electric (Tier 4 available on the 930E-5).
KOMATSU_930E = FleetSpec(
    model="komatsu-930e",
    payload_tonnes=290.0,
    empty_weight_tonnes=200.0,
    nominal_haul_speed_kmh=(18.0, 38.0),
    cycle_time_minutes=(22.0, 38.0),
    fuel_burn_l_per_hr=290.0,
    tire_contact_area_m2=3.6,
    engine_tier=2,
    source_url="https://www.komatsu.com/en/products/trucks/electric-drive-trucks/930e-5/",
)

# Caterpillar 6020B / 6030 hydraulic shovel — pairs with the 793F,
# nominal bucket payload ~37t per pass; 6 passes to fill a 793F.
# Tracked machine (no tyres); `tire_contact_area_m2` is the track
# footprint kept on the same field for schema uniformity.
CATERPILLAR_6030 = FleetSpec(
    model="cat-6030",
    payload_tonnes=37.0,
    empty_weight_tonnes=583.0,
    nominal_haul_speed_kmh=(0.0, 0.0),
    cycle_time_minutes=(0.4, 0.6),
    fuel_burn_l_per_hr=180.0,
    tire_contact_area_m2=18.0,
    engine_tier=2,
    source_url="https://www.cat.com/en_US/products/new/equipment/hyd-mining-shovels.html",
)


FLEET: dict[str, FleetSpec] = {
    "cat-793f": CATERPILLAR_793F,
    "komatsu-930e": KOMATSU_930E,
    "cat-6030": CATERPILLAR_6030,
}


def get_spec(model: str) -> FleetSpec:
    spec = FLEET.get(model)
    if spec is None:
        raise KeyError(f"unknown fleet model: {model!r}")
    return spec


__all__ = [
    "CATERPILLAR_6030",
    "CATERPILLAR_793F",
    "FLEET",
    "FleetSpec",
    "KOMATSU_930E",
    "get_spec",
]
