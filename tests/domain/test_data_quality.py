from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.domain.data_quality import SensorHealthScorer
from app.storage.models import Mine, Sensor
from app.storage.repositories.sensor_readings import SensorReadingRepository


def _seed_sensor(session: Session, sensor_id: str = "S1") -> None:
    session.add(Mine(mine_id="m1", name="Test"))
    session.add(Sensor(sensor_id=sensor_id, mine_id="m1", sensor_type="pm10"))
    session.flush()


def test_offline_when_no_readings(session: Session) -> None:
    _seed_sensor(session)
    scorer = SensorHealthScorer(SensorReadingRepository(session))
    status = scorer.score("S1")
    assert status.status == "offline"
    assert status.quality_score == 0.0
    assert status.downstream_confidence_multiplier == 0.0
    assert "no_recent_readings" in status.issues


def test_healthy_with_steady_recent_readings(session: Session) -> None:
    _seed_sensor(session)
    repo = SensorReadingRepository(session)
    now = datetime.now(UTC)
    for i in range(10):
        repo.add("S1", now - timedelta(minutes=i), {"pm10_ugm3": 80 + (i % 3)})
    scorer = SensorHealthScorer(SensorReadingRepository(session))
    status = scorer.score("S1", now=now)
    assert status.status == "healthy"
    assert status.quality_score >= 0.85
    assert status.downstream_confidence_multiplier >= 0.85


def test_stale_when_latest_reading_too_old(session: Session) -> None:
    _seed_sensor(session)
    repo = SensorReadingRepository(session)
    now = datetime.now(UTC)
    # all readings older than max_silence (10 min default)
    for i in range(8):
        repo.add("S1", now - timedelta(minutes=15 + i), {"pm10_ugm3": 80})
    scorer = SensorHealthScorer(SensorReadingRepository(session))
    status = scorer.score("S1", now=now)
    assert status.status == "degraded"
    assert any(issue.startswith("stale_") for issue in status.issues)
    assert status.quality_score < 1.0


def test_few_readings_degrades(session: Session) -> None:
    _seed_sensor(session)
    repo = SensorReadingRepository(session)
    now = datetime.now(UTC)
    # only 2 recent readings; min is 5
    repo.add("S1", now - timedelta(minutes=1), {"pm10_ugm3": 90})
    repo.add("S1", now, {"pm10_ugm3": 92})
    scorer = SensorHealthScorer(SensorReadingRepository(session))
    status = scorer.score("S1", now=now)
    assert "few_recent_readings" in status.issues


def test_high_variance_spike_flagged(session: Session) -> None:
    _seed_sensor(session)
    repo = SensorReadingRepository(session)
    now = datetime.now(UTC)
    # mix of low and very-high readings -> stddev > 50% of mean
    pm10s = [50, 50, 50, 200, 250, 300, 50, 50]
    for i, v in enumerate(pm10s):
        repo.add("S1", now - timedelta(minutes=i), {"pm10_ugm3": v})
    scorer = SensorHealthScorer(SensorReadingRepository(session))
    status = scorer.score("S1", now=now)
    assert "high_variance_spike" in status.issues


def test_low_source_quality_hint_propagates(session: Session) -> None:
    _seed_sensor(session)
    repo = SensorReadingRepository(session)
    now = datetime.now(UTC)
    for i in range(8):
        repo.add(
            "S1",
            now - timedelta(minutes=i),
            {"pm10_ugm3": 80},
            source_quality_hint=0.4,
        )
    scorer = SensorHealthScorer(SensorReadingRepository(session))
    status = scorer.score("S1", now=now)
    assert "low_source_quality_hint" in status.issues
    assert status.downstream_confidence_multiplier <= 0.4
