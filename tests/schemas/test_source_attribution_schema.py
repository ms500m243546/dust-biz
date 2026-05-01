"""SourceAttribution schema-level tests.

These mirror what `scripts/checks/validate-safety.js` enforces
structurally on Attribution-kind schemas (G2: confidence) plus the
field-level constraints the scanner can't see (ranges, defaults).
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.attributions import ProbableSource, SourceAttributionSchema


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "attribution_id": "ATTR-20260501-001",
        "dust_event_id": "EVT-20260501-001",
        "issued_at": datetime(2026, 5, 1, 12, 5, tzinfo=UTC),
        "affected_station": "cs1",
        "probable_sources": [
            {"source": "haul_c", "confidence": 0.62, "reason": "wind alignment + truck activity"},
            {"source": "external_background", "confidence": 0.18, "reason": "regional baseline"},
        ],
        "evidence_fields": {"wind_angle_deg": 270.0, "trucks_active": 6},
        "confidence": 0.71,
        "model_version": "source_attribution_rules_v0.1.0",
    }
    base.update(overrides)
    return base


def test_round_trip_includes_guardrail_fields() -> None:
    s = SourceAttributionSchema(**_payload())  # type: ignore[arg-type]
    assert hasattr(s, "confidence")  # G2
    assert hasattr(s, "model_version")
    assert s.confidence == 0.71
    assert len(s.probable_sources) == 2
    assert s.probable_sources[0].source == "haul_c"
    assert s.probable_sources[0].reason  # G3 spirit at per-source level
    assert s.evidence_fields["trucks_active"] == 6


def test_overall_confidence_must_be_in_unit_interval() -> None:
    with pytest.raises(ValidationError):
        SourceAttributionSchema(**_payload(confidence=1.4))  # type: ignore[arg-type]


def test_probable_source_confidence_bounded() -> None:
    with pytest.raises(ValidationError):
        ProbableSource(source="x", confidence=-0.1, reason="r")


def test_probable_sources_default_to_empty_list() -> None:
    s = SourceAttributionSchema(**_payload(probable_sources=[]))  # type: ignore[arg-type]
    assert s.probable_sources == []
