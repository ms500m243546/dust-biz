"""Ingestion package.

Today: mock stream generators (Phase C.3) - synthetic but
operationally-shaped data so the rest of the platform can be exercised
end to end before real sensors are connected.

Later: real ingestion adapters (vendor-specific sensor protocols,
dispatch system pulls). Each one writes through the same Pydantic
schemas + repositories that mock streams use, so downstream code never
sees the difference.
"""
