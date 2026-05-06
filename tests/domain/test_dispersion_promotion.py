"""Phase BA.10 — dispersion-model auto-promotion tests."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.domain.dispersion_matrix import persist_dispersion_matrix
from app.domain.dispersion_promotion import (
    CFD_LOOKUP_VERSION,
    DISPERSION_BASELINE_VERSION,
    ensure_dispersion_baseline_registered,
    maybe_promote_cfd_lookup,
)
from app.models import registry
from app.models.dispersion.cfd_lookup_v0_1_0 import CFDLookupDispersionModel
from app.models.dispersion.distance_decay_baseline import (
    DistanceDecayDispersionModel,
)
from app.schemas.dispersion import DispersionMatrixSchema, RegimeGridSchema
from app.storage.models import Mine


@pytest.fixture(autouse=True)
def _reset_dispersion_registry():
    """Each test starts from a clean dispersion registry."""
    yield
    # Drop only the dispersion entries; other test suites depend on
    # forecasting / cost / etc. being registered as they are.
    for kv in list(registry._models.keys()):
        if kv[0] == "dispersion":
            registry._models.pop(kv, None)
    registry._current.pop("dispersion", None)


def test_ensure_baseline_registered_makes_baseline_current() -> None:
    ensure_dispersion_baseline_registered()
    current = registry.get_current("dispersion")
    assert isinstance(current, DistanceDecayDispersionModel)
    assert current.model_version == DISPERSION_BASELINE_VERSION


def test_ensure_baseline_idempotent() -> None:
    ensure_dispersion_baseline_registered()
    ensure_dispersion_baseline_registered()
    # Still exactly one dispersion entry registered.
    keys = [k for k in registry._models if k[0] == "dispersion"]
    assert len(keys) == 1


def test_promote_held_when_no_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch session_scope to a no-matrix fixture so we don't depend
    # on the dev DB state.
    from contextlib import contextmanager

    @contextmanager
    def fake_scope():
        yield None

    from app.domain import dispersion_promotion as dp_module
    monkeypatch.setattr(dp_module, "session_scope", fake_scope)
    monkeypatch.setattr(
        "app.domain.dispersion_matrix.load_latest_for_mine",
        lambda session, mine_id: None,
    )
    promoted = maybe_promote_cfd_lookup(pilot_mine_id="ba10-no-matrix")
    assert promoted is False
    current = registry.get_current("dispersion")
    assert isinstance(current, DistanceDecayDispersionModel)


def test_promote_flips_current_when_matrix_present(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    schema = DispersionMatrixSchema(
        mine_id="ba10-mine",
        model_version=CFD_LOOKUP_VERSION,
        regime_grid=RegimeGridSchema(
            directions_deg=[0.0, 90.0, 180.0, 270.0], speeds_ms=[5.0]
        ),
        # MIN_REGIMES = 4 in the BD.3 calibration probe; populate all
        # four so the structural sanity check passes.
        coefficients={
            f"dir{i:02d}_speed00_neutral": {"src": {"rec": 0.4}}
            for i in range(4)
        },
    )
    session.add(Mine(mine_id="ba10-mine", name="BA10 mine", default_automation_level="L1"))
    session.flush()
    persist_dispersion_matrix(session, schema)
    session.commit()

    from contextlib import contextmanager

    @contextmanager
    def fake_scope():
        yield session

    from app.domain import dispersion_promotion as dp_module
    monkeypatch.setattr(dp_module, "session_scope", fake_scope)

    promoted = maybe_promote_cfd_lookup(pilot_mine_id="ba10-mine")
    assert promoted is True
    current = registry.get_current("dispersion")
    assert isinstance(current, CFDLookupDispersionModel)
    assert current.model_version == CFD_LOOKUP_VERSION


def test_promote_held_when_matrix_has_empty_coefficients(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    schema = DispersionMatrixSchema(
        mine_id="ba10-empty",
        model_version=CFD_LOOKUP_VERSION,
        regime_grid=RegimeGridSchema(directions_deg=[0.0], speeds_ms=[3.0]),
        coefficients={},
    )
    session.add(Mine(mine_id="ba10-empty", name="BA10 empty", default_automation_level="L1"))
    session.flush()
    persist_dispersion_matrix(session, schema)
    session.commit()

    from contextlib import contextmanager

    @contextmanager
    def fake_scope():
        yield session

    from app.domain import dispersion_promotion as dp_module
    monkeypatch.setattr(dp_module, "session_scope", fake_scope)

    promoted = maybe_promote_cfd_lookup(pilot_mine_id="ba10-empty")
    assert promoted is False
    # Baseline still current.
    current = registry.get_current("dispersion")
    assert isinstance(current, DistanceDecayDispersionModel)


def test_promote_tolerates_storage_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bootstrap path must never raise."""
    from contextlib import contextmanager

    @contextmanager
    def fake_scope():
        raise RuntimeError("DB unreachable")
        yield  # pragma: no cover

    from app.domain import dispersion_promotion as dp_module
    monkeypatch.setattr(dp_module, "session_scope", fake_scope)

    promoted = maybe_promote_cfd_lookup(pilot_mine_id="ba10-storage-fail")
    assert promoted is False
    # Baseline still current (registered before the failing call).
    current = registry.get_current("dispersion")
    assert isinstance(current, DistanceDecayDispersionModel)
