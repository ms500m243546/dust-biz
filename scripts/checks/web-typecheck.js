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
  console.log('SKIP: web/node_modules not installed (run `npm install` in web/ to enable)');
  process.exit(0);
}

const tscBin = process.platform === 'win32'
  ? path.join(NODE_MODULES, 'typescript', 'bin', 'tsc')
  : path.join(NODE_MODULES, '.bin', 'tsc');

const result = spawnSync(process.execPath, [tscBin, '-p', 'tsconfig.json', '--noEmit'], {
  cwd: WEB,
  encoding: 'utf8',
});
if (result.stdout) process.stdout.write(result.stdout);
if (result.stderr) process.stderr.write(result.stderr);
if (result.status === 0) console.log('web typecheck: clean');
process.exit(result.status ?? 1);
