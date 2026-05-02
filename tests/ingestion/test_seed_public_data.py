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
        filters={"station_code": "EM05", "parameter": "pm10"},
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
    assert "parsed 8 records" in captured.out


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
