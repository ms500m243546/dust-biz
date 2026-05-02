'use strict';

/**
 * Phase L.7: assert no production-tagged RCA seed file still contains
 * TODO_FROM_RCA markers.
 *
 * Dev + staging tolerate placeholders so we can iterate; production
 * deployments must have every receptor coord, every threshold value,
 * and every source URL filled in.
 *
 * The check walks data_seed/*.yaml. Files without `deployment_tier`
 * default to "dev" and are skipped. Files tagged `production` and
 * containing any `TODO_FROM_RCA` substring fail the gate.
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const SEED_DIR = path.join(ROOT, 'data_seed');

if (!fs.existsSync(SEED_DIR)) {
  console.log('no data_seed/ directory; skipping');
  process.exit(0);
}

const yamls = fs
  .readdirSync(SEED_DIR)
  .filter((f) => f.endsWith('.yaml') || f.endsWith('.yml'))
  .map((f) => path.join(SEED_DIR, f));

if (yamls.length === 0) {
  console.log('no seed YAMLs; skipping');
  process.exit(0);
}

const errors = [];
let scanned = 0;
let prodFiles = 0;

for (const f of yamls) {
  const text = fs.readFileSync(f, 'utf8');
  scanned += 1;

  // Crude tier detection — sufficient since the line is canonical.
  const tierMatch = text.match(/^deployment_tier:\s*(\w+)/m);
  const tier = tierMatch ? tierMatch[1] : 'dev';

  if (tier !== 'production') continue;
  prodFiles += 1;

  if (text.includes('TODO_FROM_RCA')) {
    const lines = text.split(/\r?\n/);
    for (let i = 0; i < lines.length; i += 1) {
      if (lines[i].includes('TODO_FROM_RCA')) {
        errors.push(`${path.basename(f)}:${i + 1}: ${lines[i].trim()}`);
      }
    }
  }
}

if (errors.length > 0) {
  console.error('production-tagged RCA seeds still contain TODO_FROM_RCA:');
  for (const e of errors) console.error('  ' + e);
  process.exit(1);
}

console.log(
  `RCA seed scan: ${scanned} file(s) checked; ${prodFiles} tagged production; clean`
);
process.exit(0);
