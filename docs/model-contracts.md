# Model Contracts

Interfaces for every model component in DustOps AI. Implementations
sit behind these interfaces; first versions may be heuristics. Trained
models swap in later without rewriting the system.

All model implementations live in `app/models/` (Phase E onward).

---

## Universal model rules

1. Every model is registered in `app/models/registry.py`. The registry
   is the only way the Domain layer obtains a model instance.
2. Every prediction returns an explicit `model_version`. The version
   string travels with the record into persistence and audit.
3. Every prediction returns an explicit `confidence` and an
   optional `main_uncertainty` string (recommended for any
   non-trivial output).
4. If a model raises or returns an invalid output, the caller falls
   back to the documented heuristic and flags the output `source =
   "heuristic_fallback"` (Guardrail 11 in `safety-guardrails.md`).
5. Models do not mutate database records. They consume typed inputs
   and return typed outputs; persistence is the caller's job.
6. Model evaluation is offline (Phase K). The runtime path never
   trains.

---

## DustForecastModel

**Implements S6.**

```python
class DustForecastModel(Protocol):
    model_version: str
    model_kind: Literal["dust_forecast"]

    def predict(
        self,
        features: FeatureRecord,
        target: ForecastTarget,
        horizon: ForecastHorizon,
    ) -> DustForecast: ...

    def evaluate(
        self,
        test_data: Iterable[tuple[FeatureRecord, DustForecastLabel]],
    ) -> ForecastEvaluation: ...

    def save(self, version: str) -> None: ...

    @classmethod
    def load(cls, version: str) -> "DustForecastModel": ...
```

`DustForecast` (return) must include:
- `predicted_pm10`, `predicted_pm25` (float)
- `breach_probability` (float)
- `confidence` (float)
- `main_uncertainty` (string)
- `main_risk_window` (string)
- `model_version` (string)

Phase: E.
First implementation: heuristic (recent PM trend + wind alignment +
surface dryness penalty) followed by gradient boosting baseline.

---

## SourceAttributionModel

**Implements S7.**

```python
class SourceAttributionModel(Protocol):
    model_version: str
    model_kind: Literal["source_attribution"]

    def attribute(
        self,
        event: DustEvent,
        mine_state: MineState,
        weather: WeatherSnapshot,
        sensor_data: SensorWindow,
    ) -> SourceAttribution: ...
```

`SourceAttribution` (return) must include:
- `probable_sources`: ranked list of `{source, confidence, reason}`
- `model_version`
- overall `confidence`
- `evidence_fields`: dict of supporting numbers (e.g. wind angle to
  source, time-lag correlation, recent activity intensity)

Phase: F.
First implementation: rule-based combining (a) wind-aligned spatial
proximity to active sources, (b) activity-time / spike-time
correlation, (c) source baseline dust potential.

---

## InterventionImpactModel

**Implements S9.**

```python
class InterventionImpactModel(Protocol):
    model_version: str
    model_kind: Literal["intervention_impact"]

    def simulate(
        self,
        intervention: InterventionOption,
        current_state: MineState,
        current_forecast: DustForecast,
    ) -> InterventionSimulation: ...
```

`InterventionSimulation` (return) must include:
- `predicted_pm10_reduction` (float)
- `breach_probability_after_action` (float)
- `time_to_effect_minutes` (int)
- `confidence` (float)
- `model_version`
- `source` (`"model"` or `"heuristic"`)

Phase: G.
First implementation: heuristic per intervention class (e.g. watering
reduces dust generation in zone by X% for Y minutes; speed reduction
reduces road dust by Z%). Coefficients live in site config so they can
be tuned without code changes.

---

## ProductionCostModel

**Implements S10.**

```python
class ProductionCostModel(Protocol):
    model_version: str
    model_kind: Literal["production_cost"]

    def estimate_cost(
        self,
        intervention: InterventionOption,
        current_state: MineState,
    ) -> ProductionCostEstimate: ...
```

`ProductionCostEstimate` (return) must include:
- `estimated_tonnes_delayed` (float)
- `cycle_time_increase_percent` (float)
- `bottleneck_risk` (enum)
- `production_impact` (enum: `low`, `medium`, `high`)
- `confidence` (float)
- `model_version`

Phase: G.
First implementation: heuristic using current production rate and
intervention duration. Financial conversion deferred until
`site_config.cost_curves` is populated.

---

## OptimizationEngine

**Implements S11.**

```python
class OptimizationEngine(Protocol):
    model_version: str
    model_kind: Literal["optimization"]

    def rank_actions(
        self,
        risk_event: DustForecast,
        intervention_options: list[InterventionOption],
        simulations: dict[str, InterventionSimulation],  # by intervention_id
        cost_estimates: dict[str, ProductionCostEstimate],
        site_config: SiteConfig,
    ) -> RankedRecommendations: ...
```

`RankedRecommendations` (return) must include:
- ordered list of action candidates with: `rank`, `action`,
  `breach_probability_after`, `production_loss` (qualitative),
  `estimated_tonnes_delayed`, `confidence`, `reason`,
  `intervention_id`
- `compliance_priority_triggered` (bool; per Guardrail 7)
- `target_probability` used (float)
- `model_version`

Phase: H.
First implementation: weighted scoring against the objective in
`safety-guardrails.md` ("compliance-priority logic"). Pure ML
optimization is not in scope for MVP.

---

## Model lifecycle

1. **Train** offline (Phase K tooling).
2. **Register** by writing a `model_versions` row.
3. **Save** model artifacts under `app/models/artifacts/<version>/`.
4. **Deploy** by setting the registry's "current" pointer for that
   `model_kind` (see `app/models/registry.py`).
5. **Shadow-evaluate** new versions before promoting (S14 / Phase K).
6. **Retire** by setting `retired_at` and removing from registry; do
   not delete artifacts.

---

## Model versioning convention

```
<model_kind>_<approach>_v<MAJOR>.<MINOR>.<PATCH>
```

Examples:
- `dust_forecast_heuristic_v0.1.0`
- `dust_forecast_xgb_v1.0.0`
- `source_attribution_rules_v0.1.0`
- `intervention_impact_heuristic_v0.1.0`
- `production_cost_heuristic_v0.1.0`
- `optimization_weighted_v0.1.0`

MAJOR bumps when the input/output contract changes (and is then
documented here). MINOR bumps for behavior-changing improvements.
PATCH bumps for fixes that should not change behavior.
