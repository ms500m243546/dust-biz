'use strict';

/**
 * Lightweight diff inspector.
 *
 * Today: confirms git is initialized, the working tree is in a sane
 * state, and reports a brief summary of changes since HEAD (or since
 * the very first state if there are no commits yet).
 *
 * Soft nudge: if app/ or scripts/ files changed, suggest also updating
 * docs/normalization_report.md (warning, not failure - active dev is
 * noisy and the architect protocol owns the final enforcement).
 *
 * Future: cross-check against the approved plan (planning response
 * file or PR description). Today the plan lives in the conversation
 * and review-diff plays the supporting role.
 */

const path = require('path');
const { spawnSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..');

function runGit(args) {
  const r = spawnSync('git', args, { cwd: ROOT, encoding: 'utf8' });
  return { ok: r.status === 0, stdout: (r.stdout || '').trim(), stderr: (r.stderr || '').trim(), exit: r.status };
}

const insideRepo = runGit(['rev-parse', '--is-inside-work-tree']);
if (!insideRepo.ok || insideRepo.stdout !== 'true') {
  console.error('not inside a git repo (run `git init` - covered by Phase B.2)');
  process.exit(1);
}

const status = runGit(['status', '--porcelain']);
if (!status.ok) {
  console.error('git status failed');
  if (status.stderr) console.error(status.stderr);
  process.exit(1);
}

const lines = status.stdout ? status.stdout.split('\n') : [];
let added = 0;
let modified = 0;
let deleted = 0;
let untracked = 0;
let touchedAppOrScripts = false;
let touchedNormalizationReport = false;

for (const line of lines) {
  const code = line.slice(0, 2);
  const file = line.slice(3);
  if (code.includes('?')) untracked += 1;
  else if (code.includes('A')) added += 1;
  else if (code.includes('M')) modified += 1;
  else if (code.includes('D')) deleted += 1;
  if (file.startsWith('app/') || file.startsWith('scripts/')) touchedAppOrScripts = true;
  if (file === 'docs/normalization_report.md') touchedNormalizationReport = true;
}

console.log(`git working tree: ${lines.length} entries (added=${added} modified=${modified} deleted=${deleted} untracked=${untracked})`);

if (touchedAppOrScripts && !touchedNormalizationReport && lines.length > 0) {
  console.log('hint: app/ or scripts/ changed; consider updating docs/normalization_report.md per architect_protocol.md step 10');
}

// Conflict marker scan in tracked files
const conflicts = runGit(['diff', '--check']);
if (!conflicts.ok && conflicts.stdout) {
  console.error('conflict markers detected:');
  console.error(conflicts.stdout);
  process.exit(1);
}

console.log('no conflict markers; working tree healthy');
process.exit(0);
