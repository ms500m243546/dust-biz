"""Intervention impact models (S9, Phase G).

Implementations register themselves into `app.models.registry` under
`model_kind = "intervention_impact"`. The Domain layer obtains a model
exclusively via the registry; it never imports a concrete class.
"""
