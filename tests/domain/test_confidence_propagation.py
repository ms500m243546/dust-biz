"""Phase V.3 — confidence propagation regression suite.

Asserts that confidence flows honestly through the prediction →
intervention → cost stack. Each model must scale its raw confidence
by `input_data_quality_score` (Guardrail 4); fallback paths must
emit lower confidence than the model path; and AP-42 + cycle-time
physics paths get a small confidence boost over the heuristic-
fallback flow (because the reduction fractions are grounded in
published physics, not a hand-tuned constant).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import joblib  # type: ignore[import-untyped]
import numpy as np
import pytest
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
)

from app.models.cost.cycle_time_v0_1_0 import CycleTimeProductionCost
from app.models.cost.heuristic_baseline import HeuristicProductionCost
from app.models.forecasting.gbm_v0_1_0 import (
    GBMForecaster,
    artifact_path,
)
from app.models.forecasting.heuristic_baseline import HeuristicBaselineForecaster
from app.models.intervention.ap42_v0_1_0 import AP42InterventionImpact
from app.models.intervention.heuristic_baseline import HeuristicInterventionImpact
from app.schemas.features import FeatureRecordSchema
from app.schemas.forecasts import ForecastTargetSchema
from app.schemas.interventions import InterventionOptionSchema
from app.training.dust_forecast_training import (
    FEATURE_PIPELINE_VERSION,
    FEATURE_SET_P1,
    GBM_VERSION,
)


def _option(intervention_id: str, *, risk: str = "low") -> InterventionOptionSchema:
    return InterventionOptionSchema(
        intervention_id=intervention_id,
        name=intervention_id,
        description="t",
        risk_class=risk,  # type: ignore[arg-type]
        requires_human_approval=False,
        automation_eligible_levels=["L1"],
        estimated_time_to_effect_minutes=10,
        allowed_zone_types=["haul_road"],
    )


def _features(payload: dict[str, object] | None = None) -> FeatureRecordSchema:
    return FeatureRecordSchema(
        timestamp=datetime(2026, 5, 3, 12, 0),
        zone_id="z",
        feature_pipeline_version=FEATURE_PIPELINE_VERSION,
        feature_payload=payload or {
            "pm.pm10_avg_15min": 60.0,
            "pm.pm25_avg_15min": 25.0,
            "pm.pm10_trend_per_min": 0.5,
            "pm.pm25_trend_per_min": 0.2,
            "wind.speed_ms": 5.0,
            "wind.humidity_pct": 50.0,
            "state.wind_exposure": "medium",
            "state.dust_generation_potential": "medium",
        },
        missing_inputs=[],
    )


def _persist_minimal_gbm_artifact(tmp_path: Path, station_id: str) -> Path:
    """Fit a 1-feature GBM bundle and persist at the canonical path.

    Saves a tiny synthetic dataset; the artifact's actual predictions
    aren't load-bearing for these tests — only the bundle shape.
    """
    rng = np.random.default_rng(0)
    X = rng.normal(size=(64, len(FEATURE_SET_P1)))
    y_pm10 = X[:, 0] * 10 + 50
    y_breach = (y_pm10 > 60).astype(int)
    reg = HistGradientBoostingRegressor(max_iter=20, random_state=0).fit(X, y_pm10)
    clf = HistGradientBoostingClassifier(max_iter=20, random_state=0).fit(X, y_breach)
    bundle = {
        "model": {"regressor": reg, "classifier": clf},
        "feature_columns": list(FEATURE_SET_P1),
        "feature_pipeline_version": FEATURE_PIPELINE_VERSION,
        "training_protocol_hash": "test-hash",
        "training_protocol_version": "M.4",
        "horizon": "60min",
        "station_id": station_id,
        "recalibrated": False,
    }
    p = artifact_path(
        artifact_root=tmp_path,
        model_version=GBM_VERSION,
        station_id=station_id,
        horizon="60min",
    )
    p.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, p)
    return p


def test_heuristic_forecast_confidence_scales_with_data_quality() -> None:
    f = HeuristicBaselineForecaster()
    target = ForecastTargetSchema(target_kind="zone", target_id="z")
    high_dq = f.predict(
        features=_features(),
        target=target,
        horizon="60min",
        input_data_quality_score=1.0,
    )
    low_dq = f.predict(
        features=_features(),
        target=target,
        horizon="60min",
        input_data_quality_score=0.3,
    )
    assert high_dq.confidence > low_dq.confidence
    # Confidence must scale roughly linearly with the multiplier.
    ratio = low_dq.confidence / high_dq.confidence if high_dq.confidence > 0 else 0
    assert 0.2 <= ratio <= 0.4


def test_gbm_forecast_confidence_scales_with_data_quality(tmp_path: Path) -> None:
    _persist_minimal_gbm_artifact(tmp_path, "s1")
    f = GBMForecaster(artifact_root=tmp_path)
    target = ForecastTargetSchema(target_kind="sensor", target_id="s1")
    payload = dict.fromkeys(FEATURE_SET_P1, 0.0)
    feats = FeatureRecordSchema(
        timestamp=datetime(2026, 5, 3, 12, 0),
        zone_id="z",
        feature_pipeline_version=FEATURE_PIPELINE_VERSION,
        feature_payload=payload,
        missing_inputs=[],
    )
    high = f.predict(features=feats, target=target, horizon="60min", input_data_quality_score=1.0)
    low = f.predict(features=feats, target=target, horizon="60min", input_data_quality_score=0.3)
    assert high.confidence > low.confidence


def test_heuristic_forecast_fallback_emits_lower_confidence_and_flag() -> None:
    f = HeuristicBaselineForecaster()
    target = ForecastTargetSchema(target_kind="zone", target_id="z")
    # Missing PM features → fallback path engages.
    bad = f.predict(
        features=_features({"wind.speed_ms": 5.0}),
        target=target,
        horizon="60min",
    )
    assert bad.source == "heuristic_fallback"
    assert bad.confidence <= 0.30  # explicit cap on fallback raw conf


def test_ap42_intervention_confidence_above_heuristic_for_physics_paths() -> None:
    ap42 = AP42InterventionImpact()
    heur = HeuristicInterventionImpact()
    for iid in ("water_road", "reduce_speed"):
        opt = _option(iid)
        a_out = ap42.simulate(
            intervention=opt,
            target_zone_id="z",
            predicted_pm10=100.0,
            predicted_pm25=40.0,
            breach_probability_before=0.4,
        )
        h_out = heur.simulate(
            intervention=opt,
            target_zone_id="z",
            predicted_pm10=100.0,
            predicted_pm25=40.0,
            breach_probability_before=0.4,
        )
        assert a_out.confidence > h_out.confidence, (
            f"AP-42 confidence {a_out.confidence} must exceed heuristic "
            f"{h_out.confidence} for physics-applicable {iid}"
        )


def test_ap42_fallback_intervention_matches_heuristic_confidence() -> None:
    ap42 = AP42InterventionImpact()
    heur = HeuristicInterventionImpact()
    opt = _option("throttle_crusher")  # not AP-42-applicable
    a_out = ap42.simulate(
        intervention=opt,
        target_zone_id="z",
        predicted_pm10=100.0,
        predicted_pm25=40.0,
        breach_probability_before=0.4,
    )
    h_out = heur.simulate(
        intervention=opt,
        target_zone_id="z",
        predicted_pm10=100.0,
        predicted_pm25=40.0,
        breach_probability_before=0.4,
    )
    # Equal: fallback path doesn't get the physics confidence boost.
    assert a_out.confidence == pytest.approx(h_out.confidence, abs=0.001)


def test_cycle_time_cost_confidence_above_heuristic_for_physics_paths() -> None:
    ct = CycleTimeProductionCost()
    heur = HeuristicProductionCost()
    for iid in ("water_road", "reduce_speed"):
        opt = _option(iid)
        c_out = ct.estimate_cost(
            intervention=opt,
            target_zone_id="z",
            production_rate_tph=1000.0,
            duration_minutes=60,
        )
        h_out = heur.estimate_cost(
            intervention=opt,
            target_zone_id="z",
            production_rate_tph=1000.0,
            duration_minutes=60,
        )
        assert c_out.confidence > h_out.confidence


def test_no_production_rate_lowers_cost_confidence() -> None:
    ct = CycleTimeProductionCost()
    high = ct.estimate_cost(
        intervention=_option("reduce_speed"),
        target_zone_id="z",
        production_rate_tph=1000.0,
        duration_minutes=60,
    )
    low = ct.estimate_cost(
        intervention=_option("reduce_speed"),
        target_zone_id="z",
        production_rate_tph=None,
        duration_minutes=60,
    )
    assert low.confidence < high.confidence
