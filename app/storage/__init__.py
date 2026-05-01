"""Storage layer.

Repositories and database session/migration code. Storage must not
import from app.api or web/. Domain consumes storage via repository
interfaces. See docs/architecture.md.
"""
