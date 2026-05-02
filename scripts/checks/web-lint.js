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

const eslintBin = path.join(NODE_MODULES, 'eslint', 'bin', 'eslint.js');
const result = spawnSync(process.execPath, [eslintBin, 'src', '--ext', '.ts,.tsx'], {
  cwd: WEB,
  encoding: 'utf8',
});
if (result.stdout) process.stdout.write(result.stdout);
if (result.stderr) process.stderr.write(result.stderr);
if (result.status === 0) console.log('web lint: clean');
process.exit(result.status ?? 1);
