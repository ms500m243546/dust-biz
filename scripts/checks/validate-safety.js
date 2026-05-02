'use strict';

/**
 * Static safety-guardrail scanner.
 *
 * Enforces the structural pieces of docs/safety-guardrails.md that
 * can be detected without running models:
 *
 *  G2  every Forecast/Prediction/Recommendation/Attribution/Simulation
 *      Pydantic schema declares a `confidence` field.
 *  G3  every Recommendation* schema declares a `reason` field.
 *  G15 every Recommendation- and DustForecast-named schema declares
 *      a `model_version` field.
 *
 * Schema-shape checks are scoped to `app/schemas/` - the only place
 * Pydantic data contracts live (per docs/architecture.md and the
 * layer rule). Repositories, exceptions, and model-implementation
 * classes whose names happen to contain "Forecast" / "Prediction"
 * are not data contracts and are not the target of this check.
 *
 * Forbidden-pattern scan (across all .py in app/):
 *  - "skip_approval", "bypass_approval", "auto_execute_without_approval"
 *  - "TODO: confidence", "TODO: reason"
 *
 * If no safety-relevant schemas exist yet (Phase B-D), the structural
 * checks pass vacuously and the scanner reports the absence so future
 * phases can confirm coverage activates as Forecast/Recommendation
 * schemas land.
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const APP_DIR = path.join(ROOT, 'app');
const SCHEMA_DIR = path.join(APP_DIR, 'schemas');

const SAFETY_RELEVANT_PATTERNS = [
  { kind: 'Forecast',       require: ['confidence', 'model_version'] },
  { kind: 'Prediction',     require: ['confidence', 'model_version'] },
  { kind: 'Recommendation', require: ['confidence', 'reason', 'model_version'] },
  { kind: 'Attribution',    require: ['confidence'] },
  { kind: 'Simulation',     require: ['confidence'] },
  // Phase I additions: every approval / outcome record must declare
  // who decided (recorded_by / approved_by) and what they decided
  // (approval_status / intervention_effectiveness) so G8/G9 hold at
  // the schema level.
  { kind: 'ApprovalSchema', require: ['approval_status', 'approved_by', 'decided_at'] },
  { kind: 'ActionOutcome',  require: ['intervention_effectiveness'] },
];

const FORBIDDEN_SUBSTRINGS = [
  'skip_approval',
  'bypass_approval',
  'auto_execute_without_approval',
  'TODO: confidence',
  'TODO: reason',
];

function listPyFiles(dir) {
  const out = [];
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...listPyFiles(full));
    } else if (entry.isFile() && entry.name.endsWith('.py')) {
      out.push(full);
    }
  }
  return out;
}

const errors = [];
const warnings = [];
let pyFilesScanned = 0;
let safetySchemasFound = 0;

const pyFiles = listPyFiles(APP_DIR);
for (const file of pyFiles) {
  pyFilesScanned += 1;
  const content = fs.readFileSync(file, 'utf8');
  const rel = path.relative(ROOT, file).replace(/\\/g, '/');

  for (const sub of FORBIDDEN_SUBSTRINGS) {
    if (content.includes(sub)) {
      errors.push(`${rel} contains forbidden token "${sub}" (safety-guardrails.md)`);
    }
  }
}

const schemaFiles = listPyFiles(SCHEMA_DIR);
for (const file of schemaFiles) {
  const content = fs.readFileSync(file, 'utf8');
  const rel = path.relative(ROOT, file).replace(/\\/g, '/');

  for (const pattern of SAFETY_RELEVANT_PATTERNS) {
    // Match class names that contain the kind, e.g. "RecommendationSchema",
    // "DustForecast", "SourceAttribution". Require they declare the listed
    // fields in the same module.
    const classRe = new RegExp(`class\\s+(\\w*${pattern.kind}\\w*)\\b`, 'g');
    let m;
    while ((m = classRe.exec(content))) {
      safetySchemasFound += 1;
      const className = m[1];
      for (const required of pattern.require) {
        const fieldRe = new RegExp(`\\b${required}\\b\\s*:`);
        if (!fieldRe.test(content)) {
          errors.push(`${rel}: ${className} missing required safety field "${required}"`);
        }
      }
    }
  }
}

if (errors.length > 0) {
  for (const e of errors) console.error(e);
  process.exit(1);
}

console.log(`scanned ${pyFilesScanned} files in app/`);
console.log(`safety-relevant schemas found: ${safetySchemasFound}`);
if (safetySchemasFound === 0) {
  console.log('(structural checks vacuously green; activates as Forecast/Recommendation/Attribution schemas land in Phase E/F/H)');
}
console.log('no forbidden tokens; required safety fields present where applicable');
process.exit(0);
