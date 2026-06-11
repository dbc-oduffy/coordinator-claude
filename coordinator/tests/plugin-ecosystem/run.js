// Plugin Infrastructure Test Suite
// Run: node --test ~/.claude/plugins/coordinator-claude/coordinator/tests/plugin-ecosystem/run.js

// ---------------------------------------------------------------------------
// Windows-only: suppress console window pop-ups for child_process spawns.
//
// Tests spawn bash/git/node constantly via execSync/spawnSync. Without
// windowsHide, each spawn briefly allocates a console — the system default
// terminal then surfaces it as a flashing window that steals focus. Mirrors
// the pytest-side fix in project-rag (tests/conftest.py, 364d258).
//
// Caller-specified windowsHide is preserved (we only fill the default).
// Production code is untouched — this only patches the test process.
// ---------------------------------------------------------------------------
if (process.platform === 'win32') {
  const cp = require('child_process');
  const wrap = (orig) => function (...args) {
    const i = args.findIndex((a) => a && typeof a === 'object' && !Array.isArray(a));
    if (i === -1) {
      args.push({ windowsHide: true });
    } else if (args[i].windowsHide === undefined) {
      args[i] = { ...args[i], windowsHide: true };
    }
    return orig.apply(this, args);
  };
  for (const name of ['spawn', 'spawnSync', 'exec', 'execSync', 'execFile', 'execFileSync']) {
    if (typeof cp[name] === 'function') cp[name] = wrap(cp[name]);
  }
}

require('./marketplace.test.js');
require('./plugin-structure.test.js');
require('./references.test.js');
require('./frontmatter.test.js');
require('./hooks.test.js');
require('./hooks-behavior.test.js');
require('./mcp-config.test.js');
require('./installed-state.test.js');
require('./pipeline-templates.test.js');
require('./coordinator-degradation.test.js');
require('./orphan-sweep.test.js');
require('./handoff-schema.test.js');
require('./discover-working-repos.test.js');
require('./exec-bit.test.js');
