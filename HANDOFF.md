# DustOps AI — Session Handoff

**As of:** 2026-05-03
**Active phase:** M.3.1 complete — causal-contamination disclosure layer in place. The system can no longer claim causal evidence it doesn't have. True causal inference (M.3.2 UI surfacing, M.3.3 operator-real cutoff, post-M RCT data) remains deferred.
**Last completed:** M.3.1 — `docs/causal-protocol.md` + `app/domain/causal_protocol.py` + 4 schema columns + `pit_query.features_pre_intervention` + `EvaluationProtocol.causal_intent` SQL probe + `validate-causal-discipline.js`.
**Validation gate:** `npm run agent-check` GREEN, **20 PASS / 0 SKIP / 0 FAIL** (was 19 at M.2; +1 new validator). 558 backend tests + 14 web tests.

---

## State at handoff

- M.3.1 changes staged in working tree, not committed.
- Rollback log adds: `phase-m3-pre-causal` (18 modified, 6 created).
- DB state: M.3 causal columns added via `scripts/migrate_causal_columns.py`. Backup at `dustops.db.bak.pre-m3-causal-2026-05-03`.
- Memory: `project_phase_m3_complete.md` supersedes M.2.

---

## What shipped in M.3.1

### Causal protocol (binding doc)

[docs/causal-protocol.md](docs/causal-protocol.md) — evidence-class hierarchy + per-subsystem rules:

- **Evidence classes** (strongest → weakest): `experimental`, `quasi_experimental`, `observational_correlational`, `expert_judgment`.
- **S6** (forecasting): no causal field required; predictive-only claims allowed.
- **S7** (attribution): `evidence_class` required (default `observational_correlational`).
- **S9** (simulator): `simulation_method` + `counterfactual_assumption` required. Naive simulations cap confidence at 0.7.
- **S10** (cost): `selection_bias_caveat` required (True by default — calibration only on operator-acted interventions).
- **S12** (recommendation): `causal_confidence` distinct from predictive `confidence`; computed via `confidence_after_causal_penalty`.

### Code

- **[app/domain/causal_protocol.py](app/domain/causal_protocol.py)** — `EvidenceClass` + `SimulationMethod` literals; `validate_simulation` (rejects empty counterfactual + confidence > cap); `confidence_after_causal_penalty` (penalty schedule); `probe_causal_intent_training` (SQL probe).
- **[app/domain/pit_query.py](app/domain/pit_query.py)** — `features_pre_intervention(prediction_time, intervention_lag=3h, sensor_id=...)`. Correlated EXISTS via `func.datetime(decided_at, '+N seconds')` (SQLite-portable; PostgreSQL-translatable).
- **[app/domain/evaluation_protocol.py](app/domain/evaluation_protocol.py)** — `EvaluationProtocol.causal_intent: bool = False`. `validate_protocol_obeyed(session=...)` calls the new probe when True.
- **API surface** — `EvaluationProtocolSchema` (and the API route `evaluate_model` translator) carry `causal_intent` through. Default False keeps every existing caller working.

### Schema

- `source_attributions.evidence_class` (default `observational_correlational`)
- `intervention_simulations.simulation_method` (default `naive_correlation`) + `counterfactual_assumption` (default empty string) + `selection_bias_caveat` (default True)
- `recommendations.causal_confidence` (default 0.5)

### Migration

[scripts/migrate_causal_columns.py](scripts/migrate_causal_columns.py) — idempotent. Applied; all expected columns verified.

### Validator

[scripts/checks/validate-causal-discipline.js](scripts/checks/validate-causal-discipline.js) — asserts `docs/causal-protocol.md` exists with the hierarchy + simulation methods declared, `app/domain/causal_protocol.py` exports the required surface, bias register includes the 7 entries M.3 affects.

### Tests

- [tests/domain/test_causal_protocol.py](tests/domain/test_causal_protocol.py) — 13 tests (evidence-rank ordering, validate_simulation rejection paths, confidence-penalty math, ceiling enforcement).
- [tests/domain/test_pre_intervention_filter.py](tests/domain/test_pre_intervention_filter.py) — 5 tests (intervention-window exclusion, no-intervention pass-through, PIT validity respected, multi-intervention, no-sensor-id case).
- Backend test count: **540 → 558** (+18).

---

## Bias-register status updates

| ID | Bias | Pre-M.3 | Post-M.3.1 |
|---|---|---|---|
| B-16 | Treatment-effect contamination | Open | **Mitigated-via-disclosure** (M.3.3 will add true cutoff with operator-real timestamps) |
| B-17 | Reverse causality | Open | **Mitigated-via-filter** (`features_pre_intervention`) |
| B-18 | Confounding | Open | Still open (covariate-list enforcement is M.4) |
| B-19 | Spurious correlation | Open | **Mitigated-via-disclosure** |
| B-20 | Lack of counterfactual | Open | **Mitigated-via-disclosure** (M.3.3 / post-M for true counterfactual) |
| B-26 | Availability heuristic in incident labeling | Open | **Mitigated-via-disclosure** (`evidence_class=expert_judgment` flags RCA-derived labels as evaluation-only) |
| B-33 | Operator-priority bias | Open | **Mitigated-via-disclosure** (`selection_bias_caveat=True` default) |

Honest framing: most are "Mitigated-via-disclosure" rather than "Mitigated outright." This is the correct framing — M.3 cannot manufacture causal evidence we don't have; it can ensure the system doesn't *pretend* it has it. Real causal mitigation needs RCT data + ≥ 2 stations.

---

## Open work / next steps

| ID | Severity | Summary | Resolution |
|---|---|---|---|
| **M.3.2** | medium-latent | UI surfacing of `evidence_class` + `causal_confidence` on attribution / recommendation cards in S16 dashboard | Phase M.3.2 (frontend work) |
| **M.3.3** | medium-latent | True intervention-window cutoff (`ActionOutcome.intervention_window`) once operator-real telematics lands | Phase M.3.3 — depends on Antofagasta partnership data flow |
| M.4 | medium-latent | Confidence calibration enforcement (B-30), per-receptor fairness audit (B-32), Goodhart canaries (B-44), drift watch (B-12), required-covariates list (B-18) | Phase M.4 |
| L.M1-R1 | medium | 12-month Open-Meteo live pull not yet executed (network was unreachable) | Operator-runnable; idempotent under M.2 orchestrator |
| L7a-R1 | medium | Only 1 of 9 nearby SINCA stations has real data | Antofagasta partnership or SMA SEIA scrape |
| L5-carryover | medium-latent | Equipment-side ingest is the bottleneck | `operator_real` adapter ready; needs partnership data flow |

**Concrete next session priorities:**

1. **Phase M.4 — calibration + fairness + Goodhart + drift watch.** Most-likely-to-bite-next bias surface, especially confidence calibration (B-30 has Exposure=High and is currently Open).
2. **Phase M.3.2 — UI surfacing.** Lower priority unless preparing a partner demo; without dashboard exposure, evidence_class + causal_confidence flow only through API responses.
3. **Run the deferred 12-month Open-Meteo live pull** when network is stable.

---

## How a model declares causal intent (M.3+)

```python
from app.domain.evaluation_protocol import EvaluationProtocol

protocol = EvaluationProtocol(
    split_strategy="walk_forward",
    # ... usual M.1 fields ...
    causal_intent=True,  # claims its predictions are causally grounded
)
```

When `causal_intent=True` and a session is provided to `validate_protocol_obeyed`:
- Training window must include at least one `quasi_experimental` or `experimental` `SourceAttribution` row, OR
- Training window must include at least one `dispersion_model` / `propensity_matched` / `rct` `InterventionSimulation` row.
- Otherwise: HTTP 422 / `ProtocolViolation`.

For predictive-only models, leave `causal_intent=False` (the default).

---

## How to use the new pre-intervention filter

```python
from app.domain.pit_query import features_pre_intervention
from app.storage.models import SensorReading

# Train a forecaster that learns the *natural* PM10 trajectory:
rows = list(session.execute(
    features_pre_intervention(
        prediction_time=T,
        intervention_lag=timedelta(hours=3),
        sensor_id="lp-em05-cuncumen",
    )
).scalars())
```

Drops sensor rows whose `timestamp` falls inside any operator-approval window `[decided_at, decided_at+lag)`. Use any time you're consuming features for a model that should NOT learn the post-intervention reality.

---

## Key references (M.3.1)

- **[docs/causal-protocol.md](docs/causal-protocol.md)** — binding spec
- **[app/domain/causal_protocol.py](app/domain/causal_protocol.py)** — `EvidenceClass`, `SimulationMethod`, `validate_simulation`, `confidence_after_causal_penalty`, `probe_causal_intent_training`
- **[app/domain/pit_query.py](app/domain/pit_query.py)** — `features_pre_intervention` joins the existing as-of helpers
- **[scripts/migrate_causal_columns.py](scripts/migrate_causal_columns.py)** — schema migration
- **[scripts/checks/validate-causal-discipline.js](scripts/checks/validate-causal-discipline.js)** — agent-check gate
- **[docs/bias-register.md](docs/bias-register.md)** — 7 Status flips per M.3.1; B-18 still open
- **[docs/data-contracts.md](docs/data-contracts.md)** — M.3 causal columns documented
- **[docs/model-contracts.md](docs/model-contracts.md)** — lifecycle step 5 cross-references the causal protocol

## Earlier-phase references (still current)

- **[docs/anti-overfit-protocol.md](docs/anti-overfit-protocol.md)** + **[docs/anti-hindsight-protocol.md](docs/anti-hindsight-protocol.md)** — M.1 + M.2 contracts
- **[scripts/migrate_pit_columns.py](scripts/migrate_pit_columns.py)** — M.2 PIT migration
- **[scripts/migrate_unique_constraints.py](scripts/migrate_unique_constraints.py)** — L.M.1 dedup migration
