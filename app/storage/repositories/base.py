"""Repository base.

Repositories sit between the Domain layer and SQLAlchemy. The Domain
layer never touches sessions or queries directly; it asks repositories
for typed reads and writes.

The base class is deliberately small: it owns the session reference
and nothing else. Each repository declares its own typed methods
because the read patterns differ enough that a generic CRUD base
would obscure intent.
"""

from __future__ import annotations

from sqlalchemy.orm import Session


class BaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
