"""InterventionSimulation ORM (Phase G, S9 + S10 joined).

Per docs/data-contracts.md `intervention_simulations`. Append-only:
each simulate call lands a new row so the recommendation engine
(Phase H) can compare candidates against history and Phase K can
join predicted vs actual outcomes.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.models.base import Base


class InterventionSimulation(Base):
    __tablename__ = "intervention_simulations"

    simulation_id: Mapped[str] = mapped_column(String, primary_key=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    intervention_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    target_zone_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    scenario: Mapped[str] = mapped_column(String, nullable=False)

    predicted_pm10_reduction: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_pm25_reduction: Mapped[float | None] = mapped_column(Float, nullable=True)
    breach_probability_before: Mapped[float] = mapped_column(Float, nullable=False)
    breach_probability_after: Mapped[float] = mapped_column(Float, nullable=False)
    time_to_effect_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    production_loss_tonnes: Mapped[float] = mapped_column(Float, nullable=False)
    cycle_time_increase_percent: Mapped[float] = mapped_column(Float, nullable=False)
    production_impact: Mapped[str] = mapped_column(String, nullable=False)

    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String, nullable=False, index=True)
    cost_model_version: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    main_uncertainty: Mapped[str | None] = mapped_column(String, nullable=True)
    # M.3: causal-protocol rules. `simulation_method` names what
    # produced the predicted_pm10_reduction estimate. Realistic
    # default = `naive_correlation` (we have no RCT data). Confidence
    # is automatically capped at 0.7 for naive simulations by the
    # validator at write time. `counterfactual_assumption` is the
    # operator-readable disclosure of what world-model the simulator
    # assumed (e.g., "no-op baseline" — biased because operators
    # always react). `selection_bias_caveat` is True when the
    # production-cost portion of this row was calibrated only on
    # operator-acted interventions.
    simulation_method: Mapped[str] = mapped_column(
        String, nullable=False, default="naive_correlation", index=True
    )
    counterfactual_assumption: Mapped[str] = mapped_column(
        String, nullable=False, default=""
    )
    selection_bias_caveat: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
