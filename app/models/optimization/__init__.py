"""Optimization engine implementations (S11, Phase H).

Implementations register themselves into `app.models.registry` under
`model_kind = "optimization"`. The Domain layer obtains the engine
exclusively via the registry.
"""
