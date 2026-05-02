'use strict';

/**
 * Phase L: assert docs/data-source-registry.md and the
 * app/ingestion/public/ connector modules stay in sync.
 *
 * Rule: every connector module path mentioned in the registry must
 * exist on disk, and every importable connector module under
 * app/ingestion/public/ (other than the protocol shell + cache helper)
 * must appear in the registry.
 *
 * The registry is the contract. Adding a connector without registering
 * it (or vice versa) fails the gate.
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const REGISTRY = path.join(ROOT, 'docs', 'data-source-registry.md');
const CONNECTOR_DIR = path.join(ROOT, 'app', 'ingestion', 'public');

// Modules that are infrastructure, not connectors — exempt from the
// registry-presence rule.
const INFRA_MODULES = new Set(['__init__.py', 'cache.py']);

function fail(msg) {
  console.error(msg);
  process.exit(1);
}

if (!fs.existsSync(REGISTRY)) {
  fail(`registry missing: ${REGISTRY}`);
}
if (!fs.existsSync(CONNECTOR_DIR)) {
  fail(`connector directory missing: ${CONNECTOR_DIR}`);
}

const registryText = fs.readFileSync(REGISTRY, 'utf8');

// Find every `app/ingestion/public/<name>.py` reference in the registry.
// Skip infrastructure module names — those aren't connectors.
const INFRA_NAMES = new Set(['__init__', 'cache']);
const refRegex = /app\/ingestion\/public\/([a-z_][a-z0-9_]*)\.py/g;
const referenced = new Set();
let match;
while ((match = refRegex.exec(registryText)) !== null) {
  if (!INFRA_NAMES.has(match[1])) referenced.add(match[1]);
}

// Walk the connector directory.
const onDisk = new Set(
  fs
    .readdirSync(CONNECTOR_DIR)
    .filter((f) => f.endsWith('.py') && !INFRA_MODULES.has(f))
    .map((f) => f.slice(0, -3))
);

const missingFromDisk = [...referenced].filter((name) => !onDisk.has(name));
const missingFromRegistry = [...onDisk].filter((name) => !referenced.has(name));

const errors = [];
for (const name of missingFromDisk) {
  // Allow forward-reference: the registry can name a connector that
  // hasn't landed yet (e.g. `(L.3)` markers) — only fail if the file
  // is referenced as if it exists. We detect "deferred" by looking for
  // `(L.<digit>)` near the reference.
  const idx = registryText.indexOf(`app/ingestion/public/${name}.py`);
  const surrounding = registryText.slice(Math.max(0, idx - 80), idx + 80);
  if (/\(L\.\d/.test(surrounding) || /\(deferred/.test(surrounding)) {
    continue;
  }
  errors.push(`registry references missing connector: app/ingestion/public/${name}.py`);
}
for (const name of missingFromRegistry) {
  errors.push(`connector not registered in docs/data-source-registry.md: ${name}.py`);
}

if (errors.length > 0) {
  for (const e of errors) console.error(e);
  process.exit(1);
}

console.log(
  `data-source registry in sync: ${onDisk.size} connector module(s) on disk, ` +
    `${referenced.size} referenced in registry`
);
process.exit(0);
