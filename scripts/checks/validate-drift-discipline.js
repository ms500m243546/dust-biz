'use strict';

/**
 * Phase M.4.3: assert the codebase carries the drift-watch surface
 * required to mitigate B-12 (concept drift / regime change).
 *
 * Static / structural checks only (drift detection itself is runtime,
 * computed on read by the GET /api/v1/drift handler):
 *
 *   1. `app/domain/drift_watch.py` exists and exports
 *      `DriftAlert`, `compute_drift`, `DRIFT_THRESHOLDS`.
 *   2. `app/schemas/drift.py` exists and defines `DriftAlertSchema`.
 *   3. `app/api/routes/drift.py` exists and is mounted in
 *      `app/api/main.py`.
 *   4. The bias register has flipped B-12 to Mitigated.
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const MODULE = path.join(ROOT, 'app', 'domain', 'drift_watch.py');
const SCHEMA = path.join(ROOT, 'app', 'schemas', 'drift.py');
const ROUTE = path.join(ROOT, 'app', 'api', 'routes', 'drift.py');
const MAIN = path.join(ROOT, 'app', 'api', 'main.py');
const BIAS_REGISTER = path.join(ROOT, 'docs', 'bias-register.md');

const REQUIRED_MODULE_EXPORTS = [
  'DriftAlert',
  'compute_drift',
  'DRIFT_THRESHOLDS',
];

const errors = [];

if (!fs.existsSync(MODULE)) {
  errors.push(`required module missing: ${path.relative(ROOT, MODULE)}`);
} else {
  const txt = fs.readFileSync(MODULE, 'utf8');
  for (const sym of REQUIRED_MODULE_EXPORTS) {
    const re = new RegExp(`(\\bdef\\s+${sym}\\b|\\bclass\\s+${sym}\\b|^${sym}\\s*[:=])`, 'm');
    if (!re.test(txt)) {
      errors.push(`drift_watch.py missing export: ${sym}`);
    }
  }
}

if (!fs.existsSync(SCHEMA)) {
  errors.push(`required schema missing: ${path.relative(ROOT, SCHEMA)}`);
} else {
  const txt = fs.readFileSync(SCHEMA, 'utf8');
  if (!/class\s+DriftAlertSchema\b/.test(txt)) {
    errors.push('app/schemas/drift.py missing DriftAlertSchema class');
  }
}

if (!fs.existsSync(ROUTE)) {
  errors.push(`required route missing: ${path.relative(ROOT, ROUTE)}`);
}

if (!fs.existsSync(MAIN)) {
  errors.push(`api main missing: ${path.relative(ROOT, MAIN)}`);
} else {
  const txt = fs.readFileSync(MAIN, 'utf8');
  if (!/\bdrift\b/.test(txt) || !/drift\.router/.test(txt)) {
    errors.push('app/api/main.py does not mount the drift router');
  }
}

if (!fs.existsSync(BIAS_REGISTER)) {
  errors.push(`bias register missing: ${path.relative(ROOT, BIAS_REGISTER)}`);
} else {
  const txt = fs.readFileSync(BIAS_REGISTER, 'utf8');
  // Look for the B-12 row carrying a Mitigated marker for M.4.3.
  const b12Line = txt.split('\n').find((line) => /\|\s*B-12\s*\|/.test(line));
  if (!b12Line) {
    errors.push('bias register missing B-12 entry');
  } else if (!/Mitigated\s*\(M\.4\.3\)/.test(b12Line)) {
    errors.push(
      'bias register B-12 has not been flipped to Mitigated (M.4.3); ' +
        'M.4.3 must mark concept-drift mitigation'
    );
  }
}

if (errors.length > 0) {
  for (const e of errors) console.error(e);
  process.exit(1);
}

console.log(
  'drift-discipline: drift_watch module + schema + route + main mount + ' +
    'bias-register B-12 flip all present'
);
process.exit(0);
