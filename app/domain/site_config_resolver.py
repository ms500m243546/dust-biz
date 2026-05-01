"""Site config resolution rule.

Encapsulates R13 mitigation: site_configurations is the authoritative
source for thresholds and automation level; `mines.default_*` is
fallback only when no site_config exists for a mine. When neither is
present the schema defaults from `app/schemas/site_config.py` apply.

Why a separate function: this rule is consulted by S11 (optimization
engine), S13 (approval / automation level gating), and the dashboard.
Pulling it out of those callers avoids three slightly-different
implementations drifting apart.
"""

from __future__ import annotations

from typing import Any, Literal, cast

from app.schemas.mine import AutomationLevel
from app.schemas.site_config import (
    DEFAULT_PM10_THRESHOLDS,
    DEFAULT_PM25_THRESHOLDS,
    OptimizationWeightsSchema,
    SiteConfigSchema,
)
from app.storage.models import Mine, SiteConfiguration

ResolvedSource = Literal["site_config", "mine_defaults", "schema_defaults"]

_VALID_LEVELS: set[AutomationLevel] = {"L0", "L1", "L2", "L3", "L4"}


def _coerce_automation_level(raw: str | None) -> AutomationLevel:
    if raw in _VALID_LEVELS:
        return cast(AutomationLevel, raw)
    return "L1"


def resolve(
    mine_id: str,
    site_config: SiteConfiguration | None,
    mine: Mine | None,
) -> tuple[SiteConfigSchema, ResolvedSource]:
    """Return the effective site config for a mine, plus its source.

    - If `site_config` is provided: use it verbatim.
    - Else if `mine` is provided: use mine defaults to fill the
      automation level + thresholds; everything else falls back to
      schema defaults.
    - Else: full schema defaults (caller likely should error, but the
      resolver returns rather than raising so callers can decide).
    """
    if site_config is not None:
        return SiteConfigSchema.model_validate(site_config), "site_config"

    if mine is not None:
        defaults = mine.default_risk_thresholds or {}
        pm10 = _extract_thresholds(defaults, "pm10", DEFAULT_PM10_THRESHOLDS)
        pm25 = _extract_thresholds(defaults, "pm25", DEFAULT_PM25_THRESHOLDS)
        return (
            SiteConfigSchema(
                site_id=f"default-{mine.mine_id}",
                mine_id=mine.mine_id,
                automation_level=_coerce_automation_level(mine.default_automation_level),
                pm10_thresholds=pm10,
                pm25_thresholds=pm25,
            ),
            "mine_defaults",
        )

    return (
        SiteConfigSchema(
            site_id=f"default-{mine_id}",
            mine_id=mine_id,
            optimization_weights=OptimizationWeightsSchema(),
        ),
        "schema_defaults",
    )


class MissingSiteConfigError(RuntimeError):
    """Raised when a caller demands an authoritative site config but none exists.

    S3's documented failure mode (subsystem-contracts.md, S3) is "fail
    loudly" rather than fabricate defaults. Read endpoints can use the
    permissive `resolve(...)` directly; automation-impacting consumers
    (S4 mine-state, S11 optimization, S13 approval gating) call
    `require_resolved(...)` so a missing config surfaces as an error
    instead of silently degrading to schema defaults.
    """


def require_resolved(
    mine_id: str,
    site_config: SiteConfiguration | None,
    mine: Mine | None,
) -> SiteConfigSchema:
    """Resolve, but raise on `schema_defaults`.

    Closes D-R2: any code path that drives operational behavior must
    fail loudly when no site_config and no mine row exist for
    `mine_id`. `mine_defaults` is still acceptable - the operator
    registered the mine, just hasn't tuned site config yet.
    """
    resolved, source = resolve(mine_id=mine_id, site_config=site_config, mine=mine)
    if source == "schema_defaults":
        raise MissingSiteConfigError(
            f"no site_configuration and no mine row exists for mine_id={mine_id!r}; "
            "register the mine and (optionally) a site_configuration before "
            "calling code that requires authoritative thresholds"
        )
    return resolved


def _extract_thresholds(
    raw: dict[str, Any], key: str, fallback: dict[str, float]
) -> dict[str, float]:
    value = raw.get(key)
    if isinstance(value, dict):
        # Filter to numeric values only; preserves any operator-defined
        # keys (warning / breach / custom_alert / ...).
        numeric: dict[str, float] = {}
        for k, v in value.items():
            if isinstance(v, int | float) and not isinstance(v, bool):
                numeric[str(k)] = float(v)
        if numeric:
            return numeric
    return dict(fallback)
