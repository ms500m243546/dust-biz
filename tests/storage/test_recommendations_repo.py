from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.storage.models import Recommendation
from app.storage.repositories.recommendations import RecommendationRepository

T0 = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _make(rid: str, t: datetime, zone: str = "haul_c") -> Recommendation:
    return Recommendation(
        recommendation_id=rid,
        issued_at=t.replace(tzinfo=None),
        target_zone_id=zone,
        risk_event="PM10 breach risk",
        current_breach_probability=0.7,
        target_probability=0.25,
        recommended_actions=[],
        requires_human_review=False,
        compliance_priority_triggered=False,
        confidence=0.7,
        reason="test",
        model_version="optimization_weighted_v0.1.0",
        feature_pipeline_version="features_v0.1.0",
        input_data_quality_score=0.9,
        data_quality_warnings=[],
        linked_prediction_ids=[],
        linked_attribution_id=None,
        automation_level="L1",
        top_production_impact=None,
    )


def test_add_and_get(session: Session) -> None:
    repo = RecommendationRepository(session)
    repo.add(_make("REC-20260501-00001", T0))
    assert repo.get("REC-20260501-00001") is not None


def test_next_id_resets_per_day(session: Session) -> None:
    repo = RecommendationRepository(session)
    repo.add(_make("REC-20260501-00001", T0))
    assert repo.next_recommendation_id(T0.date()) == "REC-20260501-00002"
    assert repo.next_recommendation_id((T0 + timedelta(days=1)).date()) == "REC-20260502-00001"


def test_latest_for_zone(session: Session) -> None:
    repo = RecommendationRepository(session)
    repo.add(_make("REC-20260501-00001", T0 - timedelta(minutes=10)))
    repo.add(_make("REC-20260501-00002", T0))
    out = repo.latest_for_zone("haul_c")
    assert out is not None
    assert out.recommendation_id == "REC-20260501-00002"


def test_get_recent_filters(session: Session) -> None:
    repo = RecommendationRepository(session)
    repo.add(_make("REC-20260501-00001", T0 - timedelta(hours=2), zone="haul_c"))
    repo.add(_make("REC-20260501-00002", T0 - timedelta(minutes=10), zone="haul_c"))
    repo.add(_make("REC-20260501-00003", T0 - timedelta(minutes=5), zone="haul_d"))
    rows = repo.get_recent(
        since=(T0 - timedelta(hours=1)).replace(tzinfo=None),
        target_zone_id="haul_c",
    )
    assert {r.recommendation_id for r in rows} == {"REC-20260501-00002"}
