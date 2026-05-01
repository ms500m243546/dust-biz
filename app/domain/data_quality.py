"""S2 - Data Quality and Sensor Health.

Heuristic scorer per `docs/model-contracts.md` ("heuristics first").
Outputs `SensorHealthStatusSchema`; downstream consumers (forecasting
in Phase E, etc.) must apply `downstream_confidence_multiplier` to
their confidence.

Heuristics implemented:
  - offline:                no readings within `recent_window`
  - stale:                  most recent reading older than `max_silence`
  - few_recent_readings:    fewer than `min_recent_readings` in window
  - high_variance_spike:    PM10 stddev > 50% of mean
  - low_source_quality_hint: minimum upstream hint < 0.7
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import get_args

from app.schemas.sensor import SensorHealthStatusSchema, SensorStatus
from app.storage.repositories.sensor_readings import SensorReadingRepository


class SensorHealthScorer:
    def __init__(
        self,
        sensor_repo: SensorReadingRepository,
        *,
        max_silence_minutes: int = 10,
        min_recent_readings: int = 5,
        recent_window_minutes: int = 30,
    ) -> None:
        self.sensor_repo = sensor_repo
        self.max_silence = timedelta(minutes=max_silence_minutes)
        self.min_recent_readings = min_recent_readings
        self.recent_window = timedelta(minutes=recent_window_minutes)

    def score(
        self, sensor_id: str, now: datetime | None = None
    ) -> SensorHealthStatusSchema:
        if now is None:
            now = datetime.now(UTC)
        recent = self.sensor_repo.get_recent(
            sensor_id, since=now - self.recent_window
        )

        if not recent:
            return SensorHealthStatusSchema(
                sensor_id=sensor_id,
                status="offline",
                quality_score=0.0,
                issues=("no_recent_readings",),
                downstream_confidence_multiplier=0.0,
            )

        issues: list[str] = []
        quality = 1.0

        # Stale check
        latest_ts = max(r.timestamp for r in recent)
        if latest_ts.tzinfo is None:
            latest_ts = latest_ts.replace(tzinfo=UTC)
        silence = now - latest_ts
        if silence > self.max_silence:
            issues.append(f"stale_{int(silence.total_seconds() // 60)}min")
            quality *= 0.5

        # Few recent readings
        if len(recent) < self.min_recent_readings:
            issues.append("few_recent_readings")
            quality *= 0.7

        # PM10 variance check (only when payload contains numeric pm10)
        pm10_values = [
            v
            for r in recent
            if isinstance(r.raw_value, dict)
            for v in [r.raw_value.get("pm10_ugm3")]
            if isinstance(v, int | float) and not isinstance(v, bool)
        ]
        if len(pm10_values) >= 5:
            mean = sum(pm10_values) / len(pm10_values)
            if mean > 0:
                variance = sum((p - mean) ** 2 for p in pm10_values) / len(pm10_values)
                stddev = variance**0.5
                if stddev > mean * 0.5:
                    issues.append("high_variance_spike")
                    quality *= 0.8

        # Source quality hint propagation
        hints = [r.source_quality_hint for r in recent if r.source_quality_hint is not None]
        if hints:
            min_hint = min(hints)
            if min_hint < 0.7:
                issues.append("low_source_quality_hint")
                quality *= min_hint

        status: SensorStatus = "healthy" if quality >= 0.85 else "degraded"
        # Sanity-check status is in the Literal alias
        assert status in get_args(SensorStatus)

        return SensorHealthStatusSchema(
            sensor_id=sensor_id,
            status=status,
            quality_score=round(quality, 3),
            issues=tuple(issues),
            downstream_confidence_multiplier=round(quality, 3),
        )
