from sqlalchemy.orm import Session

from app.storage.repositories.interventions import InterventionOptionRepository


def _upsert(repo: InterventionOptionRepository, iid: str, **overrides: object) -> None:
    base: dict[str, object] = {
        "intervention_id": iid,
        "name": iid,
        "description": "desc",
        "risk_class": "low",
        "requires_human_approval": False,
        "automation_eligible_levels": ["L3"],
        "estimated_time_to_effect_minutes": 0,
        "allowed_zone_types": ["haul_road"],
    }
    base.update(overrides)
    repo.upsert(**base)  # type: ignore[arg-type]


def test_upsert_inserts_then_updates(session: Session) -> None:
    repo = InterventionOptionRepository(session)
    _upsert(repo, "reduce_speed")
    _upsert(repo, "reduce_speed", description="updated", risk_class="medium")
    row = repo.get("reduce_speed")
    assert row is not None
    assert row.description == "updated"
    assert row.risk_class == "medium"


def test_list_all_returns_sorted_ids(session: Session) -> None:
    repo = InterventionOptionRepository(session)
    _upsert(repo, "water_road")
    _upsert(repo, "raise_alert")
    _upsert(repo, "reduce_speed")
    assert [r.intervention_id for r in repo.list_all()] == [
        "raise_alert",
        "reduce_speed",
        "water_road",
    ]


def test_known_ids_returns_set(session: Session) -> None:
    repo = InterventionOptionRepository(session)
    _upsert(repo, "raise_alert")
    _upsert(repo, "reduce_speed")
    assert repo.known_ids() == {"raise_alert", "reduce_speed"}


def test_get_returns_none_for_unknown(session: Session) -> None:
    repo = InterventionOptionRepository(session)
    assert repo.get("nope") is None
