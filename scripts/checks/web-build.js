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

const tscBin = path.join(NODE_MODULES, 'typescript', 'bin', 'tsc');
const tsc = spawnSync(process.execPath, [tscBin, '-p', 'tsconfig.json', '--noEmit'], {
  cwd: WEB,
  encoding: 'utf8',
});
if (tsc.stdout) process.stdout.write(tsc.stdout);
if (tsc.stderr) process.stderr.write(tsc.stderr);
if (tsc.status !== 0) {
  process.exit(tsc.status ?? 1);
}

const viteBin = path.join(NODE_MODULES, 'vite', 'bin', 'vite.js');
const result = spawnSync(process.execPath, [viteBin, 'build', '--logLevel=warn'], {
  cwd: WEB,
  encoding: 'utf8',
});
const out = (result.stdout || '') + (result.stderr || '');
if (out) {
  const tail = out.split('\n').slice(-3).join('\n').trim();
  if (tail) console.log(tail);
}
if (result.status === 0) console.log('web build: success');
process.exit(result.status ?? 1);
