#!/usr/bin/env node
'use strict';
/**
 * verify-coverage.js — cross-reference integrity sweep for the coordinator-claude plugin tree.
 *
 * Inspired by holodeck's agent-domain-coverage.test.ts (which enforces TOOL_ORPHANED /
 * TOOL_DOUBLE_CLAIMED / STALE_AGENT_ENTRY against the MCP tool-defs ↔ agent-routing-table
 * producer/consumer contract). This script ports the same shape to coordinator-claude's
 * producer/consumer surface — every reference to a skill, agent, or command must resolve
 * to a real artifact on disk.
 *
 * Invariants enforced:
 *
 *   SKILL_ORPHANED   — every `<plugin>:<skill>` reference resolves to a real
 *                      <plugin>/skills/<skill>/SKILL.md
 *   AGENT_ORPHANED   — every `subagent_type: <name>` or `<plugin>:<agent>` reference
 *                      resolves to a real <plugin>/agents/<agent>.md
 *   COMMAND_ORPHANED — every `/<plugin>:<command>` or bare `/command` reference
 *                      resolves to a real <plugin>/commands/<command>.md
 *   WORKER_ORPHANED  — every worker named under a reviewer's "## Worker Dispatch
 *                      Recommendations" block exists as an agent (special case of
 *                      AGENT_ORPHANED with stricter prose-context anchor)
 *
 * Each reference must resolve to either a skill, an agent, OR a command in the
 * fully-qualified `<plugin>:<name>` namespace — the script tracks all three artifact
 * types under the same prefix because the namespace is shared at the reference site.
 *
 * Usage:
 *   node bin/verify-coverage.js [--root <path>] [--json] [--report-only]
 *
 * Options:
 *   --root <path>    Plugin tree root. Defaults to ~/.claude/plugins/coordinator-claude/
 *   --json           Emit machine-readable JSON instead of markdown report
 *   --report-only    Always exit 0 even when violations exist (useful for /update-docs
 *                    surface emission without gating)
 *
 * Exit codes:
 *   0  — all references resolve (or --report-only flag set)
 *   1  — one or more orphan references found
 *   2  — usage / configuration error
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  const args = { root: null, json: false, reportOnly: false };
  for (let i = 2; i < argv.length; i++) {
    switch (argv[i]) {
      case '--root':        args.root = argv[++i]; break;
      case '--json':        args.json = true; break;
      case '--report-only': args.reportOnly = true; break;
      case '-h':
      case '--help':
        console.log('Usage: node bin/verify-coverage.js [--root <path>] [--json] [--report-only]');
        process.exit(0);
      default:
        console.error(`Unknown argument: ${argv[i]}`);
        process.exit(2);
    }
  }
  return args;
}

// ---------------------------------------------------------------------------
// Plugin tree discovery
// ---------------------------------------------------------------------------

function defaultRoot() {
  return path.join(os.homedir(), '.claude', 'plugins', 'coordinator-claude');
}

/**
 * Walk the plugin tree and discover artifacts.
 *
 * The tree shape is: <root>/<plugin>/{skills,agents,commands}/*
 * Plus the deep-research subplugin: <root>/deep-research/notebooklm/{skills,agents,commands}/*
 *
 * Returns { skills, agents, commands } maps keyed by "<plugin>:<name>".
 */
function discoverArtifacts(root) {
  const skills = new Map();    // "<plugin>:<name>" → absolute path
  const agents = new Map();
  const commands = new Map();

  // Enumerate top-level plugin directories.
  const topPlugins = fs.readdirSync(root, { withFileTypes: true })
    .filter(d => d.isDirectory() && !d.name.startsWith('.') && d.name !== 'docs')
    .map(d => d.name);

  // Also include the notebooklm sub-plugin under deep-research, if present.
  const pluginPairs = topPlugins.map(p => [p, path.join(root, p)]);
  const nlmDir = path.join(root, 'deep-research', 'notebooklm');
  if (fs.existsSync(nlmDir)) pluginPairs.push(['notebooklm', nlmDir]);

  for (const [plugin, pluginDir] of pluginPairs) {
    // skills: <pluginDir>/skills/<name>/SKILL.md
    const skillsDir = path.join(pluginDir, 'skills');
    if (fs.existsSync(skillsDir)) {
      for (const entry of fs.readdirSync(skillsDir, { withFileTypes: true })) {
        if (!entry.isDirectory()) continue;
        const skillFile = path.join(skillsDir, entry.name, 'SKILL.md');
        if (fs.existsSync(skillFile)) {
          skills.set(`${plugin}:${entry.name}`, skillFile);
        }
      }
    }

    // agents: <pluginDir>/agents/<name>.md
    const agentsDir = path.join(pluginDir, 'agents');
    if (fs.existsSync(agentsDir)) {
      for (const entry of fs.readdirSync(agentsDir, { withFileTypes: true })) {
        if (!entry.isFile() || !entry.name.endsWith('.md')) continue;
        const name = entry.name.replace(/\.md$/, '');
        agents.set(`${plugin}:${name}`, path.join(agentsDir, entry.name));
      }
    }

    // commands: <pluginDir>/commands/<name>.md
    const commandsDir = path.join(pluginDir, 'commands');
    if (fs.existsSync(commandsDir)) {
      for (const entry of fs.readdirSync(commandsDir, { withFileTypes: true })) {
        if (!entry.isFile() || !entry.name.endsWith('.md')) continue;
        const name = entry.name.replace(/\.md$/, '');
        commands.set(`${plugin}:${name}`, path.join(commandsDir, entry.name));
      }
    }
  }

  return { skills, agents, commands, plugins: pluginPairs.map(([p]) => p) };
}

// ---------------------------------------------------------------------------
// Reference extraction
// ---------------------------------------------------------------------------

/**
 * Strip fenced code blocks (```...```) and YAML frontmatter from a markdown body.
 * Inline backticks (`...`) are KEPT — many references live in them (e.g., `coordinator:plan`).
 */
function stripCodeFences(content) {
  let out = content;
  if (out.startsWith('---')) {
    const secondDash = out.indexOf('\n---', 3);
    if (secondDash !== -1) out = out.slice(secondDash + 4);
  }
  out = out.replace(/```[\s\S]*?```/g, '');
  out = out.replace(/~~~[\s\S]*?~~~/g, '');
  return out;
}

/**
 * Walk all .md files under a directory tree.
 */
function* walkMarkdown(root, exclude = new Set()) {
  const stack = [root];
  while (stack.length) {
    const dir = stack.pop();
    let entries;
    try { entries = fs.readdirSync(dir, { withFileTypes: true }); }
    catch { continue; }
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === 'node_modules' || entry.name === '.git' || exclude.has(entry.name)) continue;
        stack.push(full);
      } else if (entry.isFile() && entry.name.endsWith('.md')) {
        yield full;
      }
    }
  }
}

/**
 * Extract references from a single markdown file.
 *
 * Returns an array of { kind, ref, line } objects. `kind` is one of:
 *   'qualified'  — "<plugin>:<name>" pattern (could be skill/agent/command)
 *   'subagent'   — subagent_type: "name" (bare name, requires inference)
 *   'command'    — /<name> or /<plugin>:<name> at word boundary
 *   'worker'     — name listed under "## Worker Dispatch Recommendations"
 */
function extractReferences(content, validPluginPrefixes) {
  const refs = [];
  const body = stripCodeFences(content);
  const lines = body.split(/\r?\n/);

  // Build plugin prefix regex alternation.
  const prefixPattern = validPluginPrefixes.map(p => p.replace(/-/g, '\\-')).join('|');

  // Pattern 1 — Qualified refs: `<plugin>:<name>`. Boundary-strict so URLs and time
  // strings ("12:30") don't match. Allow optional leading slash for command form.
  const qualifiedRe = new RegExp(
    `(?<![\\w\\-/:.])\\/?(${prefixPattern}):([a-z][a-z0-9\\-]+)(?![\\w\\-:])`,
    'g'
  );

  // Pattern 2 — subagent_type assignments: subagent_type: "name", subagent_type=name.
  // Require alphanumeric terminal char so docs templates like "holodeck-control:ue-{domain}"
  // don't capture the trailing dash before the placeholder brace.
  const subagentRe = /subagent_type\s*[:=]\s*['"]?([a-z][a-z0-9_:\-]*[a-z0-9])['"]?/g;

  // Pattern 3 — worker bullets inside "## Worker Dispatch Recommendations" blocks.
  // Find the header, then collect lines starting with "- " or "* " until the next heading.
  let inWorkerBlock = false;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^##+\s+Worker Dispatch Recommendations/i.test(line)) {
      inWorkerBlock = true;
      continue;
    }
    if (inWorkerBlock && /^##+\s/.test(line)) {
      inWorkerBlock = false;
    }
    if (inWorkerBlock) {
      const m = line.match(/^\s*[-*]\s+`?([a-z][a-z0-9_\-]+)`?/);
      if (m) refs.push({ kind: 'worker', ref: m[1], line: i + 1 });
    }
  }

  // Apply patterns 1 & 2 over the full body.
  let m;
  while ((m = qualifiedRe.exec(body)) !== null) {
    const lineNum = body.slice(0, m.index).split('\n').length;
    const leadingSlash = m[0].startsWith('/');
    refs.push({
      kind: leadingSlash ? 'command' : 'qualified',
      ref: `${m[1]}:${m[2]}`,
      line: lineNum,
    });
  }
  while ((m = subagentRe.exec(body)) !== null) {
    const lineNum = body.slice(0, m.index).split('\n').length;
    refs.push({ kind: 'subagent', ref: m[1], line: lineNum });
  }

  return refs;
}

// ---------------------------------------------------------------------------
// Resolution
// ---------------------------------------------------------------------------

/**
 * Check whether a reference resolves to a registered artifact.
 *
 * For qualified refs ("<plugin>:<name>"), check across all three maps (skill / agent / command)
 * since the prefix:name namespace is shared at the reference site.
 *
 * For subagent and worker refs (bare names), check across agents in any plugin.
 *
 * For command refs ("/<plugin>:<name>" or "/<name>"), check commands first, then fall back
 * to skills (since /<name> can invoke a skill).
 */
function resolve(ref, kind, artifacts) {
  const { skills, agents, commands } = artifacts;
  if (kind === 'qualified') {
    return skills.has(ref) || agents.has(ref) || commands.has(ref);
  }
  if (kind === 'command') {
    if (commands.has(ref)) return true;
    if (skills.has(ref)) return true;
    // Bare /<name> form (no colon) — match against any plugin's commands or skills.
    if (!ref.includes(':')) {
      for (const key of commands.keys()) if (key.endsWith(`:${ref}`)) return true;
      for (const key of skills.keys()) if (key.endsWith(`:${ref}`)) return true;
    }
    return false;
  }
  if (kind === 'subagent' || kind === 'worker') {
    if (ref.includes(':')) {
      // Qualified ref. If the plugin prefix isn't in our discovered set, treat as
      // out-of-tree (external plugin like holodeck-control) and skip silently.
      const [prefix] = ref.split(':');
      const knownPlugins = new Set(Array.from(agents.keys()).map(k => k.split(':')[0]));
      if (!knownPlugins.has(prefix)) return true;
      return agents.has(ref);
    }
    // Bare-name agent lookup across all plugins.
    for (const key of agents.keys()) if (key.endsWith(`:${ref}`)) return true;
    return false;
  }
  return false;
}

// ---------------------------------------------------------------------------
// Allowlist for known false positives
// ---------------------------------------------------------------------------

const REF_ALLOWLIST = new Set([
  // Historical rename mentions — skill no longer exists but the documented
  // rename note is the load-bearing artifact (tells future readers where
  // the capability went). Body always reads "Replaces/Supersedes/absorbed".
  'coordinator:artifact-consolidation', // absorbed into /update-docs Phase 8b 2026-05-06; 5 callers are rename notes in pipelines/commands
  'coordinator:lesson-triage',          // renamed to coordinator:learn-lessons 2026-05-06; 1 caller is the rename note inside learn-lessons/SKILL.md
  // Version-history documentation of renamed skills in super-skill-architecture.md
  // § Version History — v2.0.0 Breaking Changes (2026-05-07). Not live dispatch refs.
  'coordinator:writing-plans',          // renamed to coordinator:plan 2026-05-07; cited in v2.0.0 rename note
  'coordinator:requesting-code-review', // renamed to coordinator:review-code 2026-05-07; cited in v2.0.0 rename note
  'coordinator:using-git-worktrees',    // removed 2026-05-07 (rule lives in CLAUDE.md); cited in v2.0.0 rename note
  // By-design non-command: the coordinator doctor is a wiki (coordinator-doctor.md) + sentinel
  // script, NOT a slash skill. The wiki itself argues a /coordinator:doctor command "would be
  // bloat for a non-interactive verification surface" — the backticked mention is the false positive.
  'coordinator:doctor',                 // doctor is docs/wiki/coordinator-doctor.md + coordinator-doctor-sentinel.sh, not a skill (2026-05-20)
  // Documented never-existent artifact: the schema-`required` lesson in
  // implementation-standards-by-domain.md cites /deep-research:doctor as the
  // negative example — deep-research shipped a doctor_skill field pointing at a
  // never-existent /deep-research:doctor (2026-06-17). The backticked mention is
  // the load-bearing lesson narrative, not a live dispatch ref.
  'deep-research:doctor',               // never-existent artifact, cited as negative example in schema-required lesson (2026-06-17)
  // Project-specific agent in holodeck consumer repo (plugin/game-dev/agents/schema-migration-auditor.md).
  // The agent exists but lives in the project repo, not the global game-dev plugin — the prefix
  // 'game-dev' is known but the specific agent-id is not resolvable from the coordinator-plugin tree.
  // Reference in docs/wiki/install-surface-completeness.md:97 is a cross-ref advisory, not a dispatch.
  'game-dev:schema-migration-auditor',  // holodeck project-local game-dev agent; coordinator wiki cross-ref only (2026-05-24)
  // Skill demoted to a methodology 2026-05-30 — it collided with native Claude Code vocabulary.
  // References in docs/plans/ are (a) the demotion plan itself (2026-05-30-fan-out-skill-to-methodology-demotion.md),
  // (b) the pre-demotion fan-out doctrine plan (2026-05-27-fan-out-default-doctrine.md), and
  // (c) plan/prior-art sidecars that cite the old skill name as historical context.
  // The skill no longer exists on disk; these are legitimate historical/demotion-record references.
  'coordinator:fan-out',                // demoted to methodology 2026-05-30; remaining refs are historical plan docs
  // FORWARD-reference (not historical): an unimplemented rename plan
  // (docs/plans/2026-06-01-session-complete-rename.md + its sidecars) proposes
  // renaming coordinator:session-end -> coordinator:session-complete. The target
  // skill does not exist yet. Allowlist is a no-op once the rename ships, and
  // harmless if the plan is abandoned (plan doc stays as a historical artifact).
  'coordinator:session-complete',       // forward-ref in unimplemented rename plan (2026-06-01)
  // Renamed to coordinator:workstream-{start,complete} and the deprecation-alias stubs
  // DELETED 2026-06-01. Remaining refs are historical: the workstream/session-complete
  // rename plans + their pre-flight sidecars, the archive completion entries, and the
  // CHANGELOG migration notes. No live dispatch resolves to these names.
  'coordinator:session-start',          // renamed→workstream-start; stub deleted 2026-06-01, refs historical
  'coordinator:session-end',            // renamed→workstream-complete; stub deleted 2026-06-01, refs historical
  // historical reference; command retired 2026-06-08 per repo-setup-consolidation plan.
  // Three callers are all plan-doc substrate counts / coverage-check notes describing the
  // old architecture — not live dispatch instructions.
  'coordinator:bootstrap-repos',        // retired 2026-06-08; refs historical in 2026-05-30 plan:50, 2026-06-08 plan:36, coverage-check:143
]);

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main() {
  const args = parseArgs(process.argv);
  const root = args.root || defaultRoot();
  if (!fs.existsSync(root)) {
    console.error(`Plugin root not found: ${root}`);
    process.exit(2);
  }

  const artifacts = discoverArtifacts(root);
  const { plugins } = artifacts;

  // Sweep every .md file in the tree (not just artifact files — CLAUDE.md, snippets,
  // wiki, docs all reference skills/agents/commands and must stay accurate).
  const violations = []; // { file, line, kind, ref }

  // Exclude dist/ — generated publish-repo snapshots whose CHANGELOGs legitimately
  // name removed/renamed skills as history. Live-dispatch coverage issues in real
  // source are caught in the non-dist tree; publish-sync is verify-dist-publish-repo-sync.sh's job.
  for (const file of walkMarkdown(root, new Set(['dist']))) {
    const content = fs.readFileSync(file, 'utf-8');
    const refs = extractReferences(content, plugins);
    for (const r of refs) {
      if (REF_ALLOWLIST.has(r.ref)) continue;
      if (!resolve(r.ref, r.kind, artifacts)) {
        violations.push({ file: path.relative(root, file), ...r });
      }
    }
  }

  // Emit.
  if (args.json) {
    process.stdout.write(JSON.stringify({
      ok: violations.length === 0,
      summary: {
        skills: artifacts.skills.size,
        agents: artifacts.agents.size,
        commands: artifacts.commands.size,
        violations: violations.length,
      },
      violations,
    }, null, 2));
    process.stdout.write('\n');
  } else {
    console.log(`# verify-coverage report`);
    console.log(``);
    console.log(`Plugin root: \`${root}\``);
    console.log(`Plugins: ${plugins.join(', ')}`);
    console.log(`Registered: ${artifacts.skills.size} skills, ${artifacts.agents.size} agents, ${artifacts.commands.size} commands`);
    console.log(``);
    if (violations.length === 0) {
      console.log(`OK — every reference resolves.`);
    } else {
      console.log(`Found ${violations.length} orphan reference(s):`);
      console.log(``);
      // Group by kind for readability.
      const byKind = {};
      for (const v of violations) (byKind[v.kind] ||= []).push(v);
      for (const kind of Object.keys(byKind).sort()) {
        console.log(`## ${kind.toUpperCase()}_ORPHANED (${byKind[kind].length})`);
        console.log(``);
        for (const v of byKind[kind]) {
          console.log(`- \`${v.ref}\`  —  ${v.file}:${v.line}`);
        }
        console.log(``);
      }
      console.log(`Fix: add the referenced artifact, or correct the reference. If the reference is`);
      console.log(`a known false positive, add it to REF_ALLOWLIST in bin/verify-coverage.js with a`);
      console.log(`one-line rationale.`);
    }
  }

  if (violations.length > 0 && !args.reportOnly) process.exit(1);
  process.exit(0);
}

main();
