'use strict';

const path = require('path');
const { spawnSync } = require('child_process');

const COLORS = { green: 32, yellow: 33, red: 31, dim: 90, bold: 1, cyan: 36 };
const useColor = process.stdout.isTTY && !process.env.NO_COLOR;

function color(s, c) {
  if (!useColor) return s;
  const code = COLORS[c];
  if (!code) return s;
  return `\x1b[${code}m${s}\x1b[0m`;
}

function indentLines(text, prefix) {
  return text
    .replace(/\r\n/g, '\n')
    .split('\n')
    .filter((line) => line.length > 0)
    .map((line) => `${prefix}${line}`)
    .join('\n');
}

function runCheck(check, root) {
  if (!check.script) {
    return { name: check.name, status: 'skip', reason: check.skipReason || 'no script' };
  }
  const scriptPath = path.join(root, 'scripts', check.script);
  const result = spawnSync(process.execPath, [scriptPath], {
    cwd: root,
    encoding: 'utf8',
  });
  return {
    name: check.name,
    status: result.status === 0 ? 'pass' : 'fail',
    stdout: (result.stdout || '').trim(),
    stderr: (result.stderr || '').trim(),
    exitCode: result.status,
  };
}

function runChecks(checks, root, phase) {
  console.log(color(`agent-check (phase ${phase})`, 'bold'));
  console.log('');

  const passed = [];
  const skipped = [];
  const failed = [];

  for (const check of checks) {
    const result = runCheck(check, root);
    let mark;
    if (result.status === 'pass') {
      mark = color('  PASS', 'green');
      passed.push(result);
    } else if (result.status === 'skip') {
      mark = color('  SKIP', 'dim');
      skipped.push(result);
    } else {
      mark = color('  FAIL', 'red');
      failed.push(result);
    }
    const reasonStr = result.reason ? color(`  (${result.reason})`, 'dim') : '';
    console.log(`${mark}  ${check.name}${reasonStr}`);

    if (result.status === 'pass' && result.stdout) {
      console.log(color(indentLines(result.stdout, '        '), 'dim'));
    }
    if (result.status === 'fail') {
      if (result.stdout) {
        console.log(color('        stdout:', 'dim'));
        console.log(color(indentLines(result.stdout, '          '), 'dim'));
      }
      if (result.stderr) {
        console.log(color('        stderr:', 'dim'));
        console.log(color(indentLines(result.stderr, '          '), 'dim'));
      }
      console.log(color(`        exit code: ${result.exitCode}`, 'dim'));
    }
  }

  console.log('');
  const statusLine =
    failed.length === 0
      ? color('agent-check: GREEN', 'green')
      : color('agent-check: RED', 'red');
  console.log(statusLine);
  console.log(`  passed:  ${passed.length}`);
  console.log(`  skipped: ${skipped.length}`);
  console.log(`  failed:  ${failed.length}`);

  return { passed, skipped, failed };
}

module.exports = { runChecks, color };
