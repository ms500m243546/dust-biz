"""seed_rca.py loader tests (Phase L.7).

Verify the YAML loader writes Mine + SiteConfiguration + Sensor +
PopulatedPlace + StationThresholdOverride rows correctly, skipping
TODO_FROM_RCA placeholders in dev mode and refusing to load in
production mode.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

SCRIPTS_ROOT = Path(__file__).resolve().parent.parent.parent / "scripts"
SEED_DIR = Path(__file__).resolve().parent.parent.parent / "data_seed"


def _load_module() -> object:
    spec = importlib.util.spec_from_file_location(
        "_seed_rca_test", SCRIPTS_ROOT / "seed_rca.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dev_yaml_loads_with_todo_placeholders(tmp_path: Path) -> None:
    # Use the real Los Pelambres seed which contains TODO_FROM_RCA in
    # dev mode. The loader should skip the placeholder rows and not
    # error.
    module = _load_module()
    written = module.load_seed(SEED_DIR / "los_pelambres.yaml")  # type: ignore[attr-defined]
    assert written > 0


def test_production_tagged_with_todos_raises(tmp_path: Path) -> None:
    seed = {
        "deployment_tier": "production",
        "mine": {"mine_id": "test-mine", "name": "Test"},
        "mine_centroid": {"longitude": -70.0, "latitude": -31.0},
        "site_config": {
            "site_id": "test-site",
            "mine_id": "test-mine",
            "pm10_thresholds": {"breach": 150.0},
            "pm25_thresholds": {"breach": 50.0},
        },
        "populated_places": [
            {
                "place_id": "p1",
                "name": "Pueblo TODO_FROM_RCA",
                "kind": "town",
                "longitude": -70.1,
                "latitude": -31.1,
            }
        ],
        "sensors": [],
        "station_threshold_overrides": [],
    }
    path = tmp_path / "test.yaml"
    path.write_text(yaml.safe_dump(seed), encoding="utf-8")

    module = _load_module()
    with pytest.raises(ValueError, match="TODO_FROM_RCA"):
        module.load_seed(path)  # type: ignore[attr-defined]


def test_dev_yaml_with_clean_data_persists_all_rows(tmp_path: Path) -> None:
    seed = {
        "deployment_tier": "dev",
        "mine": {"mine_id": "tm", "name": "Test Mine"},
        "mine_centroid": {"longitude": -70.0, "latitude": -31.0},
        "site_config": {
            "site_id": "tm-site",
            "mine_id": "tm",
            "pm10_thresholds": {"breach": 150.0},
            "pm25_thresholds": {"breach": 50.0},
            "optimization_weights": {
                "w_breach": 1.0,
                "w_production": 1.0,
                "w_disruption": 0.5,
                "w_low_confidence": 0.5,
                "w_compliance": 1.0,
            },
            "cost_curves": {"tonne_value_usd": 100.0},
        },
        "populated_places": [
            {
                "place_id": "tm-town",
                "name": "Town",
                "kind": "town",
                "longitude": -70.1,
                "latitude": -31.1,
                "population": 500,
            }
        ],
        "sensors": [
            {
                "sensor_id": "tm-pm10",
                "mine_id": "tm",
                "sensor_type": "pm10",
                "is_compliance_station": True,
            }
        ],
        "station_threshold_overrides": [
            {
                "sensor_id": "tm-pm10",
                "pm10_breach_ugm3": 100.0,
                "rca_reference": "Test RCA",
            }
        ],
    }
    path = tmp_path / "tm.yaml"
    path.write_text(yaml.safe_dump(seed), encoding="utf-8")

    module = _load_module()
    written = module.load_seed(path)  # type: ignore[attr-defined]
    # site + place + override; mine + sensor are upserts whose count
    # depends on whether the prior los_pelambres test already populated
    # them, so the lower bound is 3.
    assert written >= 3
