#!/usr/bin/env node
'use strict';

const { skipIfMissing, runWebBin } = require('../lib/web');

// Type-checking is owned by web-typecheck; web-build only verifies the
// production bundle assembles. Vite delegates type-erasure to esbuild
// without re-running tsc.
skipIfMissing();
runWebBin('vite/bin/vite.js', ['build', '--logLevel=warn'], {
  summarize: (out) => out.split('\n').slice(-3).join('\n').trim(),
  successLine: 'web build: success',
});
