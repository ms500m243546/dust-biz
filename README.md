# DustOps AI

Production-preserving dust-risk optimization platform for mines.

DustOps AI predicts PM10/PM2.5 dust risk, identifies likely operational
causes, simulates interventions, and recommends the smallest operational
adjustment needed to avoid dust-related stoppages while preserving
production throughput.

## The wedge

> Help mines avoid dust-related stoppages by forecasting dust-risk and
> recommending the minimum operational adjustment needed to remain under
> thresholds without sacrificing unnecessary production.

This is **not** a generic IoT dashboard, a generic ESG tool, a mine
dispatch system, or an autonomous mine controller. The boundaries are
documented in [`CLAUDE.md`](CLAUDE.md) and [`docs/system-map.md`](docs/system-map.md).

## Status

Currently in **Phase A - Architecture Constitution**. No application code
yet. The active phase plan lives in
[`docs/normalization_report.md`](docs/normalization_report.md).

## How to navigate the docs

Read in this order before proposing any change:

1. [`CLAUDE.md`](CLAUDE.md) - constitution
2. [`PLAN.md`](PLAN.md) - phase sequence A-K
3. [`docs/architect_protocol.md`](docs/architect_protocol.md) - planning, approval, rollback contract
4. [`docs/architecture.md`](docs/architecture.md) - layered architecture and dependency rules
5. [`docs/system-map.md`](docs/system-map.md) - subsystem boundaries S1-S16
6. [`docs/subsystem-contracts.md`](docs/subsystem-contracts.md) - I/O contracts
7. [`docs/data-contracts.md`](docs/data-contracts.md) - data schemas
8. [`docs/model-contracts.md`](docs/model-contracts.md) - model interfaces
9. [`docs/safety-guardrails.md`](docs/safety-guardrails.md) - automation levels and approval rules
10. [`docs/definition-of-done.md`](docs/definition-of-done.md) - merge gate
11. [`docs/ui-principles.md`](docs/ui-principles.md) - dashboard standards
12. [`docs/mining-domain.md`](docs/mining-domain.md) - operational background
13. [`docs/compliance-context.md`](docs/compliance-context.md) - PM10/PM2.5 thresholds and audit context
14. [`docs/normalization_report.md`](docs/normalization_report.md) - current state and active phase

## Setup (Phase B.2 onward)

One-time:

```
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"   # Windows
.venv/bin/python -m pip install -e ".[dev]"       # macOS / Linux
```

`agent-check` auto-detects `.venv/`. Override with `DUSTOPS_PYTHON=...`
if you keep your env elsewhere.

## Daily tools

```
npm run agent-check
python progress.py
python ops/rollback.py snapshot <name> --created F1 F2 ...
python ops/rollback.py to <name>
python ops/rollback.py list
```

## The system loop

```
Observe -> Predict -> Attribute -> Simulate -> Optimize -> Recommend -> Approve -> Execute -> Learn
```

Every recommendation includes confidence, a human-readable reason, an
estimated production impact, and an approval requirement. Nothing
high-impact executes without a human in the loop.

## License / authorship

Internal. See `CLAUDE.md` for the operating constitution.
