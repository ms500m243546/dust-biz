'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');

const REQUIRED_FILES = [
  'CLAUDE.md',
  'PLAN.md',
  'README.md',
  'progress.py',
  'ops/rollback.py',
  'docs/architect_protocol.md',
  'docs/architecture.md',
  'docs/system-map.md',
  'docs/subsystem-contracts.md',
  'docs/data-contracts.md',
  'docs/model-contracts.md',
  'docs/safety-guardrails.md',
  'docs/definition-of-done.md',
  'docs/ui-principles.md',
  'docs/mining-domain.md',
  'docs/compliance-context.md',
  'docs/normalization_report.md',
];

const MIN_DOC_CHARS = 200;
const errors = [];

// 1. Existence + non-empty
for (const rel of REQUIRED_FILES) {
  const abs = path.join(ROOT, rel);
  if (!fs.existsSync(abs)) {
    errors.push(`missing: ${rel}`);
    continue;
  }
  const content = fs.readFileSync(abs, 'utf8');
  if (content.trim().length < MIN_DOC_CHARS) {
    errors.push(`too short: ${rel} (${content.trim().length} chars, min ${MIN_DOC_CHARS})`);
  }
}

function readIfExists(rel) {
  const abs = path.join(ROOT, rel);
  return fs.existsSync(abs) ? fs.readFileSync(abs, 'utf8') : null;
}

// 2. Subsystem ID consistency: S1-S16 referenced in system-map AND subsystem-contracts
const subsystemDocs = ['docs/system-map.md', 'docs/subsystem-contracts.md'];
for (const rel of subsystemDocs) {
  const content = readIfExists(rel);
  if (content === null) continue;
  for (let i = 1; i <= 16; i++) {
    const id = `S${i}`;
    const re = new RegExp(`\\b${id}\\b`);
    if (!re.test(content)) {
      errors.push(`${rel} missing reference to subsystem ${id}`);
    }
  }
}

// 3. Architecture: dependency rule statement
const arch = readIfExists('docs/architecture.md');
if (arch && !arch.includes('UI -> API -> Domain -> Storage')) {
  errors.push('docs/architecture.md does not state dependency rule "UI -> API -> Domain -> Storage"');
}
if (arch && !/Forbidden/i.test(arch)) {
  errors.push('docs/architecture.md does not list forbidden imports');
}

// 4. Safety guardrails: 15 numbered headings + L1 default
const safety = readIfExists('docs/safety-guardrails.md');
if (safety) {
  const guardrailHeadings = safety.match(/^### \d+\. /gm) || [];
  if (guardrailHeadings.length < 15) {
    errors.push(`docs/safety-guardrails.md has ${guardrailHeadings.length} guardrail headings; expected at least 15`);
  }
  if (!safety.includes('L1 - Advisory') || !safety.includes('DEFAULT')) {
    errors.push('docs/safety-guardrails.md does not declare L1 as DEFAULT');
  }
}

// 5. Compliance context: WHO + EPA citation, "replace per site"
const comp = readIfExists('docs/compliance-context.md');
if (comp) {
  if (!/replace per site/i.test(comp)) {
    errors.push('docs/compliance-context.md does not mark defaults as "replace per site"');
  }
  if (!comp.includes('WHO 2021') || !comp.includes('NAAQS')) {
    errors.push('docs/compliance-context.md missing WHO 2021 / NAAQS citations');
  }
}

// 6. Normalization report: phases A-K rows present
const norm = readIfExists('docs/normalization_report.md');
if (norm) {
  for (const ph of ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K']) {
    if (!new RegExp(`\\|\\s+${ph}\\s+\\|`).test(norm)) {
      errors.push(`docs/normalization_report.md missing phase-${ph} table row`);
    }
  }
}

if (errors.length === 0) {
  console.log(`all ${REQUIRED_FILES.length} Phase A files present and non-empty`);
  console.log('subsystem IDs S1-S16 consistent across system-map and subsystem-contracts');
  console.log('architecture dependency rule + forbidden imports asserted');
  console.log('15 safety guardrails + L1 default asserted');
  console.log('compliance defaults cite WHO 2021 + NAAQS and are marked replace-per-site');
  console.log('normalization report lists all phases A-K');
  process.exit(0);
} else {
  for (const e of errors) console.error(e);
  process.exit(1);
}
