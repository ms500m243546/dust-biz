"""Training pipelines (Phase P+).

Domain-layer training entry points that produce persisted model
artifacts plus M.4 `model_performance_metrics` rows. Per the layer
rule, training reads via repositories and writes via the storage
layer; it never imports API or UI modules.
"""
