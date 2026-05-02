"""Audit log writer (S15 partial, Phase I).

Append-only event log per docs/safety-guardrails.md ("Mandatory audit
list"). Phase I lights up the writer for the approval / outcome /
safety-decision paths; subsequent phases extend the action vocabulary
without changing the schema.
"""

from app.audit.writer import record

__all__ = ["record"]
