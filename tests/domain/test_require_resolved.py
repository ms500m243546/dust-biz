import pytest

from app.domain.site_config_resolver import (
    MissingSiteConfigError,
    require_resolved,
)
from app.storage.models import Mine, SiteConfiguration


def test_require_resolved_accepts_site_config() -> None:
    cfg = SiteConfiguration(
        site_id="m1-main",
        mine_id="m1",
        automation_level="L1",
        pm10_thresholds={"warning": 100.0, "breach": 150.0},
        pm25_thresholds={"warning": 25.0, "breach": 35.0},
        extreme_breach_threshold=0.85,
        low_confidence_threshold=0.5,
        optimization_weights={"w_breach": 1.0},
    )
    out = require_resolved(mine_id="m1", site_config=cfg, mine=None)
    assert out.site_id == "m1-main"


def test_require_resolved_accepts_mine_defaults() -> None:
    mine = Mine(mine_id="m1", name="Demo", default_automation_level="L1")
    out = require_resolved(mine_id="m1", site_config=None, mine=mine)
    assert out.mine_id == "m1"


def test_require_resolved_raises_on_schema_defaults() -> None:
    with pytest.raises(MissingSiteConfigError):
        require_resolved(mine_id="ghost", site_config=None, mine=None)
