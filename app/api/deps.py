"""FastAPI dependencies.

Today: just the per-request DB session. Domain-level dependencies will
arrive alongside the subsystems that need them (forecasting at E,
recommendation at H, etc.).
"""

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.storage.database import get_session_factory


def get_session() -> Iterator[Session]:
    """Per-request SQLAlchemy session.

    Commits on clean exit, rolls back on exception. Tests override this
    via `app.dependency_overrides[get_session] = ...` to share the
    in-memory test engine.
    """
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
