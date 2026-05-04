"""Recommendation orchestration (S12).

`generate_recommendation` ties Phase E (forecast), Phase F
(attribution), Phase G (intervention library + simulation joined
with cost), and Phase H (optimization engine) into a single audited
record:

  1. Resolve the target zone + its mine + the active site config
     (require_resolved -> fail loudly on missing config per D-R2).
  2. Pull the latest DustForecast for the zone (zone-targeted first;
     sensor-in-zone fallback - same rule as the simulation
     orchestrator).
  3. For every InterventionOption whose `allowed_zone_types` admits
     the zone, run `simulate_intervention(...)` against the forecast.
     Add `simulate_do_nothing(...)` as the counterfactual.
  4. Resolve the current `optimization` model from the registry
     (lazy-register the heuristic baseline) and call rank_actions(...)
     with the active site_config weights and thresholds.
  5. Apply G6 high-risk gating: when requires_human_review is true,
     drop high-risk-class actions from the surfaced ranking; keep the
     do-nothing baseline + low-risk options + monitor/alert paths.
  6. Render the S12 template (six-line text aimed at a shift
     supervisor in <30s) and persist a Recommendation row keyed
     `REC-YYYYMMDD-NNNNN`.

Per the layer rule (`docs/architecture.md`), this module sits in
`app/domain/`; it imports models, schemas, and storage but never
the API layer. Per `safety-guardrails.md` "Safety-reviewer subagent
triggers", touching this file should trigger the safety reviewer
before merge.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.interventions import seed_default_interventions
from app.domain.shift_progress import compute_shift_progress
from app.domain.simulation import (
    NoForecastError,
    ZoneNotFoundError,
    simulate_do_nothing,
    simulate_intervention,
)
from app.domain.site_config_resolver import require_resolved
from app.domain.temporal_trigger import synthesize_flat_track
from app.models import registry
from app.models.optimization.heuristic_baseline import WeightedOptimizationEngine
from app.schemas.recommendations import (
    RecommendationActionSchema,
    RecommendationSchema,
)
from app.schemas.simulations import (
    DO_NOTHING_INTERVENTION_ID,
    InterventionSimulationSchema,
)
from app.storage.models import (
    DustPrediction,
    InterventionOption,
    Mine,
    Recommendation,
    SiteConfiguration,
    SourceAttribution,
    Zone,
)
from app.storage.repositories.attributions import SourceAttributionRepository
from app.storage.repositories.forecasts import DustPredictionRepository
from app.storage.repositories.recommendations import RecommendationRepository

# Risk classes that must be suppressed when the engine flags the
# overall recommendation for human review (G6). Low-risk monitoring +
# the do-nothing counterfactual remain so the supervisor still sees
# something to act on.
_HIGH_RISK_CLASSES = frozenset({"medium", "high"})


def ensure_optimizer_registered() -> None:
    try:
        registry.get_current("optimization")
    except registry.ModelNotFoundError:
        registry.register(WeightedOptimizationEngine())


def generate_recommendation(
    *,
    session: Session,
    target_zone_id: str,
    now: datetime | None = None,
) -> RecommendationSchema:
    """Run S12 for one target zone."""
    issued_at = (now or datetime.now(UTC)).replace(microsecond=0)

    zone = session.get(Zone, target_zone_id)
    if zone is None:
        raise ZoneNotFoundError(f"target zone not found: {target_zone_id}")

    mine = session.get(Mine, zone.mine_id)
    site_cfgs = list(
        session.execute(
            select(SiteConfiguration).where(SiteConfiguration.mine_id == zone.mine_id)
        ).scalars()
    )
    site_cfg_row = site_cfgs[0] if site_cfgs else None
    site_cfg = require_resolved(
        mine_id=zone.mine_id, site_config=site_cfg_row, mine=mine
    )

    forecast = _latest_forecast_for_zone(session, target_zone_id)
    if forecast is None:
        raise NoForecastError(
            f"no forecast available for zone {target_zone_id}; issue a forecast first"
        )

    seed_default_interventions(session)
    catalog = _eligible_catalog(session, zone)

    sims, risk_classes, requires_approval, cause_classes_map = _simulate_all(
        session=session,
        target_zone_id=target_zone_id,
        catalog=catalog,
        now=issued_at,
    )
    do_nothing_sim = simulate_do_nothing(
        session=session, target_zone_id=target_zone_id, now=issued_at
    )
    sims.append(do_nothing_sim)
    risk_classes[DO_NOTHING_INTERVENTION_ID] = "low"
    requires_approval[DO_NOTHING_INTERVENTION_ID] = False
    cause_classes_map[DO_NOTHING_INTERVENTION_ID] = []

    attribution_row = _latest_attribution_for_forecast(session, forecast)
    cause_class = _resolve_cause_class(session, attribution_row)

    shift_progress = compute_shift_progress(
        session=session,
        mine_id=zone.mine_id,
        now=issued_at,
        cost_curves=site_cfg.cost_curves,
    )

    ensure_optimizer_registered()
    engine: Any = registry.get_current("optimization")
    ranked = engine.rank_actions(
        target_zone_id=target_zone_id,
        breach_probability_before=forecast.breach_probability,
        candidates=sims,
        candidate_risk_classes=risk_classes,
        candidate_requires_approval=requires_approval,
        weights=site_cfg.optimization_weights,
        extreme_breach_threshold=site_cfg.extreme_breach_threshold,
        low_confidence_threshold=site_cfg.low_confidence_threshold,
        cause_class=cause_class,
        candidate_target_cause_classes=cause_classes_map,
        shift_progress=shift_progress,
        forecast_track=synthesize_flat_track(
            breach_probability=forecast.breach_probability,
        ),
    )

    surfaced = _filter_for_review(
        candidates=ranked.candidates,
        requires_human_review=ranked.requires_human_review,
    )
    actions = [_to_action(c, sim_lookup=_index(sims)) for c in surfaced]

    attribution_id = (
        attribution_row.attribution_id if attribution_row is not None else None
    )

    schema = _render(
        recommendation_id=_next_id(session, issued_at),
        issued_at=issued_at,
        target_zone_id=target_zone_id,
        forecast=forecast,
        ranked=ranked,
        actions=actions,
        site_cfg_automation_level=site_cfg.automation_level,
        attribution_id=attribution_id,
    )
    _persist(session, schema)
    return schema


def _latest_forecast_for_zone(session: Session, zone_id: str) -> Any:
    repo = DustPredictionRepository(session)
    forecast = repo.latest_for_target("zone", zone_id)
    if forecast is not None:
        return forecast
    from app.storage.models import Sensor

    sensors_in_zone = list(
        session.query(Sensor.sensor_id).filter(Sensor.zone_id == zone_id).all()
    )
    best = None
    for (sensor_id,) in sensors_in_zone:
        f = repo.latest_for_target("sensor", sensor_id)
        if f is None:
            continue
        if best is None or f.issued_at > best.issued_at:
            best = f
    return best


def _eligible_catalog(session: Session, zone: Zone) -> list[InterventionOption]:
    """Catalog entries whose allowed_zone_types includes this zone's type."""
    rows = list(
        session.execute(select(InterventionOption)).scalars()
    )
    return [r for r in rows if zone.zone_type in (r.allowed_zone_types or [])]


def _simulate_all(
    *,
    session: Session,
    target_zone_id: str,
    catalog: list[InterventionOption],
    now: datetime,
) -> tuple[
    list[InterventionSimulationSchema],
    dict[str, str],
    dict[str, bool],
    dict[str, list[str]],
]:
    sims: list[InterventionSimulationSchema] = []
    risk_classes: dict[str, str] = {}
    requires_approval: dict[str, bool] = {}
    cause_classes_map: dict[str, list[str]] = {}
    for entry in catalog:
        sim = simulate_intervention(
            session=session,
            intervention_id=entry.intervention_id,
            target_zone_id=target_zone_id,
            now=now,
        )
        sims.append(sim)
        risk_classes[entry.intervention_id] = entry.risk_class
        requires_approval[entry.intervention_id] = entry.requires_human_approval
        cause_classes_map[entry.intervention_id] = list(
            entry.target_cause_classes or []
        )
    return sims, risk_classes, requires_approval, cause_classes_map


def _filter_for_review(
    *,
    candidates: list[Any],
    requires_human_review: bool,
) -> list[Any]:
    """G6: under low-confidence review, drop high/medium-risk actions.

    The optimizer still ranks them; the orchestrator hides them from
    the supervisor's surfaced list so a low-confidence model can't push
    a high-impact change. The do-nothing baseline and low-risk monitor
    paths remain.
    """
    if not requires_human_review:
        return candidates
    return [c for c in candidates if c.risk_class not in _HIGH_RISK_CLASSES]


def _to_action(
    candidate: Any,
    *,
    sim_lookup: dict[str, InterventionSimulationSchema],
) -> RecommendationActionSchema:
    sim = sim_lookup.get(candidate.simulation_id)
    return RecommendationActionSchema(
        rank=candidate.rank,
        intervention_id=candidate.intervention_id,
        action=_action_phrase(candidate, sim),
        breach_probability_after=candidate.breach_probability_after,
        production_loss=candidate.production_loss,
        estimated_tonnes_delayed=candidate.estimated_tonnes_delayed,
        confidence=candidate.confidence,
        reason=candidate.reason,
        requires_human_approval=candidate.requires_human_approval,
        risk_class=candidate.risk_class,
        simulation_id=candidate.simulation_id,
    )


def _action_phrase(candidate: Any, sim: InterventionSimulationSchema | None) -> str:
    if sim is not None:
        return sim.scenario
    if candidate.intervention_id == DO_NOTHING_INTERVENTION_ID:
        return "Do nothing (monitor only)"
    return str(candidate.intervention_id)


def _index(
    sims: list[InterventionSimulationSchema],
) -> dict[str, InterventionSimulationSchema]:
    return {s.simulation_id: s for s in sims}


def _latest_attribution_for_forecast(
    session: Session, forecast: DustPrediction
) -> SourceAttribution | None:
    """Best-effort link to the latest attribution row for the same station.

    Recommendations don't require an attribution to issue. When one is
    available, the orchestrator uses it for two things: (1) link the
    attribution_id into the persisted recommendation; (2) resolve the
    top probable source's zone_type as the Phase Z cause class so the
    optimizer can apply the cause-coupling boost.
    """
    repo = SourceAttributionRepository(session)
    rows = repo.get_recent(
        since=forecast.issued_at,
        limit=10,
    )
    for row in rows:
        if row.affected_station == forecast.target_id:
            return row
    return None


def _resolve_cause_class(
    session: Session, attribution: SourceAttribution | None
) -> str | None:
    """Phase Z — resolve the cause-class hint from the top probable source.

    The attribution model writes ranked sources keyed by `zone_id`
    (plus the `external_background` floor). We pull the top entry and
    look up its zone to get the canonical zone_type — that's the cause
    class. Returns None when:
      - no attribution row, or
      - the top source isn't a real zone (Unknown / external_background), or
      - the named zone has been deleted since attribution time.

    A None return means the optimizer skips the cause-coupling boost
    entirely; no candidate is preferred over another on cause grounds.
    """
    if attribution is None:
        return None
    sources = attribution.probable_sources or []
    if not sources:
        return None
    top = sources[0]
    if not isinstance(top, dict):
        return None
    source_id = top.get("source")
    if not isinstance(source_id, str) or not source_id:
        return None
    if source_id in {"Unknown", "external_background"}:
        return None
    zone = session.get(Zone, source_id)
    if zone is None:
        return None
    return zone.zone_type


def _next_id(session: Session, issued_at: datetime) -> str:
    return RecommendationRepository(session).next_recommendation_id(issued_at.date())


def _render(
    *,
    recommendation_id: str,
    issued_at: datetime,
    target_zone_id: str,
    forecast: DustPrediction,
    ranked: Any,
    actions: list[RecommendationActionSchema],
    site_cfg_automation_level: str,
    attribution_id: str | None,
) -> RecommendationSchema:
    risk_event = (
        f"PM10 breach risk at {forecast.target_id} "
        f"(p={forecast.breach_probability:.0%}, horizon {forecast.forecast_horizon})"
    )

    top_action_phrase = (
        actions[0].action if actions else "Monitor closely; no safe automated action available"
    )

    reason_lines: list[str] = []
    reason_lines.append(f"Risk: PM10 breach likely at {forecast.target_id}.")
    if attribution_id is not None:
        reason_lines.append(f"Cause: see attribution {attribution_id}.")
    cause_class = getattr(ranked, "cause_class", None)
    if cause_class:
        reason_lines.append(
            f"Cause class: {cause_class}; cause-targeted actions preferred."
        )
    slack = getattr(ranked, "shift_slack_ratio", None)
    if isinstance(slack, (int, float)):
        if slack < 0.85:
            reason_lines.append(
                f"Shift behind plan (slack {slack:.2f}); production weight up."
            )
        elif slack > 1.15:
            reason_lines.append(
                f"Shift ahead of plan (slack {slack:.2f}); production weight down."
            )
    if ranked.compliance_priority_triggered:
        reason_lines.append(
            "Extreme breach risk - compliance prioritized over production."
        )
    reason_lines.append(f"Recommended action: {top_action_phrase}.")
    if actions:
        reason_lines.append(
            f"Expected result: breach probability "
            f"{forecast.breach_probability:.0%} -> "
            f"{actions[0].breach_probability_after:.0%}."
        )
        reason_lines.append(
            f"Production impact: {actions[0].production_loss}; "
            f"~{int(actions[0].estimated_tonnes_delayed)} tonnes delayed."
        )
    reason_lines.append(f"Confidence: {ranked.overall_confidence:.0%}.")
    if ranked.requires_human_review:
        reason_lines.append(
            "Confidence below review threshold; supervisor judgement required."
        )

    top_impact = actions[0].production_loss if actions else None

    return RecommendationSchema(
        recommendation_id=recommendation_id,
        issued_at=issued_at,
        target_zone_id=target_zone_id,
        risk_event=risk_event,
        current_breach_probability=round(forecast.breach_probability, 4),
        target_probability=ranked.target_probability,
        recommended_actions=actions,
        requires_human_review=ranked.requires_human_review,
        compliance_priority_triggered=ranked.compliance_priority_triggered,
        confidence=ranked.overall_confidence,
        reason=" ".join(reason_lines),
        model_version=ranked.model_version,
        feature_pipeline_version=forecast.feature_pipeline_version,
        input_data_quality_score=forecast.input_data_quality_score,
        data_quality_warnings=list(forecast.data_quality_warnings or []),
        linked_prediction_ids=[forecast.prediction_id],
        linked_attribution_id=attribution_id,
        automation_level=site_cfg_automation_level,
        top_production_impact=top_impact,
    )


def _persist(session: Session, schema: RecommendationSchema) -> Recommendation:
    repo = RecommendationRepository(session)
    issued_at = (
        schema.issued_at.replace(tzinfo=None)
        if schema.issued_at.tzinfo
        else schema.issued_at
    )
    row = Recommendation(
        recommendation_id=schema.recommendation_id,
        issued_at=issued_at,
        target_zone_id=schema.target_zone_id,
        risk_event=schema.risk_event,
        current_breach_probability=schema.current_breach_probability,
        target_probability=schema.target_probability,
        recommended_actions=[a.model_dump() for a in schema.recommended_actions],
        requires_human_review=schema.requires_human_review,
        compliance_priority_triggered=schema.compliance_priority_triggered,
        confidence=schema.confidence,
        reason=schema.reason,
        model_version=schema.model_version,
        feature_pipeline_version=schema.feature_pipeline_version,
        input_data_quality_score=schema.input_data_quality_score,
        data_quality_warnings=list(schema.data_quality_warnings),
        linked_prediction_ids=list(schema.linked_prediction_ids),
        linked_attribution_id=schema.linked_attribution_id,
        automation_level=schema.automation_level,
        top_production_impact=schema.top_production_impact,
    )
    return repo.add(row)


# Re-export for the API layer's exception handlers.
__all__ = [
    "NoForecastError",
    "ZoneNotFoundError",
    "ensure_optimizer_registered",
    "generate_recommendation",
]


# SourceAttribution is now used directly by `_latest_attribution_for_forecast`
# and `_resolve_cause_class`; the explicit reference below is no longer
# needed but kept as a defensive anchor against accidental import pruning.
_ = SourceAttribution
