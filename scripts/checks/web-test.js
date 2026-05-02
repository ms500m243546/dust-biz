#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..');
const WEB = path.join(ROOT, 'web');
const NODE_MODULES = path.join(WEB, 'node_modules');

if (!fs.existsSync(WEB)) {
  console.log('SKIP: no web/ directory yet');
  process.exit(0);
}
if (!fs.existsSync(NODE_MODULES)) {
  console.log('SKIP: web/node_modules not installed');
  process.exit(0);
}

const vitestBin = path.join(NODE_MODULES, 'vitest', 'vitest.mjs');
const result = spawnSync(process.execPath, [vitestBin, 'run', '--reporter=basic'], {
  cwd: WEB,
  encoding: 'utf8',
  env: { ...process.env, CI: '1', NO_COLOR: '1' },
});
const out = (result.stdout || '') + (result.stderr || '');
const lines = out.split('\n');
const summary = lines.filter(l => /Test Files|Tests/.test(l)).join('\n').trim();
if (summary) console.log(summary);
else if (out) process.stdout.write(out);
process.exit(result.status ?? 1);
