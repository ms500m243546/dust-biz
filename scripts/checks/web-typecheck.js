#!/usr/bin/env node
'use strict';

const { skipIfMissing, runWebBin } = require('../lib/web');

skipIfMissing();
runWebBin('typescript/bin/tsc', ['-p', 'tsconfig.json', '--noEmit'], {
  successLine: 'web typecheck: clean',
});
