from sqlalchemy.orm import Session

from app.domain.site_config_resolver import resolve
from app.storage.models import Mine, SiteConfiguration


def test_resolver_uses_site_config_when_present(session: Session) -> None:
    cfg = SiteConfiguration(
        site_id="m1-main",
        mine_id="m1",
        automation_level="L2",
        pm10_thresholds={"warning": 80.0, "breach": 130.0},
        pm25_thresholds={"warning": 20.0, "breach": 30.0},
        extreme_breach_threshold=0.9,
        low_confidence_threshold=0.6,
        optimization_weights={"w_breach": 2.0, "w_production": 1.0},
    )
    resolved, source = resolve(mine_id="m1", site_config=cfg, mine=None)
    assert source == "site_config"
    assert resolved.automation_level == "L2"
    assert resolved.pm10_thresholds["warning"] == 80.0


def test_resolver_falls_back_to_mine_defaults() -> None:
    mine = Mine(
        mine_id="m1",
        name="Demo",
        default_automation_level="L0",
        default_risk_thresholds={
            "pm10": {"warning": 90.0, "breach": 140.0},
        },
    )
    resolved, source = resolve(mine_id="m1", site_config=None, mine=mine)
    assert source == "mine_defaults"
    assert resolved.automation_level == "L0"
    assert resolved.pm10_thresholds["warning"] == 90.0
    # pm25 not in mine defaults -> uses schema defaults
    assert resolved.pm25_thresholds["warning"] == 25.0


def test_resolver_falls_back_to_schema_defaults() -> None:
    resolved, source = resolve(mine_id="m1", site_config=None, mine=None)
    assert source == "schema_defaults"
    assert resolved.automation_level == "L1"
    assert resolved.pm10_thresholds["warning"] == 100.0
    assert resolved.pm25_thresholds["warning"] == 25.0
    assert resolved.optimization_weights.w_breach == 1.0


def test_resolver_invalid_mine_automation_level_falls_back_to_l1() -> None:
    mine = Mine(mine_id="m1", name="Demo", default_automation_level="ZZZ")
    resolved, _ = resolve(mine_id="m1", site_config=None, mine=mine)
    assert resolved.automation_level == "L1"
