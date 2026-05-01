from datetime import UTC, datetime

import pytest

from app.models.attribution.rules_baseline import (
    RULES_VERSION,
    CandidateSource,
    RulesBaselineAttributor,
)

NOW = datetime(2026, 5, 1, 12, 5, tzinfo=UTC)


def _candidate(
    source_id: str,
    *,
    wind_offset: float | None = 0.0,
    activity: float = 0.5,
    dust: str = "medium",
    pm_rise: float = 0.5,
) -> CandidateSource:
    return CandidateSource(
        source_id=source_id,
        wind_angle_offset_deg=wind_offset,
        activity_intensity=activity,
        dust_generation_potential=dust,
        concurrent_pm_rise=pm_rise,
    )


def test_attribute_returns_schema_with_safety_fields() -> None:
    model = RulesBaselineAttributor()
    out = model.attribute(
        attribution_id="ATTR-1",
        dust_event_id="EVT-1",
        affected_station="cs1",
        candidates=[_candidate("haul_c", dust="high", activity=0.8, pm_rise=0.7)],
        issued_at=NOW,
    )
    assert out.model_version == RULES_VERSION
    assert 0.0 <= out.confidence <= 1.0
    # external_background floor is always present
    assert any(p.source == "external_background" for p in out.probable_sources)


def test_high_signal_source_ranks_first() -> None:
    model = RulesBaselineAttributor()
    out = model.attribute(
        attribution_id="ATTR-1",
        dust_event_id="EVT-1",
        affected_station="cs1",
        candidates=[
            _candidate("haul_c", dust="high", activity=0.9, pm_rise=0.9),
            _candidate("idle_pit", dust="low", activity=0.0, pm_rise=0.0),
        ],
        issued_at=NOW,
    )
    sources = [p.source for p in out.probable_sources]
    assert sources[0] == "haul_c"
    # Confidence should be substantial when one source dominates.
    assert out.confidence > 0.5


def test_no_candidates_returns_unknown_with_zero_confidence() -> None:
    model = RulesBaselineAttributor()
    out = model.attribute(
        attribution_id="ATTR-1",
        dust_event_id="EVT-1",
        affected_station="cs1",
        candidates=[],
        issued_at=NOW,
    )
    assert out.confidence == 0.0
    assert len(out.probable_sources) == 1
    assert out.probable_sources[0].source == "Unknown"
    assert out.probable_sources[0].confidence == 0.0


def test_no_wind_data_falls_back_to_neutral_proximity() -> None:
    model = RulesBaselineAttributor()
    out = model.attribute(
        attribution_id="ATTR-1",
        dust_event_id="EVT-1",
        affected_station="cs1",
        candidates=[_candidate("haul_c", wind_offset=None, dust="high", activity=0.9)],
        issued_at=NOW,
    )
    assert out.evidence_fields["wind_angle_offsets_deg"] == {"haul_c": None}
    # Still ranks above background floor with strong activity + dust potential
    assert out.probable_sources[0].source == "haul_c"


def test_evidence_fields_record_per_source_inputs() -> None:
    model = RulesBaselineAttributor()
    out = model.attribute(
        attribution_id="ATTR-1",
        dust_event_id="EVT-1",
        affected_station="cs1",
        candidates=[
            _candidate("haul_c", activity=0.8),
            _candidate("crusher_1", activity=0.4),
        ],
        issued_at=NOW,
    )
    intensities = out.evidence_fields["activity_intensities"]
    assert intensities["haul_c"] == 0.8
    assert intensities["crusher_1"] == 0.4
    assert out.evidence_fields["candidate_count"] == 2


def test_dominant_source_pushes_confidence_higher_than_split_sources() -> None:
    model = RulesBaselineAttributor()
    dominated = model.attribute(
        attribution_id="ATTR-1",
        dust_event_id="EVT-1",
        affected_station="cs1",
        candidates=[
            _candidate("haul_c", dust="high", activity=0.9, pm_rise=0.9),
            _candidate("crusher_1", dust="low", activity=0.05, pm_rise=0.05),
        ],
        issued_at=NOW,
    )
    split = model.attribute(
        attribution_id="ATTR-2",
        dust_event_id="EVT-1",
        affected_station="cs1",
        candidates=[
            _candidate("haul_c", dust="medium", activity=0.5, pm_rise=0.5),
            _candidate("crusher_1", dust="medium", activity=0.5, pm_rise=0.5),
        ],
        issued_at=NOW,
    )
    assert dominated.confidence > split.confidence


@pytest.mark.parametrize(
    "wind_offset,expected_higher_when_aligned",
    [(0.0, True), (180.0, False), (45.0, True)],
)
def test_wind_alignment_affects_score(
    wind_offset: float, expected_higher_when_aligned: bool
) -> None:
    model = RulesBaselineAttributor()
    aligned = model.attribute(
        attribution_id="ATTR-1",
        dust_event_id="EVT-1",
        affected_station="cs1",
        candidates=[_candidate("haul_c", wind_offset=0.0, dust="high", activity=0.7)],
        issued_at=NOW,
    )
    test = model.attribute(
        attribution_id="ATTR-2",
        dust_event_id="EVT-1",
        affected_station="cs1",
        candidates=[_candidate("haul_c", wind_offset=wind_offset, dust="high", activity=0.7)],
        issued_at=NOW,
    )
    aligned_score = next(
        p.confidence for p in aligned.probable_sources if p.source == "haul_c"
    )
    test_score = next(
        p.confidence for p in test.probable_sources if p.source == "haul_c"
    )
    if expected_higher_when_aligned:
        assert aligned_score >= test_score
    else:
        assert aligned_score > test_score
