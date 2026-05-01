'use strict';

const fs = require('fs');
const path = require('path');
const { runChecks } = require('./lib/runner');

const ROOT = path.resolve(__dirname, '..');

function getCurrentPhase() {
  const stateFile = path.join(ROOT, '.progress_state.json');
  if (!fs.existsSync(stateFile)) return 'A';
  try {
    const state = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
    return state.current_phase || 'A';
  } catch (err) {
    console.warn(`warning: could not parse .progress_state.json (${err.message}); defaulting to phase A`);
    return 'A';
  }
}

const phase = getCurrentPhase();

// Documentary + tooling checks (active from Phase A onward)
const PHASE_A_GATE = [
  { name: 'validate-phase-a-docs', script: 'checks/validate-phase-a-docs.js' },
  { name: 'validate-progress',     script: 'checks/validate-progress.js' },
  { name: 'validate-rollback',     script: 'checks/validate-rollback.js' },
];

// Python tooling checks (active from Phase B.2 onward)
const PYTHON_TOOLING = [
  { name: 'lint',      script: 'checks/lint.js' },
  { name: 'typecheck', script: 'checks/typecheck.js' },
  { name: 'test',      script: 'checks/test.js' },
  { name: 'smoke',     script: 'checks/smoke.js' },
];

// Contract validators (active from Phase B.4 onward)
const CONTRACT_VALIDATORS = [
  { name: 'validate-contracts',   script: 'checks/validate-contracts.js' },
];

// Boundary, safety, and diff inspectors (active from Phase B.5 onward)
const STRUCTURAL_VALIDATORS = [
  { name: 'validate-boundaries',  script: 'checks/validate-boundaries.js' },
  { name: 'validate-safety',      script: 'checks/validate-safety.js' },
  { name: 'review-diff',          script: 'checks/review-diff.js' },
];

const PHASE_B_PENDING = [];

const checks = [
  ...PHASE_A_GATE,
  ...PYTHON_TOOLING,
  ...CONTRACT_VALIDATORS,
  ...STRUCTURAL_VALIDATORS,
  ...PHASE_B_PENDING,
];

const { failed } = runChecks(checks, ROOT, phase);
process.exit(failed.length === 0 ? 0 : 1);
