'use strict';

const fs = require('fs');
const path = require('path');

/**
 * Resolve the Python executable to use for project tooling.
 *
 * Preference order:
 *   1. $DUSTOPS_PYTHON env override
 *   2. Project-local venv (.venv/Scripts/python.exe on Windows,
 *      .venv/bin/python on POSIX)
 *   3. System `python` on PATH
 */
function resolvePython(root) {
  if (process.env.DUSTOPS_PYTHON) {
    return process.env.DUSTOPS_PYTHON;
  }
  const isWin = process.platform === 'win32';
  const venvPython = isWin
    ? path.join(root, '.venv', 'Scripts', 'python.exe')
    : path.join(root, '.venv', 'bin', 'python');
  if (fs.existsSync(venvPython)) {
    return venvPython;
  }
  return 'python';
}

function pythonSourceLabel(pythonPath, root) {
  if (process.env.DUSTOPS_PYTHON) return `env DUSTOPS_PYTHON=${pythonPath}`;
  if (pythonPath.startsWith(path.join(root, '.venv'))) return '.venv';
  return 'system PATH';
}

module.exports = { resolvePython, pythonSourceLabel };
