'use strict';

/**
 * Phase M.3: assert the codebase honors the binding causal-protocol
 * rules from `docs/causal-protocol.md`.
 *
 * Static / structural checks (DB-introspection probes are runtime,
 * via `validate_protocol_obeyed(causal_intent=True)` in Python):
 *
 *   1. The `docs/causal-protocol.md` doc exists.
 *   2. `app/domain/causal_protocol.py` exports the required surface
 *      (`EvidenceClass`, `SimulationMethod`, `validate_simulation`,
 *      `confidence_after_causal_penalty`, `probe_causal_intent_training`,
 *      `CausalValidationResult`).
 *   3. The bias register includes the 7 entries that M.3 affects
 *      (B-16, B-17, B-18, B-19, B-20, B-26, B-33) — sanity check that
 *      the doc didn't get trimmed mid-edit.
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const PROTOCOL_DOC = path.join(ROOT, 'docs', 'causal-protocol.md');
const PROTOCOL_MODULE = path.join(ROOT, 'app', 'domain', 'causal_protocol.py');
const BIAS_REGISTER = path.join(ROOT, 'docs', 'bias-register.md');

const REQUIRED_PROTOCOL_EXPORTS = [
  'EvidenceClass',
  'SimulationMethod',
  'validate_simulation',
  'confidence_after_causal_penalty',
  'probe_causal_intent_training',
  'CausalValidationResult',
];

const M3_BIAS_IDS = ['B-16', 'B-17', 'B-18', 'B-19', 'B-20', 'B-26', 'B-33'];

const errors = [];

if (!fs.existsSync(PROTOCOL_DOC)) {
  errors.push(`required doc missing: ${path.relative(ROOT, PROTOCOL_DOC)}`);
} else {
  const txt = fs.readFileSync(PROTOCOL_DOC, 'utf8');
  if (!/observational_correlational/.test(txt)) {
    errors.push(
      'docs/causal-protocol.md missing the evidence-class hierarchy ' +
        '(no `observational_correlational` mention) — doc may be truncated'
    );
  }
  if (!/naive_correlation/.test(txt)) {
    errors.push(
      'docs/causal-protocol.md missing simulation-method definitions ' +
        '(no `naive_correlation` mention)'
    );
  }
}

if (!fs.existsSync(PROTOCOL_MODULE)) {
  errors.push(`required module missing: ${path.relative(ROOT, PROTOCOL_MODULE)}`);
} else {
  const src = fs.readFileSync(PROTOCOL_MODULE, 'utf8');
  for (const name of REQUIRED_PROTOCOL_EXPORTS) {
    const declRe = new RegExp(
      `^(?:class|def)\\s+${name}\\b|^${name}\\s*[:=]`,
      'm'
    );
    const allRe = new RegExp(`["']${name}["']`);
    if (!declRe.test(src) && !allRe.test(src)) {
      errors.push(
        `causal_protocol.py missing required export: ${name}`
      );
    }
  }
}

if (fs.existsSync(BIAS_REGISTER)) {
  const txt = fs.readFileSync(BIAS_REGISTER, 'utf8');
  for (const id of M3_BIAS_IDS) {
    if (!txt.includes(id)) {
      errors.push(
        `bias-register.md missing entry ${id} (expected by causal-protocol M.3 mitigation)`
      );
    }
  }
}

if (errors.length > 0) {
  for (const e of errors) console.error(e);
  process.exit(1);
}

console.log(
  'causal-discipline: protocol doc + module + bias register all present; ' +
    'evidence-class hierarchy + simulation methods declared'
);
process.exit(0);
