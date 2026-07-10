#!/usr/bin/env node
'use strict';
/**
 * normalize-handoff-frontmatter.js — backfill and canonicalize active handoff frontmatter.
 *
 * Spec backlink: docs/plans/2026-05-29-handoff-tracker-renderer.md § Chunk 5
 *               docs/plans/2026-07-03-fleet-deliverable-spine-identity-and-facets.md § C3c
 *
 * Operates exclusively on `state/handoffs/*.md` in the repo root (NEVER
 * `archive/handoffs/` — archived files are immutable history).
 *
 * Normalizations applied:
 *   - `created` → strip any ISO time component; keep bare `YYYY-MM-DD`
 *   - `pickup_ready: "true"` / `pickup_ready: "false"` → unquoted bare bool
 *   - `category:` backfilled as `uncategorized` when absent (optional keyword
 *     heuristic applied — see matchCategory)
 *   - `summary:` backfilled from the H1/title (truncated to ≤140 chars) when absent
 *   - `deliverable_id:` minted (dlv-<slug>-<6hex>) when absent; carried unchanged
 *     when present (D1 carry rule: never re-mint an existing id)
 *   - `initiative:` inserted as YAML null when absent (D9 present-as-null: key
 *     present carrying null so rag/tc-5 inserts a column value; absent = schema gap)
 *
 * IMPORTANT: only the six field names above are touched. Key order and all
 * other frontmatter content are preserved byte-for-byte.
 *
 * Usage:
 *   normalize-handoff-frontmatter.js [--write] [--root <path>]
 *
 * --write applies changes to disk (default is dry-run: print diff summary, no writes).
 * Exit codes: 0 always (non-empty stdout summarises changes).
 */

const fs     = require('fs');
const path   = require('path');
const os     = require('os');
const crypto = require('crypto');
const { execSync, spawnSync } = require('child_process');

// ---------------------------------------------------------------------------
// Frontmatter text helpers (minimal regex-based; preserves key order)
// ---------------------------------------------------------------------------

/**
 * splitFrontmatter — split a file's content into YAML frontmatter text and body.
 * Returns null when the file has no valid frontmatter block.
 *
 * Intentionally kept as a simple text split (not a full YAML parse) so we can
 * reconstruct the file with byte-identical whitespace outside the changed fields.
 */
function splitFrontmatter(content) {
  // Tolerate an optional leading preamble (blank lines + HTML comment blocks) before the
  // opening `---`; installer-seeded batons carry a provenance comment. Captured in
  // `preamble`, reassembled verbatim on write.
  let preamble = '';
  if (!content.startsWith('---')) {
    const pre = /^(?:[ \t]*\r?\n|[ \t]*<!--[\s\S]*?-->[ \t]*\r?\n?)+/.exec(content);
    if (!pre) return null;
    const after = content.slice(pre[0].length);
    if (!after.startsWith('---')) return null;
    preamble = pre[0];
    content = after;
  }
  const afterFirst = content.slice(3);
  const firstNewline = afterFirst.indexOf('\n');
  if (firstNewline === -1) return null;
  const rest = afterFirst.slice(firstNewline + 1);
  // [ \t]* — NOT \s* which would eat body blank lines.
  const closeRe = /^---[ \t]*$/m;
  const closeMatch = closeRe.exec(rest);
  if (!closeMatch) return null;
  const fmText = rest.slice(0, closeMatch.index);
  // Everything after `---` (including the newline that follows it).
  const bodyWithLeadingNewline = rest.slice(closeMatch.index + closeMatch[0].length);
  return { preamble, fmText, bodyWithLeadingNewline };
}

/**
 * readFmField — return the raw value string for `key:` in frontmatter text,
 * or null when the key is absent.
 */
function readFmField(fmText, key) {
  const re = new RegExp(`^${key}:\\s*(.*?)\\s*$`, 'm');
  const m = re.exec(fmText);
  return m ? m[1].trim() : null;
}

/**
 * replaceFmField — replace the value of an existing `key:` line in frontmatter text.
 * Returns the updated frontmatter text.
 *
 * Negative-spec: does NOT insert a new line when the key is absent — call
 * insertFmField for that.
 */
function replaceFmField(fmText, key, value) {
  const re = new RegExp(`^(${key}:\\s*).*$`, 'm');
  return fmText.replace(re, `$1${serializeYamlScalar(value)}`);
}

/**
 * insertFmField — append `key: value` to the end of the frontmatter block.
 * Used when the key is absent and we need to add it.
 */
function insertFmField(fmText, key, value) {
  const trimmed = fmText.replace(/\s+$/, '');
  return `${trimmed}\n${key}: ${serializeYamlScalar(value)}\n`;
}

/**
 * serializeYamlScalar — single-quote a value that contains YAML structural
 * characters; pass through safe values unquoted; serialize null as the bare
 * YAML null literal so consumers get an unambiguous absent-vs-null signal.
 *
 * Negative-spec: does NOT handle multi-line values; frontmatter fields
 * normalised by this script are all single-line scalars.
 */
function serializeYamlScalar(value) {
  // D9 present-as-null: emit the bare YAML literal so rag/tc-5 gets a typed null,
  // not an absent key (which maps to a missing column in relational stores).
  if (value === null) return 'null';
  const needsQuoting = /[#:{}\[\],&*!|>"'%@`]/.test(value) ||
                       value.startsWith('-') ||
                       value.startsWith('?') ||
                       value.startsWith(' ');
  if (!needsQuoting) return value;
  return `'${value.replace(/'/g, "''")}'`;
}

// ---------------------------------------------------------------------------
// Deliverable-id helpers (C3c — spine identity threading)
// ---------------------------------------------------------------------------

/**
 * deriveSlugFromPath — extract a normalizer-suitable slug from a handoff file path.
 * Returns the basename without the `.md` extension; used as the slug when minting
 * a new deliverable_id for pre-existing handoffs that predate the spine.
 *
 * Example: "state/handoffs/2026-07-03-my-handoff.md" → "2026-07-03-my-handoff"
 */
function deriveSlugFromPath(filePath) {
  return path.basename(filePath, '.md');
}

/**
 * mintDeliverableIdFromSlug — mint a dlv-<slug>-<6hex> deliverable_id.
 *
 * Mirrors the slug path in bin/mint-deliverable-id.sh (D1, C3a) using Node's
 * built-in crypto instead of bash, so the JS normalizer is self-contained without
 * a bash >=4 dependency. The hash input and output format are identical:
 *   6hex = SHA-1(slug|epochMs|pid|random)[0:6]
 *
 * Negative-spec: does NOT implement the carry path (caller's responsibility) or
 * the stub path (dlv-<stub_id> — only coordinator-doc-new/roadmap-planning use that).
 * The id is opaque downstream; no consumer parses the suffix.
 */
function mintDeliverableIdFromSlug(slug) {
  const entropy = `${slug}|${Date.now()}|${process.pid}|${Math.floor(Math.random() * 65536)}`;
  const hex6 = crypto.createHash('sha1').update(entropy).digest('hex').slice(0, 6);
  return `dlv-${slug}-${hex6}`;
}

// ---------------------------------------------------------------------------
// Category heuristic
// ---------------------------------------------------------------------------

/**
 * matchCategory — best-effort keyword match on a handoff title.
 * Returns one of the schema-valid category enum values, or 'uncategorized'
 * when no keyword fires.
 *
 * HARD CONSTRAINT: every return value MUST be a member of the category enum in
 * schemas/handoff.yaml — [roadmap, infra, bug, docs, research, refactor, uncategorized].
 * Emitting a value outside the enum makes the normalized file fail schema
 * validation (the validator enum-checks category whenever it is present).
 * Intentionally conservative — only unambiguous category signals are mapped;
 * kind/lifecycle words (spinoff, recovery, review, release) are NOT categories
 * and fall through to 'uncategorized', the safe default.
 */
function matchCategory(title) {
  const t = (title || '').toLowerCase();
  if (/\broadmap\b|\bsprint\b/.test(t))                                  return 'roadmap';
  if (/\brefactor\b|\bcleanup\b|\bconsolidat/.test(t))                   return 'refactor';
  if (/\bbug\b|\bhotfix\b|\bregression\b/.test(t))                       return 'bug';
  if (/\bresearch\b|\bspike\b|\binvestigat/.test(t))                     return 'research';
  if (/\bdoc(?:s|umentation)?\b|\bwiki\b/.test(t))                       return 'docs';
  if (/\binfra(?:structure)?\b|\binstall\b|\bhook\b|\bpipeline\b|\bci\b/.test(t)) return 'infra';
  return 'uncategorized';
}

// ---------------------------------------------------------------------------
// Per-file normalizer
// ---------------------------------------------------------------------------

/**
 * normalizeOne — compute the normalised content for a single file.
 * Returns `{ rebuilt, changes }` when drift is detected, or null when the
 * file is already clean (idempotent: second run always returns null).
 *
 * @param {string} filePath  Absolute path to the handoff file.
 * @returns {{ rebuilt: string, changes: string[] } | null}
 */
function normalizeOne(filePath) {
  const original = fs.readFileSync(filePath, 'utf8');
  const split = splitFrontmatter(original);
  if (!split) return null;

  let fmText = split.fmText;
  const changes = [];

  // ── 1. created: strip ISO time component ──────────────────────────────
  const createdRaw = readFmField(fmText, 'created');
  if (createdRaw) {
    // Matches `2026-05-28T11:16:48Z` or `2026-05-28T11:16:48` etc.
    const isoMatch = /^(\d{4}-\d{2}-\d{2})[T ]/.exec(createdRaw);
    if (isoMatch) {
      const bare = isoMatch[1];
      fmText = replaceFmField(fmText, 'created', bare);
      changes.push(`created: "${createdRaw}" → "${bare}"`);
    }
  }

  // ── 2. pickup_ready: unquote boolean strings ───────────────────────────
  const pickupRaw = readFmField(fmText, 'pickup_ready');
  if (pickupRaw !== null) {
    // Quoted `"true"` or `"false"` — strip quotes by writing the bare value.
    if (pickupRaw === '"true"' || pickupRaw === "'true'") {
      fmText = replaceFmField(fmText, 'pickup_ready', 'true');
      changes.push(`pickup_ready: ${pickupRaw} → true`);
    } else if (pickupRaw === '"false"' || pickupRaw === "'false'") {
      fmText = replaceFmField(fmText, 'pickup_ready', 'false');
      changes.push(`pickup_ready: ${pickupRaw} → false`);
    }
    // bare `true`/`false` already correct — no-op
  }

  // ── 3. category: backfill when absent ─────────────────────────────────
  const categoryRaw = readFmField(fmText, 'category');
  if (categoryRaw === null) {
    const title = readFmField(fmText, 'title') || '';
    const cat = matchCategory(title);
    fmText = insertFmField(fmText, 'category', cat);
    changes.push(`category: (absent) → ${cat}`);
  }

  // ── 4. summary: backfill when absent ──────────────────────────────────
  const summaryRaw = readFmField(fmText, 'summary');
  if (summaryRaw === null) {
    // Extract text from the first H1 in the body; fall back to `title:` field.
    let summaryText = '';
    const h1Match = /^#\s+(.+)$/m.exec(split.bodyWithLeadingNewline);
    if (h1Match) {
      summaryText = h1Match[1].trim();
    } else {
      summaryText = readFmField(fmText, 'title') || '';
    }
    // Truncate to ≤140 chars; strip inline markdown (bold, code, links).
    summaryText = summaryText
      .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')   // [text](url) → text
      .replace(/`([^`]+)`/g, '$1')               // `code` → code
      .replace(/\*\*([^*]+)\*\*/g, '$1')         // **bold** → bold
      .replace(/\*([^*]+)\*/g, '$1')             // *italic* → italic
      .trim();
    if (summaryText.length > 140) summaryText = summaryText.slice(0, 137) + '...';
    if (summaryText) {
      fmText = insertFmField(fmText, 'summary', summaryText);
      changes.push(`summary: (absent) → "${summaryText.slice(0, 60)}${summaryText.length > 60 ? '…' : ''}"`);
    }
  }

  // ── 5. deliverable_id: carry if present; mint if absent (D1 carry rule) ──
  // Carry rule (D1): never re-mint an id that already exists — carrying preserves
  // the join key across downstream artifacts. Mint rule: absent → dlv-<slug>-<6hex>.
  // Log is embedded in changes only for the mint path (carry = no drift, not reported).
  const deliverableIdRaw = readFmField(fmText, 'deliverable_id');
  if (deliverableIdRaw === null) {
    const slug = deriveSlugFromPath(filePath);
    const minted = mintDeliverableIdFromSlug(slug);
    fmText = insertFmField(fmText, 'deliverable_id', minted);
    changes.push(`deliverable_id: (absent) → ${minted} [mint-from-slug]`);
  }
  // If present: carry unchanged — not a drift condition; no changes entry emitted.

  // ── 6. initiative: present-as-null when absent (D9 discipline) ────────────
  // initiative is a nullable FK to a lightweight parent entity (D2). D9 mandates
  // key-present-carrying-null (not key-absent) so rag/tc-5 inserts a typed null
  // in every column without absent-vs-null ambiguity. null = not yet assigned.
  const initiativeRaw = readFmField(fmText, 'initiative');
  if (initiativeRaw === null) {
    fmText = insertFmField(fmText, 'initiative', null);
    changes.push(`initiative: (absent) → null`);
  }
  // If present (including the literal "null" value): carry — no drift.

  if (changes.length === 0) return null;

  const fmTextNormalized = fmText.endsWith('\n') ? fmText : fmText + '\n';
  const rebuilt = `${split.preamble || ''}---\n${fmTextNormalized}---${split.bodyWithLeadingNewline}`;
  return { rebuilt, changes };
}

// ---------------------------------------------------------------------------
// CLI helpers
// ---------------------------------------------------------------------------

function parseArgs(argv) {
  // Default: dry-run (--write must be explicit)
  const opts = { dryRun: true, root: null };
  const args = argv.slice(2);
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === '--write')   opts.dryRun = false;
    else if (a === '--dry-run') opts.dryRun = true;  // explicit no-op (already default)
    else if (a === '--root') opts.root = args[++i];
    else {
      process.stderr.write(`Unknown argument: ${a}\n`);
      process.exit(1);
    }
  }
  return opts;
}

function detectRoot(specified) {
  if (specified) return path.resolve(specified);
  try {
    return execSync('git rev-parse --show-toplevel', {
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
    }).trim();
  } catch {
    return process.cwd();
  }
}

function walkHandoffsDir(absDir) {
  // CONSTRAINT: active handoffs only — state/handoffs/*.md, NOT archive/handoffs/.
  // Flat glob only: no recursion into subdirectories, so state/handoffs/archive/
  // (the example-game-repo legacy pattern) is also excluded.
  if (!fs.existsSync(absDir)) return [];
  const stat = fs.statSync(absDir);
  if (!stat.isDirectory()) return [];
  return fs.readdirSync(absDir)
    .filter(f => f.endsWith('.md'))
    .map(f => path.join(absDir, f));
}

// ---------------------------------------------------------------------------
// DR-210 facade seam helpers (strang-07 C7)
//
// Three-state routing model (Design pin 3 — do NOT re-open):
//   State 1 (seam absent on disk) → legacy_normalize() runs the existing JS core.
//   State 2 (seam present, invoke success) → coordinator_core.invoke spawned per-call (~59ms).
//   State 3 (seam present, invoke failure) → hard non-zero exit, NO fallback.
//
// Trigger is BINARY disk-presence of coordinator_core.invoke (importability),
// NEVER a liveness probe.  DR-215: spawn-per-call; no daemon, no socket.
//
// Negative-spec: NEVER calls `machine-local get` as a CLI (cold-shell hazard,
// Design pin 4).  EXAMPLE_ORCHESTRATION_HUB_ROOT resolution uses direct file reads only.
// ---------------------------------------------------------------------------

/**
 * resolveExampleOrchestrationHubRoot — resolve the example-orchestration-hub sibling-repo root without spawning
 * the machine-local CLI (Design pin 4 cold-shell constraint).
 *
 * Resolution ladder (mirrors coordinator-example-orchestration-hub-root.sh § rungs 1–2 in JS):
 *   1. EXAMPLE_ORCHESTRATION_HUB_ROOT env var already set → return as-is.
 *   2. Direct TOML parse of ~/.claude/machine-local/registry.local.toml →
 *      look for a `"repos.example_orchestration_hub_repo" = '...'` line and return the path.
 *
 * Returns the resolved path string, or null when the root cannot be determined.
 * Logs a notice to stderr on null so callers can degrade gracefully.
 *
 * Grep-gate: this function MUST NOT contain the string 'machine-local get'
 * anywhere in its body (P3 cold-fallback constraint).
 */
function resolveExampleOrchestrationHubRoot() {
  // Rung 1: env var fast-path (§4b idempotency guard).
  if (process.env.EXAMPLE_ORCHESTRATION_HUB_ROOT) return process.env.EXAMPLE_ORCHESTRATION_HUB_ROOT;

  // Rung 2: direct file read of the machine-local registry TOML.
  // The TOML key format is: "repos.example_orchestration_hub_repo" = '/path/to/example-orchestration-hub'
  // We parse it with a targeted regex rather than a full TOML parser to avoid
  // any npm dependency; the registry format is machine-written and stable.
  const registryPath = path.join(os.homedir(), '.claude', 'machine-local', 'registry.local.toml');
  try {
    const text = fs.readFileSync(registryPath, 'utf8');
    // Match: "repos.example_orchestration_hub_repo" = '/path'  or  "repos.example_orchestration_hub_repo" = "/path"
    // Review: code-reviewer F6 — use separate alternatives to require matched delimiters
    // (single-quoted or double-quoted); mixed open/close quotes are not valid TOML.
    // Also avoids silently returning null for paths containing a single-quote character.
    const mSingle = /^"repos\.example_orchestration_hub_repo"\s*=\s*'([^']*)'/m.exec(text);
    const mDouble = /^"repos\.example_orchestration_hub_repo"\s*=\s*"([^"]*)"/m.exec(text);
    const m = mSingle || mDouble;
    if (m) return m[1].trim();
  } catch {
    // File absent or unreadable — fall through to null.
  }

  process.stderr.write(
    'normalize-handoff-frontmatter: cannot resolve EXAMPLE_ORCHESTRATION_HUB_ROOT — ' +
    '"repos.example_orchestration_hub_repo" not found in machine-local registry.\n'
  );
  return null;
}

/**
 * seamPresent — returns true when coordinator_core.invoke is importable on disk.
 *
 * Tests coordinator_core.invoke importability with EXAMPLE_ORCHESTRATION_HUB_ROOT on PYTHONPATH
 * (mirrors _sf_seam_present in strangler-facade.sh; DR-215: probes invoke, not
 * the retired coordinator_core.client).  Returns false on any non-zero exit or
 * spawn error (treats the seam as absent, routes to legacy).
 *
 * This is the ONLY gate for the legacy vs. native routing decision.
 */
function seamPresent(example_orchestration_hubRoot) {
  const pythonpath = example_orchestration_hubRoot +
    (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : '');
  const result = spawnSync(
    'python3',
    ['-c', 'import coordinator_core.invoke'],
    { env: { ...process.env, PYTHONPATH: pythonpath }, stdio: 'pipe' }
  );
  return result.status === 0 && !result.error;
}

// ---------------------------------------------------------------------------
// Legacy normalize — pre-facade main body, preserved byte-identical.
// Called ONLY on State 1 (coordinator_core.invoke absent on disk).
// Negative-spec: MUST NOT be called when the seam is present (State 2/3).
// ---------------------------------------------------------------------------

function legacy_normalize() {
  const opts = parseArgs(process.argv);
  const root = detectRoot(opts.root);
  const handoffsDir = path.join(root, 'state', 'handoffs');

  const files = walkHandoffsDir(handoffsDir);
  const results = [];

  for (const file of files) {
    let out;
    try {
      out = normalizeOne(file);
    } catch (err) {
      process.stderr.write(`ERROR ${path.relative(root, file).replace(/\\/g, '/')}: ${err.message}\n`);
      process.exitCode = 1;
      continue;
    }
    if (!out) continue;

    results.push({
      file: path.relative(root, file).replace(/\\/g, '/'),
      changes: out.changes,
    });

    if (!opts.dryRun) {
      fs.writeFileSync(file, out.rebuilt, 'utf8');
    }
  }

  if (results.length === 0) {
    process.stderr.write('No drift found in active handoffs.\n');
    return;
  }

  const verb = opts.dryRun ? 'Would update' : 'Updated';
  for (const r of results) {
    process.stdout.write(`${verb} ${r.file}\n`);
    for (const c of r.changes) process.stdout.write(`  ${c}\n`);
  }
  process.stdout.write(`\n${verb.toLowerCase()} ${results.length} file(s).\n`);
}

// ---------------------------------------------------------------------------
// main — DR-210/DR-215 three-state facade router (strang-07 C7).
//
// When the example-orchestration-hub seam is present: routes handoff.normalize to coordinator_core.invoke
// (spawn-per-call; DR-215 retired the UDS daemon and coordinator_core.client).
// When absent: calls legacy_normalize() (the original JS core) unchanged.
// CLI name, flags, and exit semantics are preserved on both paths.
// ---------------------------------------------------------------------------

function main() {
  const example_orchestration_hubRoot = resolveExampleOrchestrationHubRoot();

  // State 1: seam absent on disk → legacy JS core.
  // seamPresent() is skipped when EXAMPLE_ORCHESTRATION_HUB_ROOT is unresolvable (defensive: treat
  // as absent rather than hard-erroring on a machine that has no example-orchestration-hub install).
  if (!example_orchestration_hubRoot || !seamPresent(example_orchestration_hubRoot)) {
    legacy_normalize();
    return;
  }

  // States 2 / 3: seam present → route to coordinator_core.invoke (DR-215).
  // parseArgs + detectRoot are called here so the invoke subprocess receives the
  // resolved, normalised flag values (not raw argv strings).
  const opts = parseArgs(process.argv);
  const root = detectRoot(opts.root);
  const params = JSON.stringify({ write: !opts.dryRun, root: root });

  const pythonpath = example_orchestration_hubRoot +
    (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : '');

  // Negative-spec (stdout format divergence): stdout on the native path is the raw
  // JSON-RPC envelope from coordinator_core.invoke; the legacy prose format
  // ("No drift found" / "updated N file(s)") is NOT preserved on State-2.
  // Any caller that parses stdout for legacy prose strings will silently break on State-2.
  // Review: code-reviewer — F4: documented stdout-format divergence between native and legacy paths.
  const result = spawnSync(
    'python3',
    ['-m', 'coordinator_core.invoke', 'handoff.normalize', params, '--repo', root],
    {
      env: { ...process.env, PYTHONPATH: pythonpath },
      stdio: 'inherit',
    }
  );

  if (result.error) {
    // Spawn itself failed — hard error, no fallback (State 3 shape).
    process.stderr.write(
      `normalize-handoff-frontmatter: invoke spawn error: ${result.error.message}\n`
    );
    process.exit(3);
  }

  // State 2 → invoke exits 0.  State 3 → invoke exits non-zero.
  // Propagate unconditionally; NEVER fall back to legacy_normalize() here.
  // status is null if killed by signal (result.error is unset in that case); fall back to 3.
  // Review: code-reviewer — F7: clarified that ?? 3 guards the signal-kill case, not dead code.
  process.exit(result.status ?? 3);
}

if (require.main === module) main();

module.exports = { normalizeOne, splitFrontmatter, readFmField, replaceFmField, insertFmField, matchCategory, deriveSlugFromPath, mintDeliverableIdFromSlug, resolveExampleOrchestrationHubRoot, seamPresent, legacy_normalize };
