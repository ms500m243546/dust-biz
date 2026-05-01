'use strict';

const path = require('path');
const { spawnSync } = require('child_process');
const { resolvePython, pythonSourceLabel } = require('../lib/python');
const { PHASE_B4 } = require('../lib/contract_index');

const ROOT = path.resolve(__dirname, '..', '..');
const python = resolvePython(ROOT);

const expectations = PHASE_B4;

// Pass expectations via stdin as JSON to avoid Python/JSON keyword
// mismatches (null vs None, true vs True).
const importProgram = `
import importlib, json, sys

expectations = json.loads(sys.stdin.read())
errors = []
checked_schemas = 0
checked_models = 0

for spec in expectations:
    try:
        mod = importlib.import_module(spec["schemaModule"])
        cls = getattr(mod, spec["schemaClass"], None)
        if cls is None:
            errors.append(f"schema class missing: {spec['schemaModule']}.{spec['schemaClass']}")
        else:
            checked_schemas += 1
    except Exception as e:
        errors.append(f"schema import failed: {spec['schemaModule']} ({e})")

    if spec["model"]:
        try:
            models_mod = importlib.import_module("app.storage.models")
            model_cls = getattr(models_mod, spec["model"], None)
            if model_cls is None:
                errors.append(f"ORM model missing: app.storage.models.{spec['model']}")
            else:
                checked_models += 1
        except Exception as e:
            errors.append(f"ORM model import failed: {spec['model']} ({e})")

print(json.dumps({"errors": errors, "schemas": checked_schemas, "models": checked_models}))
sys.exit(1 if errors else 0)
`;

const result = spawnSync(python, ['-c', importProgram], {
  cwd: ROOT,
  encoding: 'utf8',
  input: JSON.stringify(expectations),
});

if (result.error) {
  console.error(`failed to invoke python (${pythonSourceLabel(python, ROOT)}): ${result.error.message}`);
  process.exit(1);
}

let payload;
try {
  payload = JSON.parse((result.stdout || '').trim().split('\n').pop() || '{}');
} catch (e) {
  console.error('could not parse validator output');
  if (result.stdout) console.error(result.stdout);
  if (result.stderr) console.error(result.stderr);
  process.exit(1);
}

if (result.status !== 0) {
  for (const err of payload.errors || []) console.error(err);
  if (result.stderr) console.error(result.stderr);
  process.exit(result.status || 1);
}

console.log(`${payload.schemas} Pydantic schemas + ${payload.models} ORM models present`);
console.log(`${expectations.length} contract entities checked against scripts/lib/contract_index.js`);
process.exit(0);
