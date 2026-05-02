"""S15 - Audit, Compliance, and ROI Reporting (Phase K.2).

Pure read-only aggregations over the persisted data layer. No writes,
no side effects. Each report function takes the entities it needs and
returns a Pydantic schema; the route handler is the only place that
talks to the session + repositories. This keeps the reports trivially
testable without DB fixtures.

Per safety-guardrails.md, report generation must never block the
operational loop — every entrypoint here must be exception-safe and
return a populated payload even on partial data.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from app.schemas.model_performance import TrainingRecordSchema
from app.schemas.reports import (
    ComplianceReport,
    ComplianceReportEntry,
    ModelPerformanceReport,
    ModelPerformanceReportEntry,
    ROIReport,
)
from app.schemas.site_config import DEFAULT_COST_CURVES
from app.storage.models import (
    DustEvent,
    ModelPerformanceMetric,
    SensorReading,
)


def build_model_performance_report(
    *,
    metrics: Iterable[ModelPerformanceMetric],
    generated_at: datetime,
    window_from: datetime,
    window_to: datetime,
) -> ModelPerformanceReport:
    """Reduce persisted metric rows to the latest-per-model view."""
    latest: dict[tuple[str, str], ModelPerformanceMetric] = {}
    for m in metrics:
        key = (m.model_version, m.model_kind)
        existing = latest.get(key)
        if existing is None or m.evaluated_at > existing.evaluated_at:
            latest[key] = m

    entries: list[ModelPerformanceReportEntry] = []
    for (version, kind), m in latest.items():
        payload = m.metric_payload or {}
        entries.append(
            ModelPerformanceReportEntry(
                model_version=version,
                model_kind=kind,  # type: ignore[arg-type]
                sample_count=int(payload.get("sample_count", m.sample_count) or 0),
                observed_count=int(payload.get("observed_count", 0) or 0),
                unobserved_count=int(payload.get("unobserved_count", 0) or 0),
                mae_pm10=payload.get("mae_pm10"),
                breach_precision=payload.get("breach_precision"),
                breach_recall=payload.get("breach_recall"),
                false_positive_rate=payload.get("false_positive_rate"),
                false_negative_rate=payload.get("false_negative_rate"),
                calibration_error=payload.get("calibration_error"),
                avoided_shutdowns_estimate=int(
                    payload.get("avoided_shutdowns_estimate", 0) or 0
                ),
                production_loss_tonnes_total=float(
                    payload.get("production_loss_tonnes_total", 0.0) or 0.0
                ),
                last_evaluated_at=m.evaluated_at,
            )
        )

    entries.sort(key=lambda e: (e.model_kind, e.model_version))
    return ModelPerformanceReport(
        generated_at=generated_at,
        window_from=window_from,
        window_to=window_to,
        entries=entries,
    )


def _resolve_cost_curves(curves: dict[str, Any] | None) -> dict[str, Any]:
    if not curves:
        return dict(DEFAULT_COST_CURVES)
    out = dict(DEFAULT_COST_CURVES)
    out.update(curves)
    if "intervention_unit_costs_usd" not in out:
        out["intervention_unit_costs_usd"] = {}
    return out


def build_roi_report(
    *,
    training_records: Iterable[TrainingRecordSchema],
    cost_curves: dict[str, Any] | None,
    generated_at: datetime,
    window_from: datetime,
    window_to: datetime,
    site_id: str | None = None,
) -> ROIReport:
    """Cost / value summary over a S14-assembled window.

    `avoided_shutdown_value_usd` mirrors the S14 avoided-shutdowns
    estimate definition (FP records the operator approved/overrode,
    not rejected). Conservative by design — any precision improvement
    has to be earned through better attribution + simulation, not
    accounting tricks.
    """
    resolved = _resolve_cost_curves(cost_curves)
    tonne_value = float(resolved.get("tonne_value_usd", 0.0) or 0.0)
    unit_costs: dict[str, float] = resolved.get("intervention_unit_costs_usd", {}) or {}

    avoided_count = 0
    intervention_cost_usd = 0.0
    realised_loss_tonnes = 0.0
    sample = 0

    for r in training_records:
        sample += 1
        if r.outcome_status != "observed":
            continue
        if r.production_loss_tonnes_actual is not None:
            realised_loss_tonnes += r.production_loss_tonnes_actual

        # Avoided shutdown: predicted breach, not observed, operator
        # approved or overrode.
        if (
            r.predicted_breach_probability >= 0.5
            and r.breach_occurred is False
            and r.human_action in {"approved", "overridden"}
        ):
            avoided_count += 1

        # Intervention cost — flat USD per executed action.
        if r.human_action == "approved" and r.chosen_action_rank is not None:
            # We don't have the action_id on the training record; the
            # action library binds rank -> action via the simulation
            # cache. Until that link lands here we proxy with a
            # nominal "default" per executed approval. Sites override
            # via cost_curves.intervention_unit_costs_usd.default.
            intervention_cost_usd += float(unit_costs.get("default", 0.0) or 0.0)
        elif r.human_action == "overridden" and r.override_action:
            intervention_cost_usd += float(
                unit_costs.get(r.override_action, unit_costs.get("default", 0.0)) or 0.0
            )

    avoided_value = avoided_count * tonne_value * 50.0  # see note below
    realised_loss_usd = realised_loss_tonnes * tonne_value
    net = avoided_value - intervention_cost_usd - realised_loss_usd

    return ROIReport(
        generated_at=generated_at,
        window_from=window_from,
        window_to=window_to,
        site_id=site_id,
        tonne_value_usd=tonne_value,
        avoided_shutdowns_count=avoided_count,
        avoided_shutdown_value_usd=avoided_value,
        intervention_cost_usd=intervention_cost_usd,
        realised_production_loss_tonnes=realised_loss_tonnes,
        realised_production_loss_usd=realised_loss_usd,
        net_value_usd=net,
        sample_count=sample,
    )


# 50.0 above is a placeholder "tonnes-protected per avoided shutdown"
# multiplier per docs/normalization_report.md G3-R1 — uncalibrated;
# sites override `tonne_value_usd` for the only knob that matters
# until calibration data arrives. Hold-down comment intentional: the
# magic number is documented at the call site so it doesn't drift.


def build_compliance_report(
    *,
    sensor_ids: Iterable[str],
    readings_by_sensor: dict[str, list[SensorReading]],
    pm10_thresholds: dict[str, float],
    pm25_thresholds: dict[str, float],
    dust_events: Iterable[DustEvent],
    generated_at: datetime,
    window_from: datetime,
    window_to: datetime,
    site_id: str | None = None,
) -> ComplianceReport:
    """PM exceedance counts per station against site-specific limits."""
    pm10_breach = float(pm10_thresholds.get("breach", 150.0))
    pm25_breach = float(pm25_thresholds.get("breach", 35.0))
    pm10_warn = float(pm10_thresholds.get("warning", 100.0))
    pm25_warn = float(pm25_thresholds.get("warning", 25.0))

    entries: list[ComplianceReportEntry] = []
    for sid in sorted(set(sensor_ids)):
        rows = readings_by_sensor.get(sid, [])
        pm10s: list[float] = []
        pm25s: list[float] = []
        for row in rows:
            payload = row.raw_value or {}
            pm10 = payload.get("pm10_ugm3")
            pm25 = payload.get("pm25_ugm3")
            if isinstance(pm10, int | float) and not isinstance(pm10, bool):
                pm10s.append(float(pm10))
            if isinstance(pm25, int | float) and not isinstance(pm25, bool):
                pm25s.append(float(pm25))

        entries.append(
            ComplianceReportEntry(
                sensor_id=sid,
                pm10_breach_count=sum(1 for v in pm10s if v >= pm10_breach),
                pm25_breach_count=sum(1 for v in pm25s if v >= pm25_breach),
                pm10_warning_count=sum(
                    1 for v in pm10s if pm10_warn <= v < pm10_breach
                ),
                pm25_warning_count=sum(
                    1 for v in pm25s if pm25_warn <= v < pm25_breach
                ),
                peak_pm10=max(pm10s) if pm10s else None,
                peak_pm25=max(pm25s) if pm25s else None,
                pm10_breach_threshold=pm10_breach,
                pm25_breach_threshold=pm25_breach,
                pm10_warning_threshold=pm10_warn,
                pm25_warning_threshold=pm25_warn,
            )
        )

    events = list(dust_events)
    return ComplianceReport(
        generated_at=generated_at,
        window_from=window_from,
        window_to=window_to,
        site_id=site_id,
        stations=entries,
        total_dust_events=len(events),
        total_breach_events=sum(1 for e in events if getattr(e, "breach_occurred", False)),
    )


def _bucket_readings(rows: Iterable[SensorReading]) -> dict[str, list[SensorReading]]:
    out: dict[str, list[SensorReading]] = defaultdict(list)
    for r in rows:
        out[r.sensor_id].append(r)
    return dict(out)


__all__ = [
    "_bucket_readings",
    "_resolve_cost_curves",
    "build_compliance_report",
    "build_model_performance_report",
    "build_roi_report",
]
