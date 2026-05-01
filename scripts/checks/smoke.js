'use strict';

const path = require('path');
const { spawnSync } = require('child_process');
const { resolvePython, pythonSourceLabel } = require('../lib/python');

const ROOT = path.resolve(__dirname, '..', '..');
const python = resolvePython(ROOT);

const result = spawnSync(python, [path.join(ROOT, 'scripts', '_smoke.py')], {
  cwd: ROOT,
  encoding: 'utf8',
});

if (result.error) {
  console.error(`failed to invoke python (${pythonSourceLabel(python, ROOT)}): ${result.error.message}`);
  process.exit(1);
}
if (result.status !== 0) {
  if (result.stdout) console.error(result.stdout);
  if (result.stderr) console.error(result.stderr);
  process.exit(result.status || 1);
}

const lines = (result.stdout || '').trim().split('\n');
for (const line of lines) console.log(line);
process.exit(0);
