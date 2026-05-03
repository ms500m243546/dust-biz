"""Phase M.1: evaluation-protocol contract tests.

Pure unit tests for `app.domain.evaluation_protocol` — no DB, no API.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.domain.evaluation_protocol import (
    PROTOCOL_VERSION,
    REQUIRED_BASELINES,
    EvaluationProtocol,
    protocol_to_payload_keys,
    validate_protocol_obeyed,
)


def _good_protocol(**overrides: object) -> EvaluationProtocol:
    """Helper: a minimal protocol that should pass `validate_protocol_obeyed`."""
    base = dict(
        split_strategy="walk_forward",
        train_window_from=datetime(2025, 1, 1),
        train_window_to=datetime(2025, 6, 1),
        validation_window_from=datetime(2025, 6, 8),  # train_to + 7d embargo
        validation_window_to=datetime(2025, 9, 1),
        test_window_from=datetime(2025, 9, 8),  # val_to + 7d embargo
        test_window_to=datetime(2026, 3, 1),
        embargo_days=7,
        sealed_test_used=False,
        baselines_named=REQUIRED_BASELINES,
        intended_for_realtime=True,
    )
    base.update(overrides)
    return EvaluationProtocol(**base)  # type: ignore[arg-type]


def test_good_protocol_has_no_errors() -> None:
    protocol = _good_protocol()
    result = validate_protocol_obeyed(protocol, station_count=1)
    assert result.errors == ()
    assert result.ok


def test_good_protocol_emits_m2_deferred_warnings() -> None:
    protocol = _good_protocol()
    result = validate_protocol_obeyed(protocol, station_count=1)
    # Three M.2-deferred checks: SINCA col-3, ERA5 realtime_proxy, labeled_at.
    assert any("SINCA col-3" in w for w in result.warnings)
    assert any("realtime_proxy" in w for w in result.warnings)
    assert any("labeled_at" in w for w in result.warnings)


def test_random_kfold_is_rejected() -> None:
    protocol = _good_protocol(split_strategy="random_kfold")
    result = validate_protocol_obeyed(protocol)
    assert any("random_kfold" in e for e in result.errors)
    assert not result.ok


def test_validation_window_inside_embargo_is_rejected() -> None:
    protocol = _good_protocol(
        train_window_to=datetime(2025, 6, 1),
        validation_window_from=datetime(2025, 6, 3),  # only 2 days, embargo=7
    )
    result = validate_protocol_obeyed(protocol)
    assert any("validation_window_from must be" in e for e in result.errors)


def test_test_window_inside_embargo_is_rejected() -> None:
    protocol = _good_protocol(
        validation_window_to=datetime(2025, 9, 1),
        test_window_from=datetime(2025, 9, 3),  # 2 days, embargo=7
    )
    result = validate_protocol_obeyed(protocol)
    assert any("test_window_from must be" in e for e in result.errors)


def test_missing_required_baseline_is_rejected() -> None:
    protocol = _good_protocol(
        baselines_named=("persistence",),  # missing seasonal_naive + threshold
    )
    result = validate_protocol_obeyed(protocol)
    assert any("missing required baseline" in e for e in result.errors)


def test_sealed_test_reuse_is_rejected() -> None:
    protocol = _good_protocol(sealed_test_used=True)
    result = validate_protocol_obeyed(
        protocol,
        prior_metric_protocol_hashes=(protocol.protocol_hash,),
    )
    assert any("already been used" in e for e in result.errors)


def test_sealed_test_first_use_is_allowed() -> None:
    protocol = _good_protocol(sealed_test_used=True)
    # No prior hashes -> first use of the sealed window.
    result = validate_protocol_obeyed(
        protocol,
        prior_metric_protocol_hashes=(),
    )
    assert all("already been used" not in e for e in result.errors)


def test_negative_embargo_is_rejected() -> None:
    protocol = _good_protocol(embargo_days=-1)
    result = validate_protocol_obeyed(protocol)
    assert any("embargo_days must be >= 0" in e for e in result.errors)


def test_protocol_hash_is_deterministic() -> None:
    p1 = _good_protocol()
    p2 = _good_protocol()
    assert p1.protocol_hash == p2.protocol_hash


def test_protocol_hash_changes_with_split_strategy() -> None:
    p1 = _good_protocol(split_strategy="walk_forward")
    p2 = _good_protocol(split_strategy="expanding_window")
    assert p1.protocol_hash != p2.protocol_hash


def test_protocol_hash_ignores_notes() -> None:
    p1 = _good_protocol()
    p2 = EvaluationProtocol(
        split_strategy=p1.split_strategy,
        train_window_from=p1.train_window_from,
        train_window_to=p1.train_window_to,
        validation_window_from=p1.validation_window_from,
        validation_window_to=p1.validation_window_to,
        test_window_from=p1.test_window_from,
        test_window_to=p1.test_window_to,
        embargo_days=p1.embargo_days,
        sealed_test_used=p1.sealed_test_used,
        baselines_named=p1.baselines_named,
        sinca_validated_legal_only_after_days=(
            p1.sinca_validated_legal_only_after_days
        ),
        realtime_proxy_required=p1.realtime_proxy_required,
        protocol_version=p1.protocol_version,
        intended_for_realtime=p1.intended_for_realtime,
        notes="audit annotation that should not invalidate the hash",
    )
    assert p1.protocol_hash == p2.protocol_hash


def test_protocol_to_payload_keys_includes_required_fields() -> None:
    protocol = _good_protocol()
    payload = protocol_to_payload_keys(protocol)
    assert payload["protocol_version"] == PROTOCOL_VERSION
    assert payload["protocol_hash"] == protocol.protocol_hash
    assert payload["split_strategy"] == "walk_forward"
    assert payload["sealed_test_used"] is False
    assert payload["baselines_named"] == list(REQUIRED_BASELINES)


def test_test_window_to_must_be_after_test_window_from() -> None:
    protocol = _good_protocol(
        test_window_from=datetime(2025, 9, 8),
        test_window_to=datetime(2025, 9, 8),  # not strictly greater
    )
    result = validate_protocol_obeyed(protocol)
    assert any("test_window_to must be > test_window_from" in e for e in result.errors)


@pytest.mark.parametrize(
    "forbidden",
    ["random_kfold", "kfold", "shuffle"],
)
def test_all_forbidden_split_strategies_rejected(forbidden: str) -> None:
    protocol = _good_protocol(split_strategy=forbidden)
    result = validate_protocol_obeyed(protocol)
    assert not result.ok


def test_train_to_after_validation_from_is_rejected() -> None:
    """A protocol where validation overlaps training fails embargo check."""
    protocol = _good_protocol(
        train_window_from=datetime(2025, 1, 1),
        train_window_to=datetime(2025, 9, 1),  # training ends after validation
        validation_window_from=datetime(2025, 6, 8),
        validation_window_to=datetime(2025, 9, 1),
    )
    result = validate_protocol_obeyed(protocol)
    assert not result.ok
