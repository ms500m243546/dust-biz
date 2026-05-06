"""Intervention simulation orchestration (S9 + S10 joined).

`simulate_intervention` composes the moving parts of one candidate
scenario:
  1. Resolve the intervention from the S8 catalog (404 if unknown).
  2. Find the latest persisted forecast for the target zone (404 if
     none - we will not invent a baseline).
  3. Look up the latest MineState snapshot for the target zone to
     read `production_rate_tph` for the cost model. Missing snapshot
     => cost confidence drops, tonnes degrade per S10 contract.
  4. Resolve the current `intervention_impact` and `production_cost`
     models from the registry (lazy-register heuristic baselines).
  5. Call both models with typed inputs (universal model rule 5).
  6. Join into a single `InterventionSimulationSchema` and persist.

`simulate_do_nothing` is the counterfactual companion: same flow but
the intervention is the reserved `_do_nothing_` shape, so impact
returns zero reduction and cost returns zero tonnes - giving the
recommendation engine a comparable "no-op" candidate.

Per the layer rule (`docs/architecture.md`), this module sits in
`app/domain/`; it imports models, schemas, and storage but never the
API layer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.domain.dispersion_intervention import (
    apply_dispersion_uplift,
    compute_dispersion_uplift,
)
from app.domain.interventions import (
    UnknownInterventionError,
    require_known,
    seed_default_interventions,
)
from app.models import registry
from app.models.cost.heuristic_baseline import HeuristicProductionCost
from app.models.intervention.heuristic_baseline import HeuristicInterventionImpact
from app.schemas.interventions import InterventionOptionSchema
from app.schemas.simulations import (
    DO_NOTHING_INTERVENTION_ID,
    InterventionImpactSchema,
    InterventionSimulationSchema,
    ProductionCostEstimateSchema,
    ProductionImpact,
)
from app.storage.models import (
    InterventionSimulation,
    MineStateSnapshot,
    Zone,
)
from app.storage.repositories.forecasts import DustPredictionRepository
from app.storage.repositories.interventions import InterventionOptionRepository
from app.storage.repositories.mine_state import MineStateSnapshotRepository
from app.storage.repositories.simulations import InterventionSimulationRepository


class ZoneNotFoundError(LookupError):
    """Raised when the target_zone_id has no Zone row."""


class NoForecastError(LookupError):
    """Raised when no forecast has been issued for the target zone."""


def ensure_models_registered() -> None:
    """Lazy-register heuristic baselines for both kinds.

    Same pattern as forecasting: keeps tests and bootstrap simple at
    MVP scale; revisit when multi-tenancy lands (E2-R2).
    """
    try:
        registry.get_current("intervention_impact")
    except registry.ModelNotFoundError:
        registry.register(HeuristicInterventionImpact())
    try:
        registry.get_current("production_cost")
    except registry.ModelNotFoundError:
        registry.register(HeuristicProductionCost())


def simulate_intervention(
    *,
    session: Session,
    intervention_id: str,
    target_zone_id: str,
    duration_minutes: int | None = None,
    now: datetime | None = None,
) -> InterventionSimulationSchema:
    """Run S9+S10 for one candidate intervention against a target zone."""
    requested_at = (now or datetime.now(UTC)).replace(microsecond=0)

    zone = session.get(Zone, target_zone_id)
    if zone is None:
        raise ZoneNotFoundError(f"target zone not found: {target_zone_id}")

    # Validate the catalog ID. Unknown -> hard error per S8 failure mode.
    require_known(session, [intervention_id])
    option_row = InterventionOptionRepository(session).get(intervention_id)
    assert option_row is not None  # require_known guarantees existence
    intervention = InterventionOptionSchema.model_validate(option_row)

    forecast = _latest_forecast_for_zone(session, target_zone_id)
    if forecast is None:
        raise NoForecastError(
            f"no forecast available for zone {target_zone_id}; issue a forecast first"
        )

    production_rate = _production_rate_for_zone(session, target_zone_id)

    ensure_models_registered()
    impact_model: Any = registry.get_current("intervention_impact")
    cost_model: Any = registry.get_current("production_cost")

    impact: InterventionImpactSchema = impact_model.simulate(
        intervention=intervention,
        target_zone_id=target_zone_id,
        predicted_pm10=forecast.predicted_pm10,
        predicted_pm25=forecast.predicted_pm25,
        breach_probability_before=forecast.breach_probability,
    )
    # Phase BA.9 / BD.2 — dispersion-aware uplift on the impact's
    # reduction + breach delta when a CFD lookup model is current.
    impact = _apply_dispersion_uplift_to_impact(
        session=session,
        impact=impact,
        mine_id=zone.mine_id,
        receptor_id=forecast.target_id,
        as_of=forecast.issued_at,
    )
    cost: ProductionCostEstimateSchema = cost_model.estimate_cost(
        intervention=intervention,
        target_zone_id=target_zone_id,
        production_rate_tph=production_rate,
        duration_minutes=duration_minutes,
    )

    schema = _join(
        session=session,
        requested_at=requested_at,
        intervention=intervention,
        impact=impact,
        cost=cost,
    )
    _persist(session, schema)
    return schema


def simulate_do_nothing(
    *,
    session: Session,
    target_zone_id: str,
    now: datetime | None = None,
) -> InterventionSimulationSchema:
    """Counterfactual "no-op" candidate.

    Returns the current breach probability unchanged, zero tonnes, and
    high confidence so the recommendation engine has a baseline to rank
    against. Persists like any other simulation row.
    """
    requested_at = (now or datetime.now(UTC)).replace(microsecond=0)

    if session.get(Zone, target_zone_id) is None:
        raise ZoneNotFoundError(f"target zone not found: {target_zone_id}")

    forecast = _latest_forecast_for_zone(session, target_zone_id)
    if forecast is None:
        raise NoForecastError(
            f"no forecast available for zone {target_zone_id}; issue a forecast first"
        )

    ensure_models_registered()
    impact_model: Any = registry.get_current("intervention_impact")
    cost_model: Any = registry.get_current("production_cost")

    placeholder = InterventionOptionSchema(
        intervention_id=DO_NOTHING_INTERVENTION_ID,
        name="Do nothing",
        description="Counterfactual: no operational change.",
        risk_class="low",
        requires_human_approval=False,
        automation_eligible_levels=[],
        estimated_time_to_effect_minutes=0,
        allowed_zone_types=[],
    )

    impact: InterventionImpactSchema = impact_model.simulate(
        intervention=placeholder,
        target_zone_id=target_zone_id,
        predicted_pm10=forecast.predicted_pm10,
        predicted_pm25=forecast.predicted_pm25,
        breach_probability_before=forecast.breach_probability,
    )
    cost: ProductionCostEstimateSchema = cost_model.estimate_cost(
        intervention=placeholder,
        target_zone_id=target_zone_id,
        production_rate_tph=_production_rate_for_zone(session, target_zone_id),
        duration_minutes=0,
    )

    schema = _join(
        session=session,
        requested_at=requested_at,
        intervention=placeholder,
        impact=impact,
        cost=cost,
        scenario_override="Do nothing (counterfactual baseline)",
    )
    _persist(session, schema)
    return schema


def _apply_dispersion_uplift_to_impact(
    *,
    session: Session,
    impact: InterventionImpactSchema,
    mine_id: str,
    receptor_id: str,
    as_of: datetime,
) -> InterventionImpactSchema:
    """Post-multiply the impact reduction + breach delta by the uplift.

    Returns the impact unchanged when no CFD dispersion model is
    promoted; otherwise scales `predicted_pm10_reduction` and
    `breach_probability_after_action` (toward the before-value) by
    the clamped multiplier.
    """
    uplift = compute_dispersion_uplift(
        session, mine_id=mine_id, receptor_id=receptor_id, as_of=as_of,
    )
    if uplift is None:
        return impact
    new_red, new_after = apply_dispersion_uplift(
        predicted_pm10_reduction=impact.predicted_pm10_reduction,
        breach_probability_before=impact.breach_probability_before,
        breach_probability_after=impact.breach_probability_after_action,
        uplift=uplift,
    )
    return impact.model_copy(update={
        "predicted_pm10_reduction": round(new_red, 3),
        "breach_probability_after_action": round(new_after, 4),
    })


def _latest_forecast_for_zone(session: Session, zone_id: str) -> Any:
    """Latest forecast keyed to the zone OR to a sensor in that zone."""
    repo = DustPredictionRepository(session)
    forecast = repo.latest_for_target("zone", zone_id)
    if forecast is not None:
        return forecast
    # Fall back to sensor-targeted forecasts whose sensor lives in this zone.
    from app.storage.models import Sensor

    sensors_in_zone = list(
        session.query(Sensor.sensor_id).filter(Sensor.zone_id == zone_id).all()
    )
    best_forecast = None
    for (sensor_id,) in sensors_in_zone:
        f = repo.latest_for_target("sensor", sensor_id)
        if f is None:
            continue
        if best_forecast is None or f.issued_at > best_forecast.issued_at:
            best_forecast = f
    return best_forecast


def _production_rate_for_zone(session: Session, zone_id: str) -> float | None:
    snap: MineStateSnapshot | None = MineStateSnapshotRepository(
        session
    ).latest_for_zone(zone_id)
    if snap is None:
        return None
    return snap.production_rate_tph


def _join(
    *,
    session: Session,
    requested_at: datetime,
    intervention: InterventionOptionSchema,
    impact: InterventionImpactSchema,
    cost: ProductionCostEstimateSchema,
    scenario_override: str | None = None,
) -> InterventionSimulationSchema:
    repo = InterventionSimulationRepository(session)
    sim_id = repo.next_simulation_id(requested_at.date())
    scenario = scenario_override or _scenario_phrase(intervention, impact.target_zone_id)
    # Joined confidence is the lower of impact and cost confidences -
    # the simulation is only as trustworthy as its weakest input.
    joined_conf = round(min(impact.confidence, cost.confidence), 3)

    return InterventionSimulationSchema(
        simulation_id=sim_id,
        requested_at=requested_at,
        intervention_id=intervention.intervention_id,
        target_zone_id=impact.target_zone_id,
        scenario=scenario,
        predicted_pm10_reduction=impact.predicted_pm10_reduction,
        predicted_pm25_reduction=impact.predicted_pm25_reduction,
        breach_probability_before=impact.breach_probability_before,
        breach_probability_after=impact.breach_probability_after_action,
        time_to_effect_minutes=impact.time_to_effect_minutes,
        production_loss_tonnes=cost.estimated_tonnes_delayed,
        cycle_time_increase_percent=cost.cycle_time_increase_percent,
        production_impact=_as_impact(cost.production_impact),
        confidence=joined_conf,
        model_version=impact.model_version,
        cost_model_version=cost.model_version,
        source=impact.source,
        main_uncertainty=impact.main_uncertainty,
    )


def _as_impact(value: str) -> ProductionImpact:
    if value not in ("low", "medium", "high"):
        return "low"
    return value  # type: ignore[return-value]


def _scenario_phrase(intervention: InterventionOptionSchema, zone_id: str) -> str:
    return f"{intervention.name} on {zone_id}"


def _persist(
    session: Session, schema: InterventionSimulationSchema
) -> InterventionSimulation:
    repo = InterventionSimulationRepository(session)
    row = InterventionSimulation(
        simulation_id=schema.simulation_id,
        requested_at=(
            schema.requested_at.replace(tzinfo=None)
            if schema.requested_at.tzinfo
            else schema.requested_at
        ),
        intervention_id=schema.intervention_id,
        target_zone_id=schema.target_zone_id,
        scenario=schema.scenario,
        predicted_pm10_reduction=schema.predicted_pm10_reduction,
        predicted_pm25_reduction=schema.predicted_pm25_reduction,
        breach_probability_before=schema.breach_probability_before,
        breach_probability_after=schema.breach_probability_after,
        time_to_effect_minutes=schema.time_to_effect_minutes,
        production_loss_tonnes=schema.production_loss_tonnes,
        cycle_time_increase_percent=schema.cycle_time_increase_percent,
        production_impact=schema.production_impact,
        confidence=schema.confidence,
        model_version=schema.model_version,
        cost_model_version=schema.cost_model_version,
        source=schema.source,
        main_uncertainty=schema.main_uncertainty,
    )
    return repo.add(row)


__all__ = [
    "NoForecastError",
    "UnknownInterventionError",
    "ZoneNotFoundError",
    "ensure_models_registered",
    "seed_default_interventions",
    "simulate_do_nothing",
    "simulate_intervention",
]
