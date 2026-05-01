from collections.abc import Iterator

import pytest

from app.models import registry


class _StubModel:
    def __init__(self, kind: str, version: str) -> None:
        self.model_kind = kind
        self.model_version = version


@pytest.fixture(autouse=True)
def _reset_registry() -> Iterator[None]:
    registry.reset()
    yield
    registry.reset()


def test_register_and_get_current_round_trip() -> None:
    m = _StubModel("dust_forecast", "v1")
    registry.register(m)
    assert registry.get_current("dust_forecast") is m
    assert registry.list_versions("dust_forecast") == ["v1"]


def test_register_second_model_does_not_clobber_current_when_disabled() -> None:
    a = _StubModel("dust_forecast", "v1")
    b = _StubModel("dust_forecast", "v2")
    registry.register(a)
    registry.register(b, set_as_current=False)
    assert registry.get_current("dust_forecast") is a
    assert registry.list_versions("dust_forecast") == ["v1", "v2"]


def test_set_current_promotes_a_registered_version() -> None:
    a = _StubModel("dust_forecast", "v1")
    b = _StubModel("dust_forecast", "v2")
    registry.register(a)
    registry.register(b, set_as_current=False)
    registry.set_current("dust_forecast", "v2")
    assert registry.get_current("dust_forecast") is b


def test_set_current_unknown_version_raises() -> None:
    with pytest.raises(registry.ModelNotFoundError):
        registry.set_current("dust_forecast", "ghost")


def test_get_current_missing_kind_raises() -> None:
    with pytest.raises(registry.ModelNotFoundError):
        registry.get_current("intervention_impact")


def test_kinds_are_isolated() -> None:
    forecaster = _StubModel("dust_forecast", "v1")
    attributor = _StubModel("source_attribution", "v1")
    registry.register(forecaster)
    registry.register(attributor)
    assert registry.get_current("dust_forecast") is forecaster
    assert registry.get_current("source_attribution") is attributor
