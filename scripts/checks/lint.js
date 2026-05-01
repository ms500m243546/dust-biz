'use strict';

const path = require('path');
const { spawnSync } = require('child_process');
const { resolvePython, pythonSourceLabel } = require('../lib/python');

const ROOT = path.resolve(__dirname, '..', '..');
const python = resolvePython(ROOT);

const result = spawnSync(python, ['-m', 'ruff', 'check', 'app', 'tests'], {
  cwd: ROOT,
  encoding: 'utf8',
});

if (result.error) {
  console.error(`failed to invoke python (${pythonSourceLabel(python, ROOT)}): ${result.error.message}`);
  console.error('install dev deps with: python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"');
  process.exit(1);
}
if (result.status !== 0) {
  if (result.stdout) console.error(result.stdout);
  if (result.stderr) console.error(result.stderr);
  process.exit(result.status || 1);
}

console.log(`ruff (${pythonSourceLabel(python, ROOT)}): no lint issues in app/, tests/`);
process.exit(0);
