# Architecture

Layered architecture spec and structural-integrity principles for
DustOps AI.

---

## Layer model

```
+------------------+
|       UI         |  web/  - React + TypeScript
+------------------+
         |
         v
+------------------+
|       API        |  app/api/  - FastAPI routes; thin
+------------------+
         |
         v
+------------------+
|     Domain       |  app/domain/  - mine state, forecasting,
|                  |  attribution, simulation, optimization,
|                  |  recommendation, approvals, feedback
+------------------+
         |
         v
+------------------+
|     Storage      |  app/storage/  - repositories + DB
+------------------+
```

Sidecars (depended on by the layers above, never the reverse):

- `app/schemas/` - Pydantic schemas (used by API and Domain)
- `app/config/` - settings and per-site configuration
- `app/audit/` - audit log writer (used by Domain and API)
- `app/models/` - ML model interfaces & implementations (used by Domain)
- `app/simulation/` - intervention simulator (used by Domain)
- `app/ingestion/` - sensor / weather / equipment intake (used by API
  and writes to Storage via repositories)

## The dependency rule

```
UI -> API -> Domain -> Storage
```

### Allowed

- UI calls API.
- API calls Domain services.
- Domain services use Storage interfaces.
- Storage talks to the database.
- Domain uses Model interfaces.
- Model implementations return typed results.
- Reporting reads from repositories.

### Forbidden (validated by `scripts/validate-boundaries.js` from Phase B)

- Storage importing API.
- Domain importing UI.
- API depending on frontend components.
- UI directly importing Storage.
- ML model code mutating database records directly.
- API route handlers containing heavy business logic.
- UI components embedding core dust-risk or optimization logic.
- Site-specific constants hardcoded inside business logic (must live in
  `app/config/site_config.py` or DB-backed site configuration).

## Structural-integrity principles

### 1. Stable contracts
Every subsystem communicates through typed interfaces or schemas defined
in `app/schemas/` and documented in `docs/subsystem-contracts.md`.

### 2. Fault isolation
If one subsystem fails, the platform should degrade, not collapse.
- Source attribution failure must not break forecasting.
- UI map failure must not break the recommendations API.
- ML model failure must trigger a documented heuristic fallback.

### 3. Confidence-aware outputs
Every prediction, attribution, simulation, and recommendation includes
confidence and a short uncertainty explanation. Schema-enforced.

### 4. Human-readable reasoning
Every recommendation explains itself in operator-friendly language. See
the recommendation template in `docs/subsystem-contracts.md` (S12).

### 5. Shadow mode
Every layer that produces operational output (forecasting, attribution,
recommendations) supports shadow mode: produce, log, do not act.

### 6. Audit everything
See `docs/safety-guardrails.md` for the mandatory audit list.

### 7. Replaceable models
ML models sit behind interfaces in `app/models/`. Heuristic baselines and
trained models implement the same interface.

### 8. Mock-first
Realistic mock data generators feed the same ingestion APIs that real
sensors will. The Domain layer cannot tell the difference.

### 9. Site-specific configuration
Mine-specific values live in `app/config/site_config.py` or database
records. Never in business logic.

### 10. Separation of concerns
Monitor, predict, attribute, simulate, recommend, approve, execute,
learn, report - each is its own subsystem with one responsibility.

### 11. No blind automation
See `docs/safety-guardrails.md`. Default automation level is L1 -
Advisory.

### 12. Observability
Structured logging, health checks, model performance metrics, data
quality monitoring, validation scripts, smoke tests.

---

## Recommended technology defaults

These are **defaults**, not lock-ins. Phase B picks the stack and
documents the choice. Every default below has a "test alternatives"
note - if the choice creates pain by Phase D or Phase E, swap it before
deeper phases compound the cost. Any swap follows the architect protocol
(plan, approve, snapshot, validate).

### Backend

| Default                | Notes                                                 |
|------------------------|-------------------------------------------------------|
| Python 3.11+           |                                                       |
| FastAPI                | Test alternatives if heavy WebSocket / streaming work appears: consider Litestar or Starlette directly. |
| Pydantic v2            | Used to enforce all schema contracts.                 |
| SQLAlchemy or SQLModel | Test alternatives: if domain modeling becomes painful, consider raw SQL with `psycopg` + dataclasses. |
| PostgreSQL             | SQLite acceptable for first local MVP if explicitly marked. Test alternatives: TimescaleDB for time-series load by Phase E; DuckDB for analytics-style reporting only. |
| Redis (optional)       | For real-time cache / queues; defer until Phase D shows need. |
| Celery / RQ / Arq      | Background jobs; pick when the first scheduled or async task lands. |

### ML

| Default                  | Notes                                              |
|--------------------------|----------------------------------------------------|
| scikit-learn baselines   | Heuristics first.                                  |
| XGBoost / LightGBM / CatBoost | Test alternatives only after baselines exist; choose based on a fair benchmark on real or simulated data. |
| pandas + numpy           | Test alternatives: Polars if dataframes become a perf bottleneck in feature pipeline. |
| Model registry abstraction | Required from Phase E. MLflow not required.      |

### Frontend

| Default                  | Notes                                              |
|--------------------------|----------------------------------------------------|
| React + TypeScript + Vite | Test alternatives: SvelteKit or SolidJS if dashboard renders become heavy at Phase J scale. |
| Recharts or Visx         | Charts. Map library decided in Phase J.            |
| TanStack Query           | API client cache layer.                            |

### DevOps

| Default                  | Notes                                              |
|--------------------------|----------------------------------------------------|
| Docker + docker-compose  | Phase B.                                           |
| GitHub Actions           | If hosting on GitHub. Otherwise plain Make + scripts. |
| Structured logging (JSON) | Required from Phase B.                            |

### Stack-swap criteria

A swap is justified when at least one of:
1. The current default blocks a contract requirement (e.g. real-time
   streaming when FastAPI's pattern feels wrong).
2. The current default forces business logic into the wrong layer.
3. Performance requirements documented in the active phase plan cannot
   be met.
4. A planned later subsystem (e.g. TimescaleDB-style retention) would
   require a destructive migration if deferred further.

A swap is **not** justified by:
- Personal preference
- Fashion
- "It would be nicer with X"

---

## What lives where (Phase B onward)

```
web/                   - presentation layer (React + TypeScript)
app/api/               - FastAPI routes; thin adapters to domain
app/domain/            - core business logic; no I/O imports
app/models/            - ML model interfaces + impls
app/simulation/        - intervention simulator + counterfactuals
app/ingestion/         - intake from sensors/weather/equipment
app/storage/           - repositories + DB session + migrations
app/schemas/           - Pydantic schemas (the wire / contract format)
app/config/            - settings + per-site config
app/audit/             - audit log writer
app/reporting/         - ROI / compliance / model-performance reports
scripts/               - dev, smoke, validation, seed, rollback helpers
tests/                 - backend tests (api, domain, models, safety, contracts)
web/src/test/          - frontend tests
docs/                  - architecture, contracts, risk register, protocols
ops/                   - operational tools (rollback.py)
```
