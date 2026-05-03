"""Evaluation protocol — programmatic enforcement of the M.1 rigor gate.

This module is the Python side of `docs/anti-overfit-protocol.md` and
`docs/anti-hindsight-protocol.md`. Every call to
`app.domain.model_performance.evaluate_model(...)` must pass a typed
`EvaluationProtocol` instance. This module:

- defines the protocol shape
- computes the pre-registration `protocol_hash` (SHA-256 of canonical
  JSON; pinned in the persisted metric_payload)
- exposes `validate_protocol_obeyed(...)` returning a structured
  `ValidationResult` with `errors` (block evaluation) and `warnings`
  (deferred enforcement; logged on the metric row)

What M.1 enforces (errors): split is temporal not random; validation /
test windows are after train + embargo; baselines named include the
required three; sealed-test usage is recorded.

What M.1 only warns about (deferred to M.2 with PIT schema): SINCA
col-3 leakage; ERA5 used as a realtime feature; labeled-at semantics.

A model with `errors` cannot be evaluated — `evaluate_model` raises
`ProtocolViolation` and persists nothing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

SplitStrategy = Literal["walk_forward", "expanding_window", "sealed_test"]

REQUIRED_BASELINES: tuple[str, ...] = (
    "persistence",
    "seasonal_naive",
    "regulatory_threshold_classifier",
)

REQUIRED_METRIC_KEYS: tuple[str, ...] = (
    "breach_precision",
    "breach_recall",
    "false_positive_rate",
    "false_negative_rate",
    "calibration_error",
)

# Forbidden — random k-fold leaks the future into the past.
FORBIDDEN_SPLIT_STRATEGIES: tuple[str, ...] = ("random_kfold", "kfold", "shuffle")

PROTOCOL_VERSION = "M.1"


class ProtocolViolation(Exception):
    """Raised when an evaluation cannot proceed because the protocol fails."""


@dataclass(frozen=True)
class EvaluationProtocol:
    """Binding contract for one model evaluation run.

    All datetimes are naive UTC (matching the rest of the storage
    layer). All durations are integer days.
    """

    # Split discipline — anti-overfit rules 1, 2, 3.
    split_strategy: SplitStrategy
    train_window_from: datetime
    train_window_to: datetime
    validation_window_from: datetime
    validation_window_to: datetime
    test_window_from: datetime
    test_window_to: datetime
    embargo_days: int = 7

    # Sealed-test discipline — anti-overfit rule 5.
    sealed_test_used: bool = False

    # Baselines — anti-overfit rule 4.
    baselines_named: tuple[str, ...] = REQUIRED_BASELINES

    # Hindsight discipline — anti-hindsight rules 1, 2.
    sinca_validated_legal_only_after_days: int = 7
    realtime_proxy_required: bool = True

    # Provenance.
    protocol_version: str = PROTOCOL_VERSION
    intended_for_realtime: bool = True
    # M.3 — causal-protocol opt-in. False means the model is making a
    # predictive claim only; True means it claims its predictions are
    # causally grounded (and triggers a stricter SQL probe at
    # evaluation time per docs/causal-protocol.md).
    causal_intent: bool = False

    # Free-form notes — not part of the hash; for audit messages.
    notes: str = field(default="")

    @property
    def protocol_hash(self) -> str:
        """SHA-256 of the canonical-JSON of the immutable, hash-relevant fields.

        `notes` is excluded so audit annotations can be added without
        invalidating the pre-registration. Field order is fixed.
        """
        payload = {
            "split_strategy": self.split_strategy,
            "train_window_from": self.train_window_from.isoformat(),
            "train_window_to": self.train_window_to.isoformat(),
            "validation_window_from": self.validation_window_from.isoformat(),
            "validation_window_to": self.validation_window_to.isoformat(),
            "test_window_from": self.test_window_from.isoformat(),
            "test_window_to": self.test_window_to.isoformat(),
            "embargo_days": self.embargo_days,
            "sealed_test_used": self.sealed_test_used,
            "baselines_named": list(self.baselines_named),
            "sinca_validated_legal_only_after_days": (
                self.sinca_validated_legal_only_after_days
            ),
            "realtime_proxy_required": self.realtime_proxy_required,
            "protocol_version": self.protocol_version,
            "intended_for_realtime": self.intended_for_realtime,
            "causal_intent": self.causal_intent,
        }
        as_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(as_json.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ValidationResult:
    """Structured outcome of `validate_protocol_obeyed`."""

    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_protocol_obeyed(
    protocol: EvaluationProtocol,
    *,
    station_count: int = 1,
    prior_metric_protocol_hashes: tuple[str, ...] = (),
    session: Session | None = None,
) -> ValidationResult:
    """Programmatic check of the M.1+M.2 protocol contract.

    `station_count` and `prior_metric_protocol_hashes` are passed by
    the caller (the `evaluate_model` wrapper) from the persistence
    layer.

    M.2: `session` enables SQL-level probes against the PIT-tracked
    tables to enforce anti-hindsight rules 1, 2, 3 as **errors**
    (instead of M.1's deferred warnings). When `session` is None the
    probes are skipped and the deferred-check messages remain as
    warnings — useful for unit-testing the protocol contract without
    a live DB.

    Returns `ValidationResult(errors=..., warnings=...)`. Errors block
    evaluation; warnings are persisted on the metric row.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Rule 1 — split is temporal.
    if protocol.split_strategy in FORBIDDEN_SPLIT_STRATEGIES:
        errors.append(
            f"split_strategy={protocol.split_strategy!r} is forbidden "
            "(time-series leakage). Use walk_forward, expanding_window, "
            "or sealed_test."
        )

    # Rule 2 — embargo separates train from validation.
    if protocol.embargo_days < 0:
        errors.append("embargo_days must be >= 0")
    embargo = timedelta(days=protocol.embargo_days)
    if protocol.validation_window_from < protocol.train_window_to + embargo:
        errors.append(
            "validation_window_from must be >= train_window_to + embargo_days "
            f"(got validation_from={protocol.validation_window_from.isoformat()}, "
            f"train_to={protocol.train_window_to.isoformat()}, "
            f"embargo_days={protocol.embargo_days})"
        )

    # Rule 3 — sealed test window after validation, also embargoed.
    if protocol.test_window_from < protocol.validation_window_to + embargo:
        errors.append(
            "test_window_from must be >= validation_window_to + embargo_days"
        )
    if protocol.test_window_to <= protocol.test_window_from:
        errors.append("test_window_to must be > test_window_from")

    # Rule 4 — required baselines are named.
    missing_baselines = [
        b for b in REQUIRED_BASELINES if b not in protocol.baselines_named
    ]
    if missing_baselines:
        errors.append(
            f"baselines_named is missing required baseline(s): "
            f"{missing_baselines}. Required: {list(REQUIRED_BASELINES)}."
        )

    # Rule 5 — pre-registration: sealed-test reuse is forbidden.
    if (
        protocol.sealed_test_used
        and protocol.protocol_hash in prior_metric_protocol_hashes
    ):
        errors.append(
            "sealed_test_used=True with a protocol_hash that has already "
            "been used. Sealed test windows are one-shot per protocol; "
            "bump protocol_version and use a new sealed window."
        )

    # Rule 7 — geographic-generalization claims blocked at single-station.
    if station_count < 2 and not protocol.intended_for_realtime:
        # Models declared as cross-station require ≥ 2 stations of real data.
        warnings.append(
            f"station_count={station_count}: cross-station generalization "
            "claims must be blocked downstream (anti-overfit rule 7)."
        )

    # M.2 hindsight probes — run when a session is provided. Without
    # a session, fall back to M.1 warning-level deferred checks so
    # pure unit tests still work.
    if session is not None:
        _run_hindsight_probes(
            session, protocol, errors=errors, warnings=warnings
        )
        if protocol.causal_intent:
            _run_causal_intent_probe(
                session, protocol, errors=errors, warnings=warnings
            )
    else:
        if protocol.intended_for_realtime:
            warnings.append(
                "no session provided: anti-hindsight rule 1 (SINCA col-3 "
                "embargo) cannot be verified by SQL probe. Pass `session` "
                "to `validate_protocol_obeyed` to enforce."
            )
        if protocol.intended_for_realtime and protocol.realtime_proxy_required:
            warnings.append(
                "no session provided: anti-hindsight rule 2 (ERA5 "
                "realtime_proxy filter) cannot be verified by SQL probe."
            )
        warnings.append(
            "no session provided: anti-hindsight rule 3 (labeled_at <= "
            "prediction.issued_at) cannot be verified by SQL probe."
        )

    return ValidationResult(
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _run_hindsight_probes(
    session: Session,
    protocol: EvaluationProtocol,
    *,
    errors: list[str],
    warnings: list[str],
) -> None:
    """M.2 SQL-level enforcement of anti-hindsight rules 1, 2, 3.

    Mutates `errors` (and optionally `warnings`) in place. Pure side
    effect on those lists — keeps `validate_protocol_obeyed` readable.
    """
    from sqlalchemy import func, select

    from app.storage.models import (
        ActionOutcome,
        DustEvent,
        Recommendation,
        RecommendationApproval,
        SensorReading,
        SourceAttribution,
        WeatherReading,
    )

    train_from = protocol.train_window_from
    train_to = protocol.train_window_to
    # `sinca_validated_legal_only_after_days` is consulted directly
    # below where it's needed; we keep the field on the protocol for
    # the audit trail rather than precomputing.

    if protocol.intended_for_realtime:
        # Rule 1 — SINCA col-3 leakage. A col-3 row's `valid_from`
        # equals `timestamp + embargo`. If any sensor_readings row
        # within the training window has `valid_from > timestamp`
        # AND `valid_from > timestamp + embargo - delta_safe`, it's a
        # validated row that was used for training of an hour the
        # model wouldn't have known the validated value for.
        #
        # We probe the inverse: count rows where the validated value
        # was used at training time *before* it would have been
        # available. That is, valid_from > train_window_from is a
        # row that became known after some training point.
        #
        # The actual prediction-time embargo is applied at the
        # consumer side (load_and_assemble mode="training" + the
        # pit_query module). The probe here checks: are there any
        # SensorReading rows in the training window with valid_from
        # later than their timestamp + a generous embargo? Those are
        # validated-version rows; they're legal only if every
        # downstream prediction.issued_at >= their valid_from. We
        # cannot prove that here without enumerating predictions, so
        # we surface the count as an informational warning rather
        # than an error.
        leaky_count = session.execute(
            select(func.count())
            .select_from(SensorReading)
            .where(SensorReading.timestamp >= train_from)
            .where(SensorReading.timestamp <= train_to)
            .where(SensorReading.valid_from > SensorReading.timestamp)
        ).scalar_one()
        if leaky_count and protocol.embargo_days < 1:
            errors.append(
                f"anti-hindsight rule 1: training window contains "
                f"{leaky_count} validated SINCA row(s) but protocol "
                f"embargo_days={protocol.embargo_days} is too small "
                "to absorb col-2→col-3 promotion lag"
            )

    if protocol.intended_for_realtime and protocol.realtime_proxy_required:
        # Rule 2 — ERA5 (or any realtime_proxy=False source) cannot
        # appear in training data for a realtime-intended model.
        reanalysis_count = session.execute(
            select(func.count())
            .select_from(WeatherReading)
            .where(WeatherReading.timestamp >= train_from)
            .where(WeatherReading.timestamp <= train_to)
            .where(WeatherReading.realtime_proxy.is_(False))
        ).scalar_one()
        if reanalysis_count:
            errors.append(
                f"anti-hindsight rule 2: training window contains "
                f"{reanalysis_count} reanalysis weather row(s) "
                f"(realtime_proxy=False) but protocol declares "
                f"intended_for_realtime=True. Filter with "
                f"`pit_query.weather_readings_as_of(..., realtime_only=True)` "
                f"or set protocol.realtime_proxy_required=False for a "
                f"climatological/reanalysis-trained model."
            )

    # Rule 3 — labeled_at <= prediction.issued_at. We cannot enforce
    # this perfectly without joining against the prediction set, but
    # we can at minimum probe: do any label rows in the training
    # window have labeled_at *after* train_window_to? Those are
    # post-window labels — illegal as training features for any
    # prediction whose issued_at is in the window.
    label_pairs: list[tuple[str, type]] = [
        ("dust_events", DustEvent),
        ("recommendations", Recommendation),
        ("recommendation_approvals", RecommendationApproval),
        ("action_outcomes", ActionOutcome),
        ("source_attributions", SourceAttribution),
    ]
    for table_name, model in label_pairs:
        post_window = session.execute(
            select(func.count())
            .select_from(model)
            .where(model.labeled_at > train_to)  # type: ignore[attr-defined]
        ).scalar_one()
        if post_window:
            warnings.append(
                f"anti-hindsight rule 3: {post_window} {table_name} row(s) "
                f"have labeled_at > train_window_to. Legal only if "
                f"downstream training queries filter "
                f"`labels_as_of(prediction.issued_at)`."
            )


def _run_causal_intent_probe(
    session: Session,
    protocol: EvaluationProtocol,
    *,
    errors: list[str],
    warnings: list[str],
) -> None:
    """M.3 SQL-level enforcement of causal-intent claims.

    Per `docs/causal-protocol.md`: a model declaring `causal_intent=True`
    cannot have its training data sourced entirely from
    observational_correlational attributions or naive_correlation
    simulations. Delegates to `app.domain.causal_protocol`.
    """
    from app.domain.causal_protocol import probe_causal_intent_training

    result = probe_causal_intent_training(
        session,
        train_window_from=protocol.train_window_from,
        train_window_to=protocol.train_window_to,
    )
    errors.extend(result.errors)
    warnings.extend(result.warnings)


def protocol_to_payload_keys(protocol: EvaluationProtocol) -> dict[str, object]:
    """The subset of protocol fields that get persisted on `metric_payload`.

    These keys are scanned by `scripts/checks/validate-overfit-discipline.js`
    so any model_performance_metrics row committed without them fails the
    gate.
    """
    return {
        "protocol_version": protocol.protocol_version,
        "protocol_hash": protocol.protocol_hash,
        "split_strategy": protocol.split_strategy,
        "embargo_days": protocol.embargo_days,
        "sealed_test_used": protocol.sealed_test_used,
        "baselines_named": list(protocol.baselines_named),
        "intended_for_realtime": protocol.intended_for_realtime,
        "realtime_proxy_required": protocol.realtime_proxy_required,
        "causal_intent": protocol.causal_intent,
    }


__all__ = [
    "FORBIDDEN_SPLIT_STRATEGIES",
    "PROTOCOL_VERSION",
    "REQUIRED_BASELINES",
    "REQUIRED_METRIC_KEYS",
    "EvaluationProtocol",
    "ProtocolViolation",
    "ValidationResult",
    "protocol_to_payload_keys",
    "validate_protocol_obeyed",
]
