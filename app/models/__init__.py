"""Model implementations + registry.

Per docs/model-contracts.md: every model is registered here; the
Domain layer obtains model instances exclusively via the registry.
Models consume typed inputs and return typed outputs; persistence
is the caller's job (universal rule 5).
"""
