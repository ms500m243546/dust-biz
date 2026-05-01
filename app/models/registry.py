"""Model registry.

The Domain layer obtains model instances by `model_kind` from this
registry. Implementations register themselves at import time. A
"current" pointer per kind selects which version is live.

Lifecycle (per docs/model-contracts.md):
  - register(model)            - add a version to the catalogue
  - set_current(kind, version) - promote a version to live
  - get_current(kind)          - read the live instance
  - reset()                    - test isolation hook

Phase E ships only the heuristic forecasting baseline. Source
attribution (F), intervention impact (G), production cost (G), and
optimization (H) plug into the same registry as they land.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

ModelKind = str


@runtime_checkable
class _Registrable(Protocol):
    model_version: str
    model_kind: str


class ModelNotFoundError(LookupError):
    """Raised when no current model is registered for a given kind."""


_models: dict[tuple[ModelKind, str], _Registrable] = {}
_current: dict[ModelKind, str] = {}


def register(model: _Registrable, *, set_as_current: bool = True) -> None:
    """Register a model instance under (model_kind, model_version)."""
    key = (model.model_kind, model.model_version)
    _models[key] = model
    if set_as_current or model.model_kind not in _current:
        _current[model.model_kind] = model.model_version


def set_current(kind: ModelKind, version: str) -> None:
    if (kind, version) not in _models:
        raise ModelNotFoundError(f"no registered model for {kind}/{version}")
    _current[kind] = version


def get_current(kind: ModelKind) -> _Registrable:
    version = _current.get(kind)
    if version is None:
        raise ModelNotFoundError(f"no current model registered for kind={kind!r}")
    return _models[(kind, version)]


def list_versions(kind: ModelKind) -> list[str]:
    return sorted(v for (k, v) in _models if k == kind)


def reset() -> None:
    """Drop all registrations. Test-only."""
    _models.clear()
    _current.clear()
