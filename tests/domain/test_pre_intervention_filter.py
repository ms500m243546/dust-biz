"""Phase M.3.1: pit_query.features_pre_intervention tests."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.domain.pit_query import features_pre_intervention
from app.storage.models import (
    Mine,
    Recommendation,
    RecommendationApproval,
    Sensor,
    SensorReading,
)


def _seed_sensor(session: Session) -> None:
    session.add(Mine(mine_id="los-pelambres", name="Los Pelambres"))
    session.add(
        Sensor(
            sensor_id="lp-em05-cuncumen",
            mine_id="los-pelambres",
            sensor_type="pm10",
        )
    )
    session.flush()


def _add_reading(
    session: Session, *, ts: datetime, valid_from: datetime, value: float
) -> None:
    session.add(
        SensorReading(
            sensor_id="lp-em05-cuncumen",
            timestamp=ts,
            raw_value={"v": value},
            valid_from=valid_from,
            valid_to=None,
        )
    )


def _add_intervention(
    session: Session, *, decided_at: datetime, idx: int = 0
) -> None:
    rec = Recommendation(
        recommendation_id=f"REC-PI-{idx}",
        issued_at=decided_at - timedelta(minutes=2),
        target_zone_id="Z-1",
        risk_event="dust",
        current_breach_probability=0.85,
        target_probability=0.3,
        recommended_actions=[],
        requires_human_review=True,
        compliance_priority_triggered=False,
        confidence=0.6,
        reason="x",
        model_version="v",
        feature_pipeline_version="fp",
        input_data_quality_score=0.9,
        data_quality_warnings=[],
        linked_prediction_ids=[],
        linked_attribution_id=None,
        automation_level="L1",
    )
    appr = RecommendationApproval(
        approval_id=f"APR-PI-{idx}",
        recommendation_id=rec.recommendation_id,
        approved_by="alice",
        approver_role="environmental_manager",
        decided_at=decided_at,
        approval_status="approved",
        chosen_action_rank=1,
        override_action=None,
        human_reason=None,
        automation_level_at_decision="L1",
    )
    session.add_all([rec, appr])
    session.flush()


def test_filter_drops_readings_in_intervention_window(session: Session) -> None:
    _seed_sensor(session)
    base = datetime(2026, 5, 1, 10, 0)

    # Reading inside the intervention window — should be filtered out.
    _add_reading(session, ts=base + timedelta(minutes=30), valid_from=base, value=100.0)
    # Reading outside (4 hours later) — should pass.
    _add_reading(session, ts=base + timedelta(hours=4), valid_from=base, value=50.0)
    # Reading before — passes.
    _add_reading(
        session,
        ts=base - timedelta(hours=1),
        valid_from=base - timedelta(hours=1),
        value=70.0,
    )
    _add_intervention(session, decided_at=base, idx=1)
    session.commit()

    rows = list(
        session.execute(
            features_pre_intervention(
                prediction_time=base + timedelta(hours=10),
                intervention_lag=timedelta(hours=3),
                sensor_id="lp-em05-cuncumen",
            )
        ).scalars()
    )
    values = sorted(r.raw_value["v"] for r in rows)
    assert values == [50.0, 70.0]


def test_filter_with_no_interventions_returns_all_readings(
    session: Session,
) -> None:
    _seed_sensor(session)
    base = datetime(2026, 5, 1, 10, 0)
    for i in range(3):
        _add_reading(
            session,
            ts=base + timedelta(hours=i),
            valid_from=base + timedelta(hours=i),
            value=float(i),
        )
    session.commit()

    rows = list(
        session.execute(
            features_pre_intervention(
                prediction_time=base + timedelta(days=1),
                sensor_id="lp-em05-cuncumen",
            )
        ).scalars()
    )
    assert len(rows) == 3


def test_filter_respects_pit_validity(session: Session) -> None:
    """A row only valid in the future of `prediction_time` is excluded."""
    _seed_sensor(session)
    base = datetime(2026, 5, 1, 10, 0)
    # Validated row that becomes legal only at base+7d.
    _add_reading(
        session,
        ts=base,
        valid_from=base + timedelta(days=7),
        value=42.0,
    )
    session.commit()

    rows = list(
        session.execute(
            features_pre_intervention(
                prediction_time=base + timedelta(days=1),
                sensor_id="lp-em05-cuncumen",
            )
        ).scalars()
    )
    assert len(rows) == 0


def test_filter_handles_multiple_interventions(session: Session) -> None:
    _seed_sensor(session)
    base = datetime(2026, 5, 1, 10, 0)
    # Two interventions 6h apart.
    _add_intervention(session, decided_at=base, idx=1)
    _add_intervention(session, decided_at=base + timedelta(hours=6), idx=2)
    # Three readings: in 1st window, between, in 2nd window.
    _add_reading(session, ts=base + timedelta(minutes=30), valid_from=base, value=10.0)  # blocked
    _add_reading(session, ts=base + timedelta(hours=4, minutes=0), valid_from=base, value=20.0)  # passes (between)
    _add_reading(
        session, ts=base + timedelta(hours=6, minutes=30), valid_from=base, value=30.0  # blocked
    )
    session.commit()

    rows = list(
        session.execute(
            features_pre_intervention(
                prediction_time=base + timedelta(days=1),
                intervention_lag=timedelta(hours=3),
                sensor_id="lp-em05-cuncumen",
            )
        ).scalars()
    )
    assert len(rows) == 1
    assert rows[0].raw_value["v"] == 20.0


def test_filter_without_sensor_id_returns_all_sensors(session: Session) -> None:
    _seed_sensor(session)
    session.add(
        Sensor(
            sensor_id="lp-other",
            mine_id="los-pelambres",
            sensor_type="pm10",
        )
    )
    base = datetime(2026, 5, 1, 10, 0)
    session.add(
        SensorReading(
            sensor_id="lp-em05-cuncumen",
            timestamp=base,
            raw_value={"v": 1.0},
            valid_from=base,
            valid_to=None,
        )
    )
    session.add(
        SensorReading(
            sensor_id="lp-other",
            timestamp=base,
            raw_value={"v": 2.0},
            valid_from=base,
            valid_to=None,
        )
    )
    session.commit()

    rows = list(
        session.execute(
            features_pre_intervention(prediction_time=base + timedelta(hours=1))
        ).scalars()
    )
    assert len(rows) == 2
