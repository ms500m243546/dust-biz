'use strict';

const path = require('path');
const { spawnSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..');
const PYTHON = process.env.PYTHON || 'python';

const result = spawnSync(PYTHON, [path.join(ROOT, 'progress.py')], {
  cwd: ROOT,
  encoding: 'utf8',
});

if (result.error) {
  console.error(`failed to run ${PYTHON}: ${result.error.message}`);
  process.exit(1);
}
if (result.status !== 0) {
  console.error('progress.py exited non-zero');
  if (result.stdout) console.error(result.stdout);
  if (result.stderr) console.error(result.stderr);
  process.exit(1);
}
if (!result.stdout.includes('current phase:')) {
  console.error('progress.py output missing "current phase:" line');
  console.error(result.stdout);
  process.exit(1);
}
if (!result.stdout.includes('phase status:')) {
  console.error('progress.py output missing "phase status:" section');
  console.error(result.stdout);
  process.exit(1);
}

console.log('progress.py runs cleanly and prints current phase + status');
process.exit(0);
