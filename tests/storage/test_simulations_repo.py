from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.storage.models import InterventionSimulation
from app.storage.repositories.simulations import InterventionSimulationRepository

T0 = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def _make(sid: str, t: datetime, zone: str = "haul_c") -> InterventionSimulation:
    return InterventionSimulation(
        simulation_id=sid,
        requested_at=t.replace(tzinfo=None),
        intervention_id="reduce_speed",
        target_zone_id=zone,
        scenario="Reduce truck speed on " + zone,
        predicted_pm10_reduction=20.0,
        predicted_pm25_reduction=8.0,
        breach_probability_before=0.74,
        breach_probability_after=0.59,
        time_to_effect_minutes=10,
        production_loss_tonnes=280.0,
        cycle_time_increase_percent=8.5,
        production_impact="medium",
        confidence=0.7,
        model_version="intervention_impact_heuristic_v0.1.0",
        cost_model_version="production_cost_heuristic_v0.1.0",
        source="heuristic",
        main_uncertainty=None,
    )


def test_add_and_get(session: Session) -> None:
    repo = InterventionSimulationRepository(session)
    repo.add(_make("SIM-20260501-0001", T0))
    assert repo.get("SIM-20260501-0001") is not None


def test_next_simulation_id_resets_per_day(session: Session) -> None:
    repo = InterventionSimulationRepository(session)
    repo.add(_make("SIM-20260501-0001", T0))
    assert repo.next_simulation_id(T0.date()) == "SIM-20260501-0002"
    assert repo.next_simulation_id((T0 + timedelta(days=1)).date()) == "SIM-20260502-0001"


def test_get_recent_filters_by_zone_and_window(session: Session) -> None:
    repo = InterventionSimulationRepository(session)
    repo.add(_make("SIM-20260501-0001", T0 - timedelta(hours=2), zone="haul_c"))
    repo.add(_make("SIM-20260501-0002", T0 - timedelta(minutes=10), zone="haul_c"))
    repo.add(_make("SIM-20260501-0003", T0 - timedelta(minutes=5), zone="haul_d"))

    rows = repo.get_recent(
        since=(T0 - timedelta(hours=1)).replace(tzinfo=None),
        target_zone_id="haul_c",
    )
    assert {r.simulation_id for r in rows} == {"SIM-20260501-0002"}
