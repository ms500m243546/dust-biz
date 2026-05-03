"""Phase U.2 — cycle-time cost promotion tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.domain.cost_promotion import (
    SANITY_TONNES_LOWER,
    SANITY_TONNES_UPPER,
    _sanity_band_pass,
    maybe_promote_cycle_time_cost,
)
from app.models import registry
from app.models.cost.cycle_time_v0_1_0 import CYCLE_TIME_VERSION
from app.models.cost.heuristic_baseline import HEURISTIC_VERSION


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    registry.reset()
    yield
    registry.reset()


def test_sanity_band_passes_with_default_inputs() -> None:
    passed, msg = _sanity_band_pass()
    assert passed, msg


def test_promotion_flips_registry_to_cycle_time_when_sanity_passes() -> None:
    promoted = maybe_promote_cycle_time_cost()
    assert promoted is True
    assert registry.get_current("production_cost").model_version == CYCLE_TIME_VERSION


def test_promotion_idempotent_under_repeated_calls() -> None:
    for _ in range(3):
        assert maybe_promote_cycle_time_cost() is True
    assert registry.get_current("production_cost").model_version == CYCLE_TIME_VERSION


def test_sanity_constants_in_reasonable_range() -> None:
    assert 0.0 < SANITY_TONNES_LOWER < SANITY_TONNES_UPPER
    # Upper bound shouldn't be absurdly above the canonical 1000 t/h
    # over an hour (which is the underlying throughput).
    assert SANITY_TONNES_UPPER < 1000.0


def test_heuristic_remains_registered_alongside_cycle_time() -> None:
    maybe_promote_cycle_time_cost()
    versions = registry.list_versions("production_cost")
    assert HEURISTIC_VERSION in versions
    assert CYCLE_TIME_VERSION in versions
