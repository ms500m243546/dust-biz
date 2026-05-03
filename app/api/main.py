"""API entry point - FastAPI app factory and router wiring.

Auth posture (Phase K.3 hardening):
- `health` and `meta` are unauthenticated by design (orchestration probes,
  external readiness checks).
- `auth` is unauthenticated by design (login + token issuance).
- Every other router is gated by `current_user` at the `include_router`
  level via `dependencies=[Depends(current_user)]`. Mutating endpoints
  layer additional `require_role(...)` checks at the route level. This
  closes I1-R1.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app as app_pkg
from app.api import API_PREFIX, API_VERSION
from app.api.dependencies.auth import current_user
from app.api.routes import (
    approvals,
    attributions,
    audit,
    auth,
    data_quality,
    drift,
    drift_retrain,
    dust_events,
    equipment_activity,
    forecasts,
    haul_road_segments,
    health,
    interventions,
    meta,
    mine_state,
    model_performance,
    outcomes,
    recommendations,
    reports,
    sensor_readings,
    shadow_mode,
    simulations,
    site_config,
    training_data,
    weather_readings,
    zones,
)
from app.config.settings import get_settings
from app.storage.database import get_engine
from app.storage.models import Base

__all__ = ["API_PREFIX", "API_VERSION", "app", "create_app"]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown hooks.

    K.3: SQLite dev path keeps `Base.metadata.create_all` for
    convenience; production Postgres deploys run alembic migrations
    out-of-band. The K.3 scheduler is opt-in via
    `settings.scheduler_enabled`.
    """
    settings = get_settings()
    Base.metadata.create_all(get_engine())
    # Phase P.3 — promote the trained GBM forecast model to `current`
    # if its latest M.4 metric_payload row passes the criteria. Tolerant:
    # leaves the heuristic baseline current if anything goes wrong.
    from app.domain.dust_forecast_promotion import maybe_promote_gbm

    maybe_promote_gbm()
    # Phase R.2 — same pattern for the AP-42 intervention model. Uses
    # the sanity-band fallback when ActionOutcome rows are too thin
    # for empirical calibration (the typical case until partnership
    # data lands).
    from app.domain.intervention_promotion import maybe_promote_ap42

    maybe_promote_ap42()
    # Phase S.2 — same pattern for the logreg attribution model.
    from app.domain.attribution_promotion import maybe_promote_logreg

    maybe_promote_logreg()
    # Phase U.2 — same pattern for the cycle-time production-cost
    # model. Promotes via canonical-probe sanity band until real
    # ActionOutcome.production_loss_tonnes_actual data is available
    # for empirical calibration.
    from app.domain.cost_promotion import maybe_promote_cycle_time_cost

    maybe_promote_cycle_time_cost()
    scheduler = None
    if settings.scheduler_enabled:
        from app.domain.scheduler import get_default_scheduler

        scheduler = get_default_scheduler()
        scheduler.start()
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    fastapi_app = FastAPI(
        title="DustOps AI",
        version=app_pkg.__version__,
        description=(
            "Production-preserving dust-risk optimization platform for mines. "
            "See docs/system-map.md for subsystem boundaries."
        ),
        lifespan=lifespan,
    )

    if settings.cors_allow_origins:
        fastapi_app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_allow_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Open by design: health + meta + auth.
    fastapi_app.include_router(health.router, prefix=API_PREFIX, tags=["meta"])
    fastapi_app.include_router(meta.router, prefix=API_PREFIX, tags=["meta"])
    fastapi_app.include_router(auth.router, prefix=API_PREFIX)

    # All other routers require an authenticated user. Mutating
    # endpoints layer require_role(...) at the route level.
    auth_dep = [Depends(current_user)]
    fastapi_app.include_router(sensor_readings.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(weather_readings.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(equipment_activity.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(data_quality.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(site_config.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(zones.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(haul_road_segments.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(mine_state.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(forecasts.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(dust_events.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(attributions.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(interventions.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(simulations.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(recommendations.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(approvals.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(outcomes.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(training_data.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(model_performance.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(drift.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(
        drift_retrain.router, prefix=API_PREFIX, dependencies=auth_dep
    )
    fastapi_app.include_router(reports.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(shadow_mode.router, prefix=API_PREFIX, dependencies=auth_dep)
    fastapi_app.include_router(audit.router, prefix=API_PREFIX, dependencies=auth_dep)

    return fastapi_app


app = create_app()
