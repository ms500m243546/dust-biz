# Definition of Done

A change is **not done** unless every item below is true.

If you cannot tick a box, the change is incomplete. Say exactly:
- what passed
- what failed
- why it failed
- what remains to fix

Never claim done if validation failed.

---

## Universal merge gate

For every change, after Phase B:

- [ ] An approved planning response exists (sections 1-11 from
      `docs/architect_protocol.md`).
- [ ] A rollback snapshot was taken before edits
      (`python ops/rollback.py snapshot ...`).
- [ ] Only the files listed in the approved plan were touched.
- [ ] Existing code that was touched was classified
      (KEEP / WRAP / ISOLATE / REFACTOR / DEFER / REMOVE LATER).
- [ ] Subsystem contracts (`docs/subsystem-contracts.md`), data
      contracts (`docs/data-contracts.md`), and model contracts
      (`docs/model-contracts.md`) are updated when applicable.
- [ ] Tests added or updated and passing.
- [ ] `npm run agent-check` is **green** end to end.
- [ ] `review-diff` reports no unresolved findings.
- [ ] Documentation updated (the docs the change refers to).
- [ ] `progress.py` state updated if a phase advanced.
- [ ] `docs/normalization_report.md` updated with what changed,
      classification applied, and any new or retired risks.
- [ ] No layer violations introduced (UI -> API -> Domain -> Storage).
- [ ] No high-impact automation path bypasses approval (S13).
- [ ] Confidence, reason, and model-version requirements are intact on
      all affected outputs.
- [ ] Rollback verified in dry-run (or snapshot listed and ready).

---

## What `npm run agent-check` runs (Phase B onward)

```
lint
typecheck
test
smoke
validate-boundaries
validate-contracts
validate-safety
review-diff
```

### `lint`
Frontend and backend linting (`ruff`, `mypy --no-incremental` if
configured, `eslint`).

### `typecheck`
TypeScript checking over `web/`. Backend type checking via `mypy` if
configured.

### `test`
- `pytest` for backend
- `vitest` for frontend

### `smoke`
Starts the backend and verifies:
```
GET /api/v1/health
GET /api/v1/meta
GET /api/v1/mine-state/current
GET /api/v1/recommendations/current
```
Then shuts down cleanly.

### `validate-boundaries`
Static scan for layer violations. Fails on:
- Storage importing API
- Domain importing UI
- UI importing Storage
- API route handlers containing heavy business logic
- Heavy business logic in UI components

### `validate-contracts`
Schema and subsystem contract validation. Fails when a subsystem
emits or consumes data that does not match its contract.

### `validate-safety`
Fails on:
- High-impact intervention can execute without approval
- Recommendation lacks confidence
- Recommendation lacks reason
- Prediction lacks `model_version`
- Low data quality does not affect downstream confidence
- Override is not audited
- Default automation level is anything other than L1 (without an
  explicit per-site override record)

### `review-diff`
Audits the diff against the approved plan. Fails on unapproved file
changes, missing contract updates, missing tests for new code paths.

---

## Phase A gate (documentary, manual)

`agent-check` does not exist yet in Phase A. Use this checklist
instead:

- [ ] All 17 files from `PLAN.md` -> Phase A deliverables exist.
- [ ] Each `docs/*.md` file is non-empty and contains the sections
      named for it in `PLAN.md` and the operating prompt.
- [ ] Subsystem IDs S1-S16 referenced in `system-map.md` match those
      used in `subsystem-contracts.md`, `data-contracts.md`,
      `model-contracts.md`, `safety-guardrails.md`, and `PLAN.md`.
- [ ] `docs/architecture.md` states the dependency rule
      `UI -> API -> Domain -> Storage` and lists forbidden imports.
- [ ] `docs/safety-guardrails.md` lists all 15 guardrails.
- [ ] Default automation level is L1 - Advisory.
- [ ] `docs/compliance-context.md` cites its threshold sources and
      marks them "replace per site."
- [ ] `docs/normalization_report.md` lists phases A-K, marks Phase A
      status, and names Phase B as next.
- [ ] `python progress.py` runs and prints the phase list.
- [ ] `python ops/rollback.py list` shows the `phase-a-init`
      snapshot.
- [ ] `python ops/rollback.py to phase-a-init` would revert the phase
      cleanly (verify by listing the snapshot manifest).

---

## What "blocked" looks like

If validation fails:

```
agent-check status: FAIL

passed:  lint, typecheck, test
failed:  validate-safety
why:     The new endpoint POST /api/v1/recommendations/dispatch
         executes an intervention without checking the approval
         record (Guardrail 1).
remaining:
- Add approval-record check in app/api/routes/recommendations.py
- Add unit test in tests/safety/test_dispatch_requires_approval.py
- Re-run agent-check
```

That format is the only acceptable "I am stuck" message. Never claim
done while a step is failing.
