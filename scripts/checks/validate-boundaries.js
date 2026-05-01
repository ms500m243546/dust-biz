'use strict';

/**
 * Static layer-boundary scanner.
 *
 * Enforces the dependency rule from docs/architecture.md:
 *
 *     UI -> API -> Domain -> Storage
 *
 * Mechanically detectable rules at this phase:
 *   - app/storage/**  must NOT import app.api.*
 *   - app/storage/**  must NOT import app.domain.*
 *   - app/domain/**   must NOT import app.api.*
 *   - app/schemas/**  must NOT import app.api.* or app.domain.* or app.storage.*
 *   - app/audit/**    must NOT import app.api.*
 *
 * Heavy-business-logic-in-routes and UI-imports-storage rules are not
 * mechanically detected here; those land as additions later.
 */

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const APP_DIR = path.join(ROOT, 'app');

const RULES = [
  { from: 'app/storage', forbidden: ['app.api', 'app.domain', 'app.audit'] },
  { from: 'app/domain',  forbidden: ['app.api'] },
  { from: 'app/schemas', forbidden: ['app.api', 'app.domain', 'app.storage'] },
  { from: 'app/audit',   forbidden: ['app.api'] },
  // app/models/ is a Domain peer: implements model-contracts.md
  // protocols against typed inputs only. It must not reach into the
  // API layer (no request/response coupling) or the Storage layer
  // (models are pure; persistence is the caller's job per
  // model-contracts.md universal rule 5).
  { from: 'app/models',  forbidden: ['app.api', 'app.storage'] },
];

const IMPORT_RE = /^\s*(?:from\s+([\w.]+)|import\s+([\w.]+))/gm;

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

function importsFrom(content) {
  const found = new Set();
  let m;
  IMPORT_RE.lastIndex = 0;
  while ((m = IMPORT_RE.exec(content))) {
    const target = m[1] || m[2];
    if (target) found.add(target);
  }
  return found;
}

const violations = [];
let scanned = 0;

for (const rule of RULES) {
  const dir = path.join(ROOT, rule.from);
  const files = listPyFiles(dir);
  for (const file of files) {
    scanned += 1;
    const content = fs.readFileSync(file, 'utf8');
    const imports = importsFrom(content);
    for (const imp of imports) {
      for (const forbidden of rule.forbidden) {
        if (imp === forbidden || imp.startsWith(forbidden + '.')) {
          const rel = path.relative(ROOT, file).replace(/\\/g, '/');
          violations.push(`${rel} imports "${imp}" - layer ${rule.from} cannot depend on ${forbidden}`);
        }
      }
    }
  }
}

if (violations.length === 0) {
  console.log(`scanned ${scanned} Python files in ${RULES.length} layered directories`);
  console.log('no layer-boundary violations');
  process.exit(0);
}

for (const v of violations) console.error(v);
process.exit(1);
