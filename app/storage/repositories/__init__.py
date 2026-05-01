"""Repository layer.

Repositories wrap SQLAlchemy models with typed read/write methods so
the Domain layer never touches sessions or queries directly. Concrete
repositories arrive in Phase C alongside the ingestion pipelines.
"""
