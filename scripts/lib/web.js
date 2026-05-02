'use strict';

const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..');
const WEB = path.join(ROOT, 'web');
const NODE_MODULES = path.join(WEB, 'node_modules');

function skipIfMissing() {
  if (!fs.existsSync(WEB)) {
    console.log('SKIP: no web/ directory yet');
    process.exit(0);
  }
  if (!fs.existsSync(NODE_MODULES)) {
    console.log('SKIP: web/node_modules not installed (run `npm install` in web/ to enable)');
    process.exit(0);
  }
}

function runWebBin(binRelPath, args, { successLine, summarize } = {}) {
  const bin = path.join(NODE_MODULES, binRelPath);
  const result = spawnSync(process.execPath, [bin, ...args], {
    cwd: WEB,
    encoding: 'utf8',
    env: { ...process.env, NO_COLOR: '1' },
  });
  const out = (result.stdout || '') + (result.stderr || '');
  if (summarize) {
    const summary = summarize(out);
    if (summary) console.log(summary);
    else if (result.status !== 0 && out) process.stdout.write(out);
  } else {
    if (result.stdout) process.stdout.write(result.stdout);
    if (result.stderr) process.stderr.write(result.stderr);
  }
  if (result.status === 0 && successLine) console.log(successLine);
  process.exit(result.status ?? 1);
}

module.exports = { skipIfMissing, runWebBin };
