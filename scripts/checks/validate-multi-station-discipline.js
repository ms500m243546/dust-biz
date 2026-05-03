'use strict';

/**
 * Phase Q.3: assert the codebase carries the multi-station-discipline
 * surface required to mitigate B-5 (survivorship), B-6 (selection),
 * and B-14 (distribution shift).
 *
 * Static / structural checks only — runtime correctness is exercised
 * by tests/domain/test_multi_station_discipline.py.
 *
 *   1. `app/domain/model_performance.py` exports
 *      `_multi_station_caveats`, `RECEPTOR_TO_MINE`, and
 *      `MIN_RECEPTORS_FOR_NO_SURVIVOR_CAVEAT`.
 *   2. `compute_metric_payload` accepts a `trained_on_mine` kwarg
 *      and emits the three caveat fields (`survivor_caveat`,
 *      `selection_caveat`, `cross_mine_eval`) on both return paths.
 *   3. The bias register has flipped B-5, B-6, B-14 to Mitigated (Q.3).
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const MODULE = path.join(ROOT, 'app', 'domain', 'model_performance.py');
const BIAS_REGISTER = path.join(ROOT, 'docs', 'bias-register.md');

const REQUIRED_MODULE_TOKENS = [
  '_multi_station_caveats',
  'RECEPTOR_TO_MINE',
  'MIN_RECEPTORS_FOR_NO_SURVIVOR_CAVEAT',
];

const REQUIRED_PAYLOAD_KEYS = [
  '"survivor_caveat"',
  '"selection_caveat"',
  '"cross_mine_eval"',
];

const REQUIRED_PROTOCOL_KWARG = /trained_on_mine\s*:/;

const REQUIRED_BIAS_FLIPS = [
  { id: 'B-5',  marker: /Mitigated\s*\(Q\.3\)/ },
  { id: 'B-6',  marker: /Mitigated\s*\(Q\.3\)/ },
  { id: 'B-14', marker: /Mitigated\s*\(Q\.3\)/ },
];

const errors = [];

if (!fs.existsSync(MODULE)) {
  errors.push(`required module missing: ${path.relative(ROOT, MODULE)}`);
} else {
  const txt = fs.readFileSync(MODULE, 'utf8');
  for (const tok of REQUIRED_MODULE_TOKENS) {
    if (!txt.includes(tok)) {
      errors.push(`model_performance.py missing token: ${tok}`);
    }
  }
  for (const key of REQUIRED_PAYLOAD_KEYS) {
    // Both the no-observed-records and the populated branch must emit
    // each caveat key. Counting >= 2 occurrences is a structural proxy.
    const count = (txt.match(new RegExp(key.replace(/"/g, '"'), 'g')) || []).length;
    if (count < 2) {
      errors.push(
        `model_performance.py emits ${key} only ${count}x; expected >=2 (both return branches)`
      );
    }
  }
  if (!REQUIRED_PROTOCOL_KWARG.test(txt)) {
    errors.push('model_performance.py compute_metric_payload missing trained_on_mine kwarg');
  }
}

if (!fs.existsSync(BIAS_REGISTER)) {
  errors.push(`bias register missing: ${path.relative(ROOT, BIAS_REGISTER)}`);
} else {
  const txt = fs.readFileSync(BIAS_REGISTER, 'utf8');
  for (const { id, marker } of REQUIRED_BIAS_FLIPS) {
    const re = new RegExp(`\\|\\s*${id.replace('-', '-')}\\s*\\|`);
    const line = txt.split('\n').find((ln) => re.test(ln));
    if (!line) {
      errors.push(`bias register missing ${id} entry`);
    } else if (!marker.test(line)) {
      errors.push(
        `bias register ${id} has not been flipped to Mitigated (Q.3); ` +
          'Q.3 must mark multi-station discipline mitigations'
      );
    }
  }
}

if (errors.length > 0) {
  for (const e of errors) console.error(e);
  process.exit(1);
}

console.log(
  'multi-station-discipline: caveat helpers + payload keys + ' +
    'bias-register B-5/B-6/B-14 flips all present'
);
process.exit(0);
