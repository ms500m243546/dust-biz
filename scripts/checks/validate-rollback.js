'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..');
const PYTHON = process.env.PYTHON || 'python';

const listResult = spawnSync(PYTHON, [path.join(ROOT, 'ops/rollback.py'), 'list'], {
  cwd: ROOT,
  encoding: 'utf8',
});

if (listResult.error) {
  console.error(`failed to run ${PYTHON}: ${listResult.error.message}`);
  process.exit(1);
}
if (listResult.status !== 0) {
  console.error('ops/rollback.py list exited non-zero');
  if (listResult.stdout) console.error(listResult.stdout);
  if (listResult.stderr) console.error(listResult.stderr);
  process.exit(1);
}
if (!listResult.stdout.includes('phase-a-init')) {
  console.error('phase-a-init snapshot not found in rollback list');
  console.error(listResult.stdout);
  process.exit(1);
}

// Verify manifest contents
const manifestPath = path.join(ROOT, '.rollback', 'phase-a-init', 'manifest.json');
if (!fs.existsSync(manifestPath)) {
  console.error(`manifest missing: ${manifestPath}`);
  process.exit(1);
}
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const created = Array.isArray(manifest.created) ? manifest.created : [];
if (created.length !== 17) {
  console.error(`expected 17 created files in phase-a-init manifest, got ${created.length}`);
  process.exit(1);
}

console.log('phase-a-init snapshot present; manifest tracks 17 created files');
process.exit(0);
