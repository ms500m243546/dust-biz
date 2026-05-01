"""Production cost models (S10, Phase G).

Implementations register themselves into `app.models.registry` under
`model_kind = "production_cost"`. The Domain layer obtains a cost model
exclusively via the registry.
"""
