"""Orchestrator tests for scripts/seed_public_data.py (Phase L.7b).

Tests run against the cache-replay path; live HTTP is never invoked.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from app.ingestion.public import cache as ingest_cache
from app.ingestion.public.sinca import SOURCE_NAME as SINCA_SOURCE

SCRIPTS_ROOT = Path(__file__).resolve().parent.parent.parent / "scripts"

FIXTURES = Path(__file__).parent / "fixtures"


def _seed_cache(tmp_path: Path) -> Path:
    csv_body = (FIXTURES / "sinca_cuncumen_pm10.csv").read_text(encoding="utf-8")
    ingest_cache.put(
        payload={"csv": csv_body, "url": "fixture://"},
        source=SINCA_SOURCE,
        window_from=datetime(2026, 4, 30),
        window_to=datetime(2026, 5, 2),
        filters={"station_code": "EM05", "parameter": "pm10", "resolution": "horario"},
        cache_dir=tmp_path,
    )
    return tmp_path


def test_dry_run_exits_zero_when_cache_present(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed_cache(tmp_path)
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_seed_public_data_test", SCRIPTS_ROOT / "seed_public_data.py"
    )
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    rc = module.main(
        [
            "--source",
            "sinca",
            "--station",
            "EM05",
            "--parameter",
            "pm10",
            "--from",
            "2026-04-30",
            "--to",
            "2026-05-02",
            "--cache-dir",
            str(tmp_path),
            "--dry-run",
            "--no-persist",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "cache hit" in captured.out
    assert "parsed 160 records" in captured.out


def test_dry_run_exits_zero_when_cache_missing(tmp_path: Path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_seed_public_data_test_2", SCRIPTS_ROOT / "seed_public_data.py"
    )
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    rc = module.main(
        [
            "--source",
            "sinca",
            "--station",
            "EM05",
            "--parameter",
            "pm10",
            "--from",
            "2026-04-30",
            "--to",
            "2026-05-02",
            "--cache-dir",
            str(tmp_path),
            "--dry-run",
        ]
    )
    assert rc == 0  # dry-run + no cache -> exits 0 with a notice


def test_from_yaml_iterates_sinca_tagged_sensors_and_skips_private(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--from-yaml` reads the RCA seed, fans out per SINCA-tagged sensor,
    skips operator-private rows, and exits 0 when every fetch is cached.
    """
    import importlib.util
    import textwrap

    yaml_path = tmp_path / "lp.yaml"
    yaml_path.write_text(
        textwrap.dedent(
            """\
            sensors:
              - sensor_id: lp-a
                sensor_type: pm10
                sinca_station_code: "424"
                sinca_region_path: RIV
              - sensor_id: lp-b
                sensor_type: pm10
                sinca_station_code: "407"
                sinca_region_path: RIV
              - sensor_id: lp-faena
                sensor_type: pm10
                sinca_station_code: null
            """
        ),
        encoding="utf-8",
    )
    cache_dir = tmp_path / "cache"
    csv_body = (FIXTURES / "sinca_cuncumen_pm10.csv").read_text(encoding="utf-8")
    for code in ("424", "407"):
        ingest_cache.put(
            payload={"csv": csv_body, "url": "fixture://"},
            source=SINCA_SOURCE,
            window_from=datetime(2025, 5, 1),
            window_to=datetime(2026, 5, 1),
            filters={"station_code": code, "parameter": "pm10", "resolution": "horario"},
            cache_dir=cache_dir,
        )

    spec = importlib.util.spec_from_file_location(
        "_seed_public_data_test_yaml", SCRIPTS_ROOT / "seed_public_data.py"
    )
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    rc = module.main(
        [
            "--source", "sinca",
            "--from-yaml", str(yaml_path),
            "--from", "2025-05-01",
            "--to", "2026-05-01",
            "--cache-dir", str(cache_dir),
            "--no-persist",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "3 sensor(s)" in out and "2 eligible for SINCA pull" in out
    assert "skipping operator-private" in out and "lp-faena" in out
    # Both eligible sensors should report parsed records (160 hourly rows
    # in the cached fixture window).
    assert "lp-a" in out and "lp-b" in out
    assert "records=160" in out


def test_orchestrator_creates_cache_key_files_on_put(tmp_path: Path) -> None:
    """Smoke check that the cache module + orchestrator agree on key shape."""
    payload = {"csv": "FECHA;VALOR\n", "url": "fixture://"}
    ingest_cache.put(
        payload=payload,
        source=SINCA_SOURCE,
        window_from=datetime(2026, 4, 30),
        window_to=datetime(2026, 5, 2),
        filters={"station_code": "EM05", "parameter": "pm10"},
        cache_dir=tmp_path,
    )
    files = list((tmp_path / SINCA_SOURCE).glob("*.json"))
    assert len(files) == 1
    parsed = json.loads(files[0].read_text(encoding="utf-8"))
    assert parsed["url"] == "fixture://"
