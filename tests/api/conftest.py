"""Shared API test fixtures.

Provides a TestClient backed by an in-memory SQLite database and the
matching session, with `app.api.deps.get_session` overridden so route
handlers see the same session the test sets up.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_session
from app.api.main import app
from app.storage.models import Base


@pytest.fixture
def api_engine() -> Iterator[Engine]:
    # StaticPool keeps a single in-memory SQLite connection alive across
    # all sessions, so tables created by Base.metadata.create_all are
    # visible to every TestClient request. Without it, each new
    # connection opens its own empty `:memory:` database.
    eng = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def api_session(api_engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=api_engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(api_engine: Engine) -> Iterator[TestClient]:
    """TestClient with get_session override.

    Each request opens a fresh session bound to the shared in-memory
    engine - this mirrors production where every request gets its own
    session but they all hit the same DB.
    """
    factory = sessionmaker(bind=api_engine, autoflush=False, autocommit=False, future=True)

    def _override() -> Iterator[Session]:
        s = factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
