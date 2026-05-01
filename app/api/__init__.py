"""API layer.

Thin adapters from HTTP to domain services. No business logic here -
see docs/architecture.md and docs/definition-of-done.md
(validate-boundaries).
"""

API_VERSION = "v1"
API_PREFIX = f"/api/{API_VERSION}"
