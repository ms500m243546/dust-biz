'use strict';

/**
 * Phase M.1: assert every persisted `model_performance_metrics` row
 * obeys the binding evaluation protocol from
 * `docs/anti-overfit-protocol.md`.
 *
 * Rule: every row's `metric_payload.protocol` block must contain:
 *   - protocol_version (matching the M.1 contract or later)
 *   - protocol_hash (SHA-256 of the canonical protocol fields)
 *   - split_strategy in {walk_forward, expanding_window, sealed_test}
 *   - baselines_named including persistence + seasonal_naive +
 *     regulatory_threshold_classifier
 *   - sealed_test_used boolean
 *
 * Pre-M.1 rows (metric_payload missing the `protocol` block) are
 * permitted but the validator emits a warning so the operator knows
 * which rows still need re-evaluation under the new gate.
 *
 * The validator reads the dev SQLite at `dustops.db` directly. If the
 * file is absent (fresh checkout, CI without DB), the gate self-skips
 * with a PASS — there are no rows to check.
 */

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..');
const DB_PATH = path.join(ROOT, 'dustops.db');

const REQUIRED_BASELINES = [
  'persistence',
  'seasonal_naive',
  'regulatory_threshold_classifier',
];

const ALLOWED_SPLITS = new Set([
  'walk_forward',
  'expanding_window',
  'sealed_test',
]);

// Protocol versions that include the M.4.1 calibration + covariate
// fields. Rows persisted under earlier versions skip those checks.
const M4_PROTOCOL_VERSIONS = new Set(['M.4']);

function pythonExe() {
  // Prefer the repo-local venv, fall back to PATH python.
  const venvPy = path.join(ROOT, '.venv', 'Scripts', 'python.exe');
  if (fs.existsSync(venvPy)) return venvPy;
  return 'python';
}

function readMetricRows() {
  // Read rows via Python — sqlite3 is in stdlib and we already depend
  // on Python for the rest of the gate.
  const script =
    'import json,sqlite3,sys;c=sqlite3.connect(sys.argv[1]);c.row_factory=sqlite3.Row;' +
    "rows=c.execute('SELECT metric_id, model_version, metric_payload FROM " +
    "model_performance_metrics ORDER BY metric_id').fetchall();" +
    "print(json.dumps([{'metric_id':r['metric_id']," +
    "'model_version':r['model_version']," +
    "'metric_payload':r['metric_payload']} for r in rows]))";
  const out = execFileSync(pythonExe(), ['-c', script, DB_PATH], {
    encoding: 'utf8',
  });
  return JSON.parse(out);
}

function fail(msg) {
  console.error(msg);
  process.exit(1);
}

function main() {
  if (!fs.existsSync(DB_PATH)) {
    console.log(
      'overfit-discipline: dustops.db absent; nothing to check (fresh checkout)'
    );
    process.exit(0);
  }

  let rows;
  try {
    rows = readMetricRows();
  } catch (err) {
    // Table missing (pre-K.1 schema) -> nothing to check; pass.
    if (/no such table/i.test(String(err))) {
      console.log(
        'overfit-discipline: model_performance_metrics absent; nothing to check'
      );
      process.exit(0);
    }
    fail(`overfit-discipline: failed to read metric rows: ${err.message}`);
  }

  const errors = [];
  let preM1 = 0;
  let postM1 = 0;
  let postM4 = 0;
  let sealedSeen = 0;
  let eceOverrides = 0;

  for (const row of rows) {
    let payload = row.metric_payload;
    if (typeof payload === 'string') {
      try {
        payload = JSON.parse(payload);
      } catch (err) {
        errors.push(
          `metric_id=${row.metric_id}: metric_payload is not valid JSON`
        );
        continue;
      }
    }
    if (!payload || typeof payload !== 'object') {
      errors.push(
        `metric_id=${row.metric_id}: metric_payload is empty or non-object`
      );
      continue;
    }
    const protocol = payload.protocol;
    if (!protocol || typeof protocol !== 'object') {
      // Pre-M.1 row — not an error, but we count and report.
      preM1 += 1;
      continue;
    }
    postM1 += 1;

    if (!protocol.protocol_version) {
      errors.push(
        `metric_id=${row.metric_id}: protocol.protocol_version missing`
      );
    }
    if (!protocol.protocol_hash || protocol.protocol_hash.length !== 64) {
      errors.push(
        `metric_id=${row.metric_id}: protocol.protocol_hash missing or malformed (expected 64-char SHA-256)`
      );
    }
    if (!ALLOWED_SPLITS.has(protocol.split_strategy)) {
      errors.push(
        `metric_id=${row.metric_id}: split_strategy=${JSON.stringify(
          protocol.split_strategy
        )} not in ${[...ALLOWED_SPLITS].join('|')}`
      );
    }
    const baselines = protocol.baselines_named || [];
    const missingBaselines = REQUIRED_BASELINES.filter(
      (b) => !baselines.includes(b)
    );
    if (missingBaselines.length) {
      errors.push(
        `metric_id=${row.metric_id}: protocol.baselines_named missing: ${missingBaselines.join(', ')}`
      );
    }
    if (typeof protocol.sealed_test_used !== 'boolean') {
      errors.push(
        `metric_id=${row.metric_id}: protocol.sealed_test_used must be boolean`
      );
    }
    if (protocol.sealed_test_used) sealedSeen += 1;

    // M.4.1 — calibration + covariate discipline. Required only for
    // rows tagged with an M.4 protocol_version. M.1/M.2/M.3 rows are
    // tolerated (they predate the rule).
    if (M4_PROTOCOL_VERSIONS.has(protocol.protocol_version)) {
      postM4 += 1;
      if (typeof protocol.max_ece !== 'number') {
        errors.push(
          `metric_id=${row.metric_id}: protocol.max_ece missing or non-numeric (M.4 requirement)`
        );
      }
      for (const key of ['feature_set', 'required_covariates', 'forbidden_covariates']) {
        if (!Array.isArray(protocol[key])) {
          errors.push(
            `metric_id=${row.metric_id}: protocol.${key} must be an array (M.4 requirement)`
          );
        }
      }
      if (!Array.isArray(payload.calibration_bins)) {
        errors.push(
          `metric_id=${row.metric_id}: metric_payload.calibration_bins missing or non-array (anti-overfit rule 8)`
        );
      }
      // ece may be null when observed_count=0; otherwise it must be a number.
      if (
        payload.observed_count > 0 &&
        typeof payload.ece !== 'number'
      ) {
        errors.push(
          `metric_id=${row.metric_id}: metric_payload.ece missing on a row with observed_count=${payload.observed_count}`
        );
      }
      if (
        payload.observed_count > 0 &&
        typeof payload.brier_score !== 'number'
      ) {
        errors.push(
          `metric_id=${row.metric_id}: metric_payload.brier_score missing on a row with observed_count=${payload.observed_count}`
        );
      }
      // ECE acceptance gate cross-check: if ece > max_ece, the row
      // must carry an override warning (the gate would have raised
      // otherwise — this catches manually-inserted rows).
      if (
        typeof payload.ece === 'number' &&
        typeof protocol.max_ece === 'number' &&
        payload.ece > protocol.max_ece
      ) {
        const warnings = Array.isArray(protocol.warnings)
          ? protocol.warnings
          : [];
        const hasOverride = warnings.some((w) =>
          /calibration acceptance gate overridden/.test(String(w))
        );
        if (!hasOverride) {
          errors.push(
            `metric_id=${row.metric_id}: ece=${payload.ece} > max_ece=${protocol.max_ece} but no override warning recorded (anti-overfit rule 8)`
          );
        } else {
          eceOverrides += 1;
        }
      }
    }
  }

  if (errors.length > 0) {
    for (const e of errors) console.error(e);
    process.exit(1);
  }

  console.log(
    `overfit-discipline: ${rows.length} metric row(s) scanned; ` +
      `${postM1} M.1+ protocol-tagged (${postM4} under M.4 calibration gate), ` +
      `${preM1} pre-M.1 (permitted), ${sealedSeen} sealed-test runs, ` +
      `${eceOverrides} ECE-gate overrides`
  );
  process.exit(0);
}

main();
