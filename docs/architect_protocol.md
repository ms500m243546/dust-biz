# Architect Protocol

The operating contract for every code change in this repo. Binding.

If you skip a step here, the change is not done, regardless of how green
the tests look.

---

## When this protocol applies

Any change other than:
- a typo fix in a doc
- updating `progress.py` state
- adding/restoring a rollback snapshot

For everything else, follow the protocol below.

---

## Step 1 - Inspect

1. Read the working directory tree. Do not assume.
2. Read the files the change will touch.
3. Read the relevant docs in the order defined in `CLAUDE.md`.

If governing docs are missing for the area you are changing, stop and
flag the gap before proposing implementation.

## Step 2 - Classify existing code

For every file the change will touch, assign one tag:

- **KEEP** - good as-is, do not alter
- **WRAP** - useful but needs an adapter / interface
- **ISOLATE** - risky or messy but needed; contain behind a boundary
- **REFACTOR** - change structure, preserve behavior
- **DEFER** - known issue, not in scope this phase
- **REMOVE LATER** - obsolete or duplicate; do not delete now

Never delete first. Isolate, wrap, or deprecate first.

## Step 3 - Three-layer reasoning

Every non-trivial change is reasoned through:

1. **Suprasystem** - mine + environment + regulation + production
   economics + human operators. What does this change mean for a shift
   supervisor or environmental manager?
2. **System** - the DustOps platform boundary touched. Which subsystem
   from `docs/system-map.md`?
3. **Subsystem** - the specific module with one responsibility. What
   contract does it expose? What contract does it consume?

## Step 4 - Produce the planning response

Use this exact structure:

```
## 1. Repo inspection summary
- Files inspected:
- Current implementation:
- Missing pieces:
- Existing code classification:
  - KEEP:
  - WRAP:
  - ISOLATE:
  - REFACTOR:
  - DEFER:
  - REMOVE LATER:

## 2. Three-layer reasoning
### Suprasystem impact
### System boundary touched
### Subsystem touched

## 3. Proposed change

## 4. Files to modify

## 5. Files to create

## 6. Contracts affected

## 7. Risks

## 8. Validation plan

## 9. Rollback plan

## 10. Implementation phases

## 11. Approval request
I will not edit files until you approve this plan.
```

Make reasonable assumptions and proceed with a plan. Ask questions only
if absolutely necessary.

## Step 5 - Stop for approval

Acceptable approval words:
- `approved`
- `go ahead`
- `proceed`

Do not write, edit, delete, move, or refactor code until approval is
given.

## Step 6 - Snapshot before edits

```
python ops/rollback.py snapshot <name> --modified <files> --created <files>
```

Snapshot name should be descriptive and unique:
`phase-<letter>-<short-purpose>` is the convention (e.g.
`phase-c-sensor-ingest`).

After Phase B, this snapshot is in addition to git, not a replacement
for it.

## Step 7 - Implement only the approved scope

- Edit only the files listed in sections 4 and 5 of the approved plan.
- If new requirements emerge during implementation, stop and re-plan.
  Do not silently expand scope.
- Update contracts (`docs/data-contracts.md`,
  `docs/subsystem-contracts.md`, `docs/model-contracts.md`) when the
  change introduces a new contract or modifies an existing one.
- Update tests.
- Update docs.

## Step 8 - Validate

Run the full validation gate:

```
npm run agent-check
```

Phase A exception: `agent-check` does not exist yet (Phase B
deliverable). Use the documentary checklist in
`docs/definition-of-done.md` -> "Phase A gate".

## Step 9 - Review-diff

Audit the actual diff against the approved plan:
- Did you touch only approved files?
- Are contracts in sync?
- Are tests added or updated?
- Are layer rules respected (UI -> API -> Domain -> Storage)?
- Are safety requirements (confidence, reason, model version, approval
  hook) intact?

## Step 10 - Update progress + normalization report

- Update `progress.py` state if a phase advanced.
- Update `docs/normalization_report.md` with: what changed, what
  classification was applied, any new risks introduced or retired.

## Step 11 - Verify rollback in dry-run

Where practical, run `python ops/rollback.py to <name>` against a
sandboxed copy or list the snapshot contents to confirm it would revert
cleanly.

---

## Failure modes this protocol prevents

- Spaghetti growth: enforced by the planning + classification step.
- Hidden coupling: enforced by contract updates being part of the change.
- Premature deletion: enforced by REMOVE LATER tag.
- Silent scope creep: enforced by step 7.
- Unsafe automation: enforced by `docs/safety-guardrails.md` checks in
  the validation gate.
- Unverifiable rollback: enforced by step 6 and step 11.
- Drift toward generic dashboard: enforced by step 3 (suprasystem
  reasoning ties every change back to the wedge).
