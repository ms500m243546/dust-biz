"""DustPrediction ORM (Phase E).

Per docs/data-contracts.md `dust_predictions`. Append-only audit
table: every issued forecast lands here with full input lineage
(input_record_ids) so the model output can be reconstructed.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.models.base import Base


class DustPrediction(Base):
    __tablename__ = "dust_predictions"

    prediction_id: Mapped[str] = mapped_column(String, primary_key=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    target_kind: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    forecast_horizon: Mapped[str] = mapped_column(String, nullable=False)
    predicted_pm10: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_pm25: Mapped[float] = mapped_column(Float, nullable=False)
    breach_probability: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    main_risk_window: Mapped[str] = mapped_column(String, nullable=False)
    main_uncertainty: Mapped[str] = mapped_column(String, nullable=False)
    model_version: Mapped[str] = mapped_column(String, nullable=False, index=True)
    feature_pipeline_version: Mapped[str] = mapped_column(String, nullable=False)
    input_data_quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    data_quality_warnings: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    input_record_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
