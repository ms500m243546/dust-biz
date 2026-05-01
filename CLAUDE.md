# CLAUDE.md - DustOps AI working-directory constitution

This file is the permanent operating contract for any Claude Code session
that runs in this repository. It is loaded into context automatically.
The full operating prompt is the master document; this file is the
in-repo enforcement layer.

---

## What this repo is

**DustOps AI** is a production-preserving dust-risk optimization platform
for mines. It predicts PM10/PM2.5 dust risk, identifies likely operational
causes, simulates interventions, and recommends the smallest operational
adjustment needed to avoid dust-related stoppages while preserving
production throughput.

The system loop is:

```
Observe -> Predict -> Attribute -> Simulate -> Optimize -> Recommend -> Approve -> Execute -> Learn
```

The product objective is:

```
Minimize dust exceedance risk while minimizing production loss.
```

## What this repo is not

- A generic IoT or ESG dashboard
- A simple PM10 alerting tool
- A mine dispatch system
- A regulatory-reporting-only tool
- A fully autonomous mine controller
- A weather dashboard
- A research notebook

If a proposed change drifts toward any of those, reject it.

---

## Non-negotiable rules

These are enforced by `docs/architect_protocol.md` and
`docs/definition-of-done.md`. Re-read them at the start of any non-trivial
change.

1. **Inspect the repo before assuming.** Current code is the source of truth.
2. **Read the governing docs before changing code.** See "Required reading
   order" below.
3. **Reason at three levels.** Suprasystem (mine + environment +
   regulation + economics + people), System (DustOps platform), Subsystem
   (the specific module).
4. **Classify existing code before changing it.** KEEP / WRAP / ISOLATE /
   REFACTOR / DEFER / REMOVE LATER.
5. **Plan first, then ask.** Produce the planning response from
   `docs/architect_protocol.md` and stop for approval. Acceptable approval
   words: `approved`, `go ahead`, `proceed`.
6. **Every change must be revertible.** Snapshot via `python ops/rollback.py
   snapshot <name> --modified <files> --created <files>` before edits.
7. **No phase skipping.** Active phase is recorded in
   `docs/normalization_report.md`.
8. **No blind automation.** DustOps may recommend operational changes but
   must not directly stop production, reroute trucks, pause shovels,
   reduce crusher throughput, or change dispatch behavior without explicit
   human approval, unless the project has moved into an explicitly
   approved low-risk automation mode.
9. **Confidence is mandatory.** Every forecast, attribution, simulation,
   and recommendation must include confidence or uncertainty.
10. **Explainability is mandatory.** Every recommendation must include a
    human-readable reason.
11. **Audit everything.** Predictions, recommendations, approvals,
    rejections, overrides, outcomes, model versions, data-quality warnings,
    and safety decisions are logged.
12. **Mock-first, real-data-ready.** Mock interfaces must be replaceable
    by real sensors / dispatch / GPS / mine maps without rewriting the
    domain layer.
13. **Do not overbuild ML first.** Heuristics and baselines first; deep
    learning only when justified.
14. **UI must be operational.** The dashboard helps a shift supervisor or
    environmental manager decide under pressure. No decorative gimmicks.
15. **One-way layered dependency rule.** `UI -> API -> Domain -> Storage`.
    Never reversed.

---

## Required reading order before any code change

1. `docs/architect_protocol.md`
2. `docs/system-map.md`
3. `docs/subsystem-contracts.md`
4. `docs/data-contracts.md`
5. `docs/model-contracts.md`
6. `docs/safety-guardrails.md`
7. `docs/definition-of-done.md`
8. `docs/ui-principles.md` (if touching `web/`)
9. `docs/normalization_report.md`
10. The actual files the change will touch

Do not assume file contents. Read them.

---

## Planning response format

Before any code change, produce the structure defined in
`docs/architect_protocol.md` (sections 1-11). Stop for explicit approval.
Do not edit until approved.

## Validation gate

A done claim is invalid unless `npm run agent-check` is green AND
`review-diff` reports no unresolved findings. The full gate definition is
in `docs/definition-of-done.md`.

`agent-check` is a Phase B deliverable. In Phase A there is no Node project
yet; doc validation is manual per `docs/definition-of-done.md`.

## Tooling

- `python progress.py` - daily progress snapshot
- `python ops/rollback.py snapshot <name> --modified ... --created ...`
- `python ops/rollback.py to <name>`
- `python ops/rollback.py list`

## Where to look next

- Active phase and risks: `docs/normalization_report.md`
- Build sequence A-K: `PLAN.md`
- Operating contract for changes: `docs/architect_protocol.md`
- Mining and compliance background: `docs/mining-domain.md`,
  `docs/compliance-context.md`
