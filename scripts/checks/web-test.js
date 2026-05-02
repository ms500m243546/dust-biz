#!/usr/bin/env node
'use strict';

const { skipIfMissing, runWebBin } = require('../lib/web');

skipIfMissing();
runWebBin('vitest/vitest.mjs', ['run', '--reporter=basic'], {
  summarize: (out) => out
    .split('\n')
    .filter((l) => /Test Files|Tests/.test(l))
    .join('\n')
    .trim(),
});
