from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.features import FeatureRecordSchema


def test_feature_record_minimal_round_trip() -> None:
    schema = FeatureRecordSchema(
        timestamp=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        zone_id="haul_c",
        feature_pipeline_version="feature_pipeline_v0.1.0",
        feature_payload={"pm.pm10_avg_15min": 42.0},
        missing_inputs=[],
    )
    assert schema.zone_id == "haul_c"
    assert schema.feature_payload["pm.pm10_avg_15min"] == 42.0
    assert schema.missing_inputs == []


def test_feature_payload_defaults_to_empty_dict_and_list() -> None:
    schema = FeatureRecordSchema(
        timestamp=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        zone_id="haul_c",
        feature_pipeline_version="feature_pipeline_v0.1.0",
    )
    assert schema.feature_payload == {}
    assert schema.missing_inputs == []


def test_zone_id_required() -> None:
    with pytest.raises(ValidationError):
        FeatureRecordSchema(  # type: ignore[call-arg]
            timestamp=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
            feature_pipeline_version="feature_pipeline_v0.1.0",
        )
