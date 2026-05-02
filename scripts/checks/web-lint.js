#!/usr/bin/env node
'use strict';

const { skipIfMissing, runWebBin } = require('../lib/web');

skipIfMissing();
runWebBin('eslint/bin/eslint.js', ['src', '--ext', '.ts,.tsx'], {
  successLine: 'web lint: clean',
});
