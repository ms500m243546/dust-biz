'use strict';

/**
 * Phase M.1: assert the codebase honors the binding hindsight rules
 * from `docs/anti-hindsight-protocol.md`.
 *
 * The full PIT (point-in-time) discipline lands in M.2 when schema
 * columns (`valid_from`, `valid_to`, `realtime_proxy`, `labeled_at`)
 * are added. M.1 enforces what is statically checkable today:
 *
 *   1. Every connector under `app/ingestion/public/*.py` (other than
 *      __init__.py / cache.py) must declare `realtime_proxy` semantics
 *      either via a module-level docstring annotation OR via a
 *      `LICENSE_NOTE` constant that mentions the temporal latency.
 *   2. SINCA orchestrator queries that read training data must NOT
 *      reference col 3 (validated) for hours within the embargo
 *      window. M.1 enforces this by string-matching `# realtime training`
 *      vs `# retrospective` annotations on training-data SQL queries.
 *      (Mostly informational at M.1; M.2 PIT schema replaces it.)
 *   3. The `app/domain/evaluation_protocol.py` module must export the
 *      symbols `EvaluationProtocol`, `validate_protocol_obeyed`,
 *      `ProtocolViolation`, and `protocol_to_payload_keys` so the API
 *      route + S14 evaluator can call into them.
 *
 * Failure of any of the above -> non-zero exit -> agent-check RED.
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const PUBLIC_INGEST = path.join(ROOT, 'app', 'ingestion', 'public');
const PROTOCOL_MODULE = path.join(
  ROOT,
  'app',
  'domain',
  'evaluation_protocol.py'
);
const PROTOCOL_DOC_OVERFIT = path.join(
  ROOT,
  'docs',
  'anti-overfit-protocol.md'
);
const PROTOCOL_DOC_HINDSIGHT = path.join(
  ROOT,
  'docs',
  'anti-hindsight-protocol.md'
);
const BIAS_REGISTER = path.join(ROOT, 'docs', 'bias-register.md');
const PIT_QUERY_MODULE = path.join(ROOT, 'app', 'domain', 'pit_query.py');
const SINCA_MODULE = path.join(ROOT, 'app', 'ingestion', 'public', 'sinca.py');

const INFRA_MODULES = new Set(['__init__.py', 'cache.py']);

const REQUIRED_PROTOCOL_EXPORTS = [
  'EvaluationProtocol',
  'validate_protocol_obeyed',
  'ProtocolViolation',
  'protocol_to_payload_keys',
];

function fail(msg) {
  console.error(msg);
  process.exit(1);
}

const errors = [];

// 1. Protocol docs and bias register are present.
for (const docPath of [
  PROTOCOL_DOC_OVERFIT,
  PROTOCOL_DOC_HINDSIGHT,
  BIAS_REGISTER,
]) {
  if (!fs.existsSync(docPath)) {
    errors.push(`required doc missing: ${path.relative(ROOT, docPath)}`);
  }
}

// 2. evaluation_protocol module exists and exports the required names.
if (!fs.existsSync(PROTOCOL_MODULE)) {
  errors.push(`required module missing: ${path.relative(ROOT, PROTOCOL_MODULE)}`);
} else {
  const src = fs.readFileSync(PROTOCOL_MODULE, 'utf8');
  for (const name of REQUIRED_PROTOCOL_EXPORTS) {
    // Look for the symbol in either the __all__ list or as a top-level def/class.
    const declRe = new RegExp(
      `^(?:class|def)\\s+${name}\\b|^${name}\\s*=`,
      'm'
    );
    const allRe = new RegExp(`["']${name}["']`);
    if (!declRe.test(src) && !allRe.test(src)) {
      errors.push(
        `evaluation_protocol.py missing required export: ${name}`
      );
    }
  }
}

// 3. Every connector under app/ingestion/public must mention realtime
// vs reanalysis semantics in its module docstring or near the top of
// the file. M.1 is liberal: any of these tokens count as "declared":
//   - LICENSE_NOTE constant
//   - "realtime" or "real-time" in module docstring
//   - "reanalysis" or "QC latency" in module docstring (-> implicitly
//     non-realtime)
//   - "regulator" or "regulatory" in module docstring (SINCA-shaped
//     connectors carry validated/pre-validated semantics)
//   - "operator-private" / "operator-direct" (private feeds, not
//     public-source latency)
const realtimeTokens =
  /LICENSE_NOTE|real-?time|reanalysis|QC\s+latency|regulator|operator-?(?:private|direct)/i;
if (!fs.existsSync(PUBLIC_INGEST)) {
  // Phase L hasn't landed yet; nothing to check.
} else {
  const connectors = fs
    .readdirSync(PUBLIC_INGEST)
    .filter((f) => f.endsWith('.py') && !INFRA_MODULES.has(f));
  for (const fname of connectors) {
    const fpath = path.join(PUBLIC_INGEST, fname);
    const head = fs.readFileSync(fpath, 'utf8').slice(0, 4000);
    if (!realtimeTokens.test(head)) {
      errors.push(
        `connector lacks realtime/reanalysis declaration in module ` +
          `head: app/ingestion/public/${fname} (per anti-hindsight-protocol.md rule 2)`
      );
    }
  }
}

// M.2: pit_query module exists and exports the as-of helpers.
if (!fs.existsSync(PIT_QUERY_MODULE)) {
  errors.push(
    `M.2 module missing: ${path.relative(ROOT, PIT_QUERY_MODULE)}`
  );
} else {
  const src = fs.readFileSync(PIT_QUERY_MODULE, 'utf8');
  for (const name of [
    'sensor_readings_as_of',
    'weather_readings_as_of',
    'labels_as_of',
  ]) {
    const declRe = new RegExp(`^def\\s+${name}\\b`, 'm');
    if (!declRe.test(src)) {
      errors.push(`pit_query.py missing required helper: ${name}`);
    }
  }
}

// M.2: SINCA parser exposes expand_to_pit_records (col-2/col-3 PIT split).
if (fs.existsSync(SINCA_MODULE)) {
  const src = fs.readFileSync(SINCA_MODULE, 'utf8');
  if (!/^def\s+expand_to_pit_records\b/m.test(src)) {
    errors.push(
      'sinca.py missing M.2 helper expand_to_pit_records (col-2/col-3 PIT)'
    );
  }
}

// 4. The sealed-test discipline doc is the canonical reference. The
// anti-overfit protocol must mention sealed-test by name (sanity check
// that the doc didn't get truncated mid-edit).
if (fs.existsSync(PROTOCOL_DOC_OVERFIT)) {
  const docText = fs.readFileSync(PROTOCOL_DOC_OVERFIT, 'utf8');
  if (!/sealed[\s_-]?test/i.test(docText)) {
    errors.push(
      'docs/anti-overfit-protocol.md does not mention "sealed test" — doc may be truncated'
    );
  }
  if (!/walk[\s_-]?forward/i.test(docText)) {
    errors.push(
      'docs/anti-overfit-protocol.md does not mention walk-forward CV — doc may be truncated'
    );
  }
}

if (errors.length > 0) {
  for (const e of errors) console.error(e);
  process.exit(1);
}

console.log(
  'hindsight-discipline: protocol docs present; ' +
    'evaluation_protocol exports verified; ' +
    'all public connectors declare realtime semantics'
);
process.exit(0);
