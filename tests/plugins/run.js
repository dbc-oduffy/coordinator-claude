// Plugin Infrastructure Test Suite
// Run: node --test ~/.claude/tests/plugins/run.js
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
