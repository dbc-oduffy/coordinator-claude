'use strict';
/**
 * validate-frontmatter-schema.js — PreToolUse hook that surfaces frontmatter-schema
 * violations to the agent before a Write/Edit/MultiEdit lands on a tracked-record file.
 *
 * Spec backlink: archive/specs/2026-05-01-portable-ideas-from-obsidian-research.md §W1/Validator
 * Spec backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 5
 * Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § Chunk G (routing-mismatch branch, own-inbox path update)
 *
 * Default mode is WARN: emits the violation as additionalContext so the agent sees
 * the schema gripe but the write still proceeds. Strict mode (COORDINATOR_SCHEMA_STRICT=1)
 * restores the original deny behavior — the write is blocked. Frontmatter-schema'd
 * files are validated against their whole prospective content; lessons (inline-tag)
 * files are validated only on the written delta (see the inline-tag branch in main()
 * for the rationale and the by-design whole-file coverage gap).
 *
 * Reads Claude PreToolUse JSON from stdin. Exits 0 in all cases (hook contract).
 *
 * Negative-spec: this hook NEVER exits non-zero. Infra failures (schema load, repo
 * root resolution, file read) are logged to stderr and silently allowed — never block
 * on infra. The hook double-fails intentionally on Edit mismatches by falling through
 * silent (let Edit fail on its own merits per the Staff Engineer R1 finding 0).
 *
 * Design-as-offers — hand-rolling catch (Chunk 5):
 * When a Write/Edit targets a memo-shaped file at a non-canonical location (i.e., a
 * path containing /memos/ OR content with free-form To:/From: header lines that are
 * NOT valid YAML frontmatter), this hook emits an additionalContext offer pointing at
 * the cross-repo-memo CLI. A correct write to cross-repo/[0-9]*.md stays SILENT —
 * the existing schema-validation path handles it. The hook never blocks (exit 0 always).
 */

const fs = require('fs');
const path = require('path');
const { execSync, execFileSync } = require('child_process');
let _schemaLib;
try {
  _schemaLib = require('../../bin/lib/schema.js');
} catch (err) {
  process.stderr.write(`validate-frontmatter-schema: cannot load schema lib (${err && err.message}) — skipping validation (never block on infra)\n`);
  process.exit(0);
}
const { loadSchemas, matchSchema, matchSchemaForPath, parseFrontmatter, validateFrontmatter, validateLessonsFile, parseYaml } = _schemaLib;

// C2 lineage-reachability pass (write-time hard-reject) reuses walk-handoff-dag.js's
// promoted _resolveTarget rather than duplicating resolution logic.
// Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C2
// Fail-open on load error (mirrors the schema-lib guard above) — never block on infra.
let _checkLineageReachability = null;
try {
  ({ checkLineageReachability: _checkLineageReachability } = require('../../bin/lib/walk-handoff-dag.js'));
} catch (err) {
  process.stderr.write(`validate-frontmatter-schema: cannot load walk-handoff-dag lib (${err && err.message}) — C2 reachability pass disabled (never block on infra)\n`);
}

// ---------------------------------------------------------------------------
// Manifest load — schemas/coordinator-registry.manifest.json
//
// Replaces three former hand-authored literal registries in this file
// (REPO_BASENAME_TO_EM_SHORTNAME, SCAFFOLD_OFFER_MAP, KIND_OFFER_OVERRIDE) and
// the identity Set _CENTRAL_EM_IDS. All four are built from the manifest at module
// load so a single edit to the manifest keeps all
// consumers in sync.
//
// On failure: write a diagnostic to stderr and process.exit(0) — never continue
// with empty maps. An empty _CENTRAL_EM_IDS would misfire routing offers for
// correctly-addressed central memos (the exact failure mode this hook's Windows
// load-crash history made concrete). Mirrors the schema.js guard pattern above.
// ---------------------------------------------------------------------------
const _MANIFEST_PATH = path.join(__dirname, '..', '..', 'schemas', 'coordinator-registry.manifest.json');
let _manifest;
try {
  _manifest = JSON.parse(fs.readFileSync(_MANIFEST_PATH, 'utf8'));
} catch (err) {
  process.stderr.write(`validate-frontmatter-schema: cannot load coordinator-registry.manifest.json (${err && err.message}) — skipping validation (never block on infra)\n`);
  process.exit(0);
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SCHEMAS_DIR = path.join(__dirname, '../../schemas');

// ---------------------------------------------------------------------------
// Cross-repo own-inbox guard — alias map
//
// Derives from schemas/coordinator-registry.manifest.json (identity.repoAliases).
//
// Spec backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md
// Negative-spec: do NOT shell out to cross-repo-memo or machine-local — this must be
// a pure in-process lookup so the hook is fast and offline-safe.
// ---------------------------------------------------------------------------

/** Maps repo directory basename → canonical em-id shortname (pre-suffix).
 * Built from manifest.identity.repoAliases at module load.
 * Only entries whose doctrine name diverges from the repo basename live here.
 * Convention-covered repos (basename→dashes-em) need no entry.
 */
// review F1 — declared let; assigned in the try/catch guard below (prevents TypeError on
// a structurally-valid-but-field-absent manifest from exiting the hook with code 1,
// which would violate the "NEVER exits non-zero" negative-spec).
let REPO_BASENAME_TO_EM_SHORTNAME;

// ---------------------------------------------------------------------------
// Scaffold offer map — schema name → coordinator-doc-new --type token
//
// Spec backlink: docs/plans/2026-06-29-cli-scaffold-deterministic-docs.md § C0a / D2
//
// Keys are schemaName values returned by matchSchema(); values carry the
// coordinator-doc-new --type token and a flag marking sidecar types (which
// require --plan <stem> derived from the new-file path).
//
// Built from manifest.docTypes where offerable === true. Excluded entries
// (offerable: false) and their reasons live in the manifest's excludeReason field.
// spinoff/spinoff-roadmap share the 'handoff' schema glob but are disambiguated
// by frontmatter.kind via KIND_OFFER_OVERRIDE below.
//
// Derives from schemas/coordinator-registry.manifest.json — see docTypes[].offerable.
// review F1 — declared let; assigned in the try/catch guard below.
let SCAFFOLD_OFFER_MAP;

// ---------------------------------------------------------------------------
// Kind-first offer override — schemaName cannot disambiguate kinds that share a
// schema. handoff/spinoff/spinoff-roadmap all resolve to schemaName 'handoff'
// (identical state/handoffs/*.md glob), so the SCAFFOLD_OFFER_MAP['handoff'] entry
// would offer --type handoff for a hand-rolled spinoff — steering the EM to the
// wrong scaffolder and letting spinoff-specific frontmatter (summary:, category
// enum) drift (observed 2026-06-30). When the prospective content carries one of
// these kinds, its specific --type takes precedence over the schemaName lookup.
//
// Mirrors matchSchema()'s kind-first, glob-fallback philosophy at the offer layer.
//
// Derives from schemas/coordinator-registry.manifest.json — see kindOfferOverride.
//
// Spec backlink: docs/plans/2026-06-29-cli-scaffold-deterministic-docs.md § C0a (kind disambiguation)
// review F1 — declared let; assigned in the try/catch guard below.
let KIND_OFFER_OVERRIDE;
// Central receiver identities — declared let here so the try/catch below can assign them.
// review F1 — _CENTRAL_EM_IDS moved from its former location (after the function definitions)
// into this single guarded block so all four constructions share one catch that exits 0 on
// structural manifest defects.
let _CENTRAL_EM_IDS;

// ---------------------------------------------------------------------------
// review F1 — All five registry constructions in a single try/catch.
// Covers the case where the manifest is valid JSON but is missing a field
// (e.g. identity.repoAliases undefined): Object.entries(undefined) or
// _manifest.identity.repoAliases.map(...) would throw TypeError at module
// load, causing Node to exit code 1 without this guard and blank-denying
// every Write/Edit until the hook is fixed — a direct contract violation.
// Mirrors the manifest-load guard above (same stderr diagnostic + exit 0).
// ---------------------------------------------------------------------------
try {
  REPO_BASENAME_TO_EM_SHORTNAME = Object.fromEntries(
    _manifest.identity.repoAliases.map(a => [a.dirBasename, a.shortname])
  );
  SCAFFOLD_OFFER_MAP = Object.fromEntries(
    _manifest.docTypes
      .filter(d => d.offerable === true)
      .map(d => [d.schemaName, { type: d.type, isSidecar: d.isSidecar }])
  );
  KIND_OFFER_OVERRIDE = Object.fromEntries(
    Object.entries(_manifest.kindOfferOverride).map(([kind, entry]) => [
      kind,
      { type: entry.type, isSidecar: entry.isSidecar, manualArgs: entry.manualArgs, authoringHint: entry.authoringHint },
    ])
  );
  // Central receiver IDs — a memo `to: claude-central-em` (or aliases) landing
  // in ~/.claude is a routing MATCH, not a mismatch. Consistent with CLI's
  // _CENTRAL_RECEIVER_IDS and the B2 fix that makes central an explicit receiver.
  // An empty centralReceiverIds set would misfire routing offers for correctly-addressed
  // central memos (the exact failure mode noted in the header comment above).
  // Derives from schemas/coordinator-registry.manifest.json — see identity.centralReceiverIds.
  _CENTRAL_EM_IDS = new Set(_manifest.identity.centralReceiverIds);
} catch (err) {
  process.stderr.write(
    `validate-frontmatter-schema: manifest structure invalid (${err && err.message}) — skipping validation (never block on infra)\n`
  );
  process.exit(0);
}

// ---------------------------------------------------------------------------
// Central landing-repo path — resolved via machine-local once per invocation.
//
// Spec backlink: docs/plans/2026-07-04-central-identity-flip.md § C3
//
// The central landing repo is now the DoE-claude repo (repos.doe_claude), not
// ~/.claude. This is a path-anchor: we compare realpath(repoRoot) to the
// realpath of the machine-local-registered repos.doe_claude path, rather than
// checking the basename against a hardcoded set.
//
// rc=0 → key found → use the resolved path
// rc=1 → cleanly absent (key not registered; normal on non-DoE machines) → fail-open silently
// rc≥2 → operational failure (Python crash, TOML error) → fail-open with debug note to stderr
//
// Negative-spec (subsystem exception): this is the ONLY shell-out in this hook.
// The `emIdForBasename` lookup (REPO_BASENAME_TO_EM_SHORTNAME) remains a pure
// in-process manifest lookup per the REPO_BASENAME_TO_EM_SHORTNAME negative-spec above.
// This exception is load-bearing: the DoE-claude dir basename ("DoE-claude") does NOT
// follow the standard <key>-em convention (it would yield "DoE-claude-em", not
// "claude-central-em"), so a manifest-based lookup cannot anchor the central identity.
// The machine-local path is the authoritative, per-machine, portable anchor.
//
// Fail-open coherence: under machine-local failure, thisEmId reverts to emIdForBasename
// ("DoE-claude-em"). Because the central offer itself also fail-opens (no central path
// available → no central match), the degraded own-inbox guard is moot. This is a single
// coherent degrade — do NOT harden the own-inbox guard fail-open path in isolation.
// ---------------------------------------------------------------------------
let _DOE_CLAUDE_PATH = null; // null = not available / unresolvable on this machine

(function resolveDoeClaude() {
  try {
    const rawPath = execFileSync(
      'machine-local', ['get', 'repos.doe_claude'],
      { encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    ).trim();
    if (rawPath) {
      // Canonicalize to resolve symlinks so realpath comparisons work reliably.
      _DOE_CLAUDE_PATH = fs.realpathSync(rawPath);
    }
    // rc=0 but empty output → treat as absent; _DOE_CLAUDE_PATH stays null.
  } catch (e) {
    if (e && e.code === 'ENOENT') {
      // ENOENT → machine-local binary not found in PATH; no process ran.
      // Review: code-reviewer — F4: distinct ENOENT branch avoids confusing rc=null diagnostic
      process.stderr.write(
        `validate-frontmatter-schema: machine-local binary not found in PATH — central path anchor unavailable; central detection degraded (no central routing offer or own-inbox central guard until machine-local is healthy)\n`
      );
    } else if (e && e.status !== 1) {
      // rc≥2 → operational failure (Python crash, malformed TOML, binary missing).
      // Emit debug note so the operator isn't left guessing; fail-open.
      process.stderr.write(
        `validate-frontmatter-schema: machine-local get repos.doe_claude failed (rc=${e && e.status}) — central path anchor unavailable; central detection degraded (no central routing offer or own-inbox central guard until machine-local is healthy)\n`
      );
    }
    // rc=1 → cleanly absent; rc≥2 or ENOENT → already logged above. Both: fail-open.
  }
}());

/**
 * Derive the plan stem from a sidecar's repo-relative path.
 * Sidecar path form: docs/plans/<stem>.<sidecarType>.md
 * Strips the leading directory and trailing .<sidecarType>.md suffix.
 * Returns the stem string, or null if the path does not match the expected form.
 *
 * Example: 'docs/plans/2026-06-29-my-plan.prior-art-check.md', 'prior-art-check'
 *          → '2026-06-29-my-plan'
 */
function deriveSidecarPlanStem(repoRel, sidecarType) {
  const normalized = repoRel.replace(/\\/g, '/');
  const basename = normalized.split('/').pop();
  const suffix = `.${sidecarType}.md`;
  if (basename && basename.endsWith(suffix)) {
    return basename.slice(0, basename.length - suffix.length);
  }
  return null;
}

/**
 * Build an additionalContext scaffold offer for a new schema-matching file.
 * Leads with the runnable coordinator-doc-new command (design-as-offers doctrine).
 *
 * Default mode: additionalContext warn — the write proceeds.
 * Strict mode (COORDINATOR_SCHEMA_STRICT=1): deny — used in tests to assert the offer fires.
 *
 * Spec backlink: docs/plans/2026-06-29-cli-scaffold-deterministic-docs.md § C0a
 * Design-as-offers: eager-agent-calibration.md § Offer-Shape vs. Friction-as-Warning
 *
 * resolvedKind: when a KIND_OFFER_OVERRIDE applies, the schema name (e.g. 'handoff')
 * and the offered --type (e.g. 'spinoff') diverge; the label then reads
 * "(schema: handoff, resolved by kind: spinoff)" instead of a contradictory bare
 * "schema: handoff". The non-override path passes null and is unchanged.
 */
function buildScaffoldOfferPayload(schemaName, type, derivedArgs, authoringHint, resolvedKind = null) {
  const args = derivedArgs ? ` ${derivedArgs}` : '';
  const cmd = `coordinator-doc-new --type ${type}${args}`;
  const schemaLabel = resolvedKind
    ? `schema: ${schemaName}, resolved by kind: ${resolvedKind}`
    : `schema: ${schemaName}`;
  const message =
    `This is a new schema-matching document (${schemaLabel}). ` +
    `Use the scaffolder to generate conformant frontmatter:\n\n` +
    `  ${cmd}\n\n` +
    `Then fill the body via Edit. The scaffolder creates the file via Python open() ` +
    `(structurally exempt from this PreToolUse Write-tool hook — see new-file-only ` +
    `rationale below), so subsequent body-fill edits stay silent. ` +
    `Hand-rolling bypasses schema enforcement and risks frontmatter drift that breaks ` +
    `query-records and example-cockpit-repo ingest.` +
    (authoringHint ? `\n\n${authoringHint}` : '');

  const strict = process.env.COORDINATOR_SCHEMA_STRICT === '1';
  if (strict) {
    return JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'deny',
        permissionDecisionReason: message,
      },
    });
  }

  return JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      additionalContext: `[scaffold offer] ${message}`,
    },
  });
}

/**
 * Derive the em-id for the repo whose directory basename is given.
 *
 * Convention: <basename>-em (with underscores→dashes).
 * Exception: entries in REPO_BASENAME_TO_EM_SHORTNAME override the shortname.
 *
 * Mirrors the combined logic of _repo_key_to_em_id() + _em_id_for_root() from
 * bin/cross-repo-memo but operates purely on the basename, no subprocess needed.
 */
function emIdForBasename(basename) {
  if (REPO_BASENAME_TO_EM_SHORTNAME[basename] !== undefined) {
    return REPO_BASENAME_TO_EM_SHORTNAME[basename] + '-em';
  }
  // Convention: replace underscores with dashes (registry keys use underscores;
  // dir names may use either).
  return basename.replace(/_/g, '-') + '-em';
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Resolve the git repo root by running `git rev-parse --show-toplevel` in cwd.
 * Falls back to cwd if the command fails or we're not in a git repo.
 */
function resolveRepoRoot(cwd) {
  try {
    const result = execSync('git rev-parse --show-toplevel', {
      cwd,
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 3000,
    });
    return result.trim();
  } catch {
    return cwd;
  }
}

/**
 * Convert an absolute file_path to a repo-relative path using forward slashes.
 * Returns null if the path is not under repoRoot.
 */
function toRepoRelative(absPath, repoRoot) {
  const normalAbs = absPath.replace(/\\/g, '/');
  const normalRoot = repoRoot.replace(/\\/g, '/');
  if (!normalAbs.startsWith(normalRoot)) return null;
  return normalAbs.slice(normalRoot.length).replace(/^\//, '');
}

/**
 * Apply a single old_string→new_string replacement to content.
 * Returns { result: string, matched: boolean }.
 */
function applyEdit(content, oldString, newString) {
  const idx = content.indexOf(oldString);
  if (idx === -1) return { result: content, matched: false };
  return {
    result: content.slice(0, idx) + newString + content.slice(idx + oldString.length),
    matched: true,
  };
}

/**
 * Detect whether a repo-relative path looks like a mislocated cross-repo memo.
 * Returns true when the path contains a /memos/ segment (e.g. state/memos/foo.md)
 * — these are the non-canonical locations EMs hand-roll into instead of using the
 * cross-repo-memo CLI.
 *
 * Negative-spec: any path under cross-repo/ (the canonical receiver surface) must
 * return false — those are handled by the schema validator, not this offer.
 * The canonical subdirs are cross-repo/inbox/ (active memos) and cross-repo/archive/
 * (closed actioned memos). Both are excluded by the deliberately-broad ^cross-repo/
 * prefix guard — do NOT narrow this to ^cross-repo/inbox/ or archive/ writes would
 * start triggering the mislocated-memo offer incorrectly.
 * The guard is ^cross-repo/ (not just cross-repo/inbox/[0-9]*.md) so cross-repo/README.md
 * and other non-dated files in the canonical surface are also excluded correctly.
 * code-review F16: updated comment to match the actual guard (^cross-repo/ is correctly
 * broader than the digit-prefix glob — it also exempts README.md).
 */
function isMemoPathMislocated(repoRel) {
  const normalized = repoRel.replace(/\\/g, '/');
  // Canonical surface: cross-repo/ at root — must NOT trigger
  if (/^cross-repo\//.test(normalized)) return false;
  // Any path with a /memos/ segment is non-canonical
  if (/(?:^|\/)memos\//.test(normalized)) return true;
  return false;
}

/**
 * Detect whether the content of a prospective write looks like a free-form
 * cross-repo memo (hand-rolled To:/From: header lines, NOT proper YAML frontmatter).
 *
 * Heuristic: the first 20 non-blank lines contain both a "To:" line and a "From:"
 * line that are NOT inside a YAML frontmatter block (--- delimited). Proper YAML
 * frontmatter uses lowercase `to:` / `from:` — bare "To:" / "From:" with an
 * uppercase first letter are the hand-rolled style.
 *
 * Negative-spec: content with valid YAML frontmatter (`---\nto: ...\nfrom: ...\n---`)
 * must return false — those are handled by schema validation.
 */
function hasFreeFormMemoHeader(content) {
  const lines = content.split('\n');
  // If the file opens with a proper frontmatter block, skip the free-form check.
  if (lines[0] && lines[0].trim() === '---') return false;
  // Scan the first 20 non-blank lines for bare To:/From: headers
  let scanned = 0;
  let hasTo = false;
  let hasFrom = false;
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed === '') continue;
    if (/^To:\s+\S/.test(trimmed)) hasTo = true;
    if (/^From:\s+\S/.test(trimmed)) hasFrom = true;
    if (++scanned >= 20) break;
  }
  return hasTo && hasFrom;
}

/**
 * Extract the `to:` value from YAML frontmatter in file content.
 * Returns the string value of `to:` if present in the leading `---`…`---` block,
 * or null if not found, not present, or the block is not YAML.
 *
 * Purpose: routing comparison only — do NOT merge with hasFreeFormMemoHeader.
 * hasFreeFormMemoHeader detects hand-rolled (capitalized) headers; this extracts
 * the YAML `to:` for em-id resolution. See Chunk G N3 negative-spec: these are
 * two separate reads for two separate purposes.
 */
function extractYamlToField(content) {
  // Assumes unindented flat YAML frontmatter (no nested keys). Review: F8 — dead inBlock removed.
  const lines = content.split('\n');
  if (!lines[0] || lines[0].trim() !== '---') return null;
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim() === '---') break; // end of frontmatter block
    const m = line.match(/^to:\s+(.+)$/);
    if (m) return m[1].replace(/^["']|["']$/g, '').trim();
  }
  return null;
}

// review F1 — _CENTRAL_EM_IDS is declared and assigned in the manifest-structure
// try/catch block above (after KIND_OFFER_OVERRIDE). See that block for rationale.
// _DOE_CLAUDE_PATH is resolved below (machine-local shell-out, once per invocation).

/**
 * Build an additionalContext offer for a memo routed to the wrong repo.
 * Always emits additionalContext (offer-shape) — never deny.
 * Exception: COORDINATOR_SCHEMA_STRICT=1 upgrades to deny to enable test assertions.
 *
 * Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § Chunk G
 * Fork diagnostic: eager-agent-calibration.md § Offer-Shape vs. Friction-as-Warning
 * This is misdirection (not genuinely-incentivised wrong path) → offer-shape is correct.
 */
function buildMemoRoutingOfferPayload(resolvedRecipientEmId) {
  const recipientHint = resolvedRecipientEmId
    ? resolvedRecipientEmId
    : '<receiver-em-id>';
  const message =
    `This memo's \`to:\` field (${recipientHint}) does not match the repo you are writing into. ` +
    `Cross-repo memos must land in the RECIPIENT'S repo, not the sender's. ` +
    `Use the CLI to route it correctly:\n\n` +
    `  cross-repo-memo --to ${recipientHint} --topic <slug> --title "..." < body.md\n\n` +
    `The CLI writes one dirty file into ${recipientHint}'s cross-repo/inbox/ directory ` +
    `so it surfaces in their git status. ` +
    `Hand-rolling to the wrong repo means the recipient will never find the memo.`;

  const strict = process.env.COORDINATOR_SCHEMA_STRICT === '1';
  if (strict) {
    return JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'deny',
        permissionDecisionReason: message,
      },
    });
  }

  return JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      additionalContext: `[cross-repo-memo routing offer] ${message}`,
    },
  });
}

/**
 * Build an additionalContext offer for a mislocated / hand-rolled cross-repo memo.
 * Always emits additionalContext (never deny) — design-as-offers: we redirect, not block.
 * Exception: COORDINATOR_SCHEMA_STRICT=1 upgrades to deny to enable test assertions.
 *
 * Spec backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 5
 */
function buildMemoOfferPayload() {
  const message =
    'This looks like a cross-repo memo being hand-rolled to a non-canonical location. ' +
    'Use the CLI instead so it lands in the receiver\'s cross-repo/inbox/ surface:\n\n' +
    '  cross-repo-memo --to <receiver-repo-name> --topic <slug>\n\n' +
    'The CLI writes one dirty file into the receiver\'s cross-repo/inbox/ directory ' +
    '(status: open), leaves it uncommitted so it surfaces in their git status, ' +
    'and prints the path for you to hand the PM for relay. ' +
    'Hand-rolling bypasses schema validation, delivery guarantees, and discoverability.';

  const strict = process.env.COORDINATOR_SCHEMA_STRICT === '1';
  if (strict) {
    return JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'deny',
        permissionDecisionReason: message,
      },
    });
  }

  return JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      additionalContext: `[cross-repo-memo offer] ${message}`,
    },
  });
}

/**
 * Build a DENY payload for the own-inbox misplacement guard.
 *
 * Always emits permissionDecision: "deny" (not a warn) — a memo with from==thisRepo and
 * to!=thisRepo sitting in this repo's cross-repo/ is a high-confidence misplacement;
 * warn-default does not apply here.
 *
 * Design-as-offers: leads with the correct alternative (cross-repo-memo --to <recipient>),
 * not just the violation. Override via COORDINATOR_OVERRIDE_OWN_INBOX=1.
 *
 * Spec backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md § Chunk 5
 */
function buildOwnInboxDenyPayload(thisEmId, toValue) {
  const message =
    `This memo's \`from:\` is THIS repo (${thisEmId}) but it's landing in this repo's own cross-repo/inbox/. ` +
    `cross-repo/inbox/ holds memos addressed TO you, not memos authored by you. ` +
    `To SEND an outbound memo, deliver it to the recipient:\n\n` +
    `  cross-repo-memo --to ${toValue || '<recipient-em>'} --topic <slug> --title "..." < body.md\n\n` +
    `That command writes into the RECIPIENT's cross-repo/inbox/ directory, not yours. ` +
    `Override (rare legit case): COORDINATOR_OVERRIDE_OWN_INBOX=1`;
  return JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: 'deny',
      permissionDecisionReason: message,
    },
  });
}

/**
 * Build a DENY payload for a lineage-reachability hard-reject (C2).
 *
 * Always emits permissionDecision:'deny' — the deny-always posture (PM-ratified
 * 2026-07-08) is NOT gated on COORDINATOR_SCHEMA_STRICT; a provably never-existed
 * lineage target is corruption of the continuity graph itself, not a soft/
 * stylistic/forward-compat violation that WARN mode is meant to let through.
 *
 * Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C2
 */
function buildReachabilityDenyPayload(violations) {
  const parts = violations.map(v => `${v.field}: "${v.value}" — ${v.reason}`);
  const message =
    `Lineage-reachability check failed (write-time hard-reject): ${parts.join('; ')}. ` +
    `Each of predecessor / forked_from / additional_predecessors[] / origin_handoff must ` +
    `resolve to a handoff that exists live (state/handoffs/), on-disk-archived ` +
    `(archive/handoffs/), or in git history — a target unresolvable in all three is ` +
    `treated as a typo'd or never-existed path, not lineage. If this is a genuine ` +
    `cross-repo recovery baton, use kind: recovery (the same-repo-only carve-out ` +
    `applies to recovery predecessor SHAs only, not path-shaped lineage fields).`;
  return JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: 'deny',
      permissionDecisionReason: message,
    },
  });
}

/**
 * Lineage-reachability write-time hard-reject (C2).
 *
 * Runs AFTER the schema.js shape pass (schema.js stays filesystem/git-free by
 * deliberate invariant — this pass is the imperative fs/git-touching seam).
 *
 * Thin wrapper over the shared rule kernel `checkLineageReachability` promoted
 * to walk-handoff-dag.js (C6 GAP1) — this hook contributes only the
 * schemaName gate (reachability is a handoff/handoff-archived-only concern)
 * and the write-time handoffDir convention. The rule itself (which fields,
 * the kind:recovery same-repo-only carve-out) now lives in exactly one place
 * so the write-time hook and the batch corpus sweep (query-records.js
 * validateAllRecords, consumed by validate-handoff.js) can never drift apart.
 *
 * Review: code-reviewer F1 — admit 'handoff-archived' (not just 'handoff') so
 * writes/edits under archive/handoffs/ get the same write-time hard-reject as
 * state/handoffs/ writes; the batch sweep was previously the ONLY reachability
 * check that ever ran against the archived corpus. handoffDir for the
 * archived case is the target file's OWN directory (path.dirname(absFilePath)),
 * matching the batch-sweep convention at query-records.js's path.dirname(file)
 * call — NOT the hardcoded <repoRoot>/state/handoffs, which would be wrong for
 * a month-foldered archive/handoffs/YYYY-MM/ target.
 *
 * Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C2, § C6 (GAP1)
 */
function checkLineageReachability(frontmatter, schemaName, repoRoot, absFilePath) {
  if (!_checkLineageReachability) return []; // walk-handoff-dag.js failed to load — fail-open
  if (schemaName !== 'handoff' && schemaName !== 'handoff-archived') return [];
  if (!frontmatter) return [];
  const handoffDir = schemaName === 'handoff-archived'
    ? path.dirname(absFilePath)
    : path.join(repoRoot, 'state', 'handoffs');
  return _checkLineageReachability(frontmatter, repoRoot, handoffDir);
}

/**
 * Build a hook output payload for a validation failure.
 * errors is an array of {field, error, hint} (or {line, field, error, hint} for lessons).
 *
 * Default mode (warn): emits additionalContext — the agent sees the message, write proceeds.
 * Strict mode (COORDINATOR_SCHEMA_STRICT=1): emits a deny — the write is blocked.
 */
function buildViolationPayload(schemaName, errors) {
  const parts = errors.map(e => {
    const field = e.field || '(unknown)';
    const hint = e.hint ? `; required shape: ${e.hint}` : '';
    return `${field}: ${e.error}${hint}`;
  });
  const message = `${schemaName}: ${parts.join('; ')}`;
  const strict = process.env.COORDINATOR_SCHEMA_STRICT === '1';

  if (strict) {
    return JSON.stringify({
      hookSpecificOutput: {
        hookEventName: 'PreToolUse',
        permissionDecision: 'deny',
        permissionDecisionReason: message,
      },
    });
  }

  return JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      additionalContext: `[frontmatter-schema warning] ${message}\n\nThe write will proceed. Fix the frontmatter on the next edit, or set COORDINATOR_SCHEMA_STRICT=1 to block on violations. Periodic drift is swept by /update-docs.`,
    },
  });
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

// Diagnostic: tee every stdout emit to a session log so we can compare
// against any "hookSpecificOutput missing hookEventName" schema-validation
// errors the harness reports. → improvement-queue 2026-06-15.
(function installEmitTee() {
  const origWrite = process.stdout.write.bind(process.stdout);
  process.stdout.write = function (chunk, ...rest) {
    try {
      const { execSync } = require('child_process');
      const path = require('path');
      const fs = require('fs');
      const gitDir = execSync('git rev-parse --git-dir', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
      const sessId = process.env.CLAUDE_SESSION_ID || 'no-session';
      const dir = path.join(gitDir, 'coordinator-sessions', sessId, 'hook-emits');
      fs.mkdirSync(dir, { recursive: true });
      const ts = new Date().toISOString().replace(/[:.]/g, '').replace(/-/g, '').slice(0, 15) + 'Z';
      const line = `${ts}\tvalidate-frontmatter-schema\t${String(chunk).replace(/\n/g, ' ')}\n`;
      fs.appendFileSync(path.join(dir, 'emits.tsv'), line);
    } catch { /* best effort */ }
    return origWrite(chunk, ...rest);
  };
})();

async function main() {
  // Read all stdin
  let raw = '';
  try {
    for await (const chunk of process.stdin) {
      raw += chunk;
    }
  } catch {
    process.exit(0);
  }

  // Parse PreToolUse payload
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch {
    process.exit(0);
  }

  const toolName = payload.tool_name;
  const toolInput = payload.tool_input || {};
  const cwd = payload.cwd || process.cwd();

  const filePath = toolInput.file_path;
  if (!filePath) process.exit(0);

  // Resolve repo root and repo-relative path
  const repoRoot = resolveRepoRoot(cwd);
  const absFilePath = path.isAbsolute(filePath) ? filePath : path.join(cwd, filePath);
  const repoRel = toRepoRelative(absFilePath, repoRoot);
  if (!repoRel) process.exit(0);

  // ---------------------------------------------------------------------------
  // Design-as-offers: hand-rolling catch (Chunk 5)
  // Check for memo-shaped writes to non-canonical locations BEFORE schema lookup.
  // This fires even when no schema matches the path (state/memos/ has no schema).
  // Canonical cross-repo/[0-9]*.md writes pass through to normal schema validation.
  // ---------------------------------------------------------------------------
  if (toolName === 'Write' || toolName === 'Edit' || toolName === 'MultiEdit') {
    const pathMislocated = isMemoPathMislocated(repoRel);
    if (pathMislocated) {
      // Path-based detection: any /memos/ path is non-canonical
      process.stdout.write(buildMemoOfferPayload());
      process.exit(0);
    }

    // Content-based detection: free-form To:/From: header (not valid YAML frontmatter).
    // For Write: probe the full content directly.
    // For Edit: probe new_string as a lightweight signal (the full apply happens below).
    // For MultiEdit (code-review F9): probe new_string of edits[0] only looks at a
    // fragment — instead, build the prospectiveContent here and probe the composed
    // result so the full document after all edits is inspected, not just one fragment.
    // Note: prospectiveContent is computed again below for schema validation; the
    // duplication is intentional — the offer check must fire before schema lookup.
    let contentToProbe = null;
    if (toolName === 'Write') {
      contentToProbe = toolInput.content || '';
    } else if (toolName === 'Edit') {
      contentToProbe = toolInput.new_string || '';
    } else if (toolName === 'MultiEdit') {
      // code-review F9: probe the composed prospective content, not just edits[0].new_string.
      const edits = toolInput.edits || [];
      let multiEditProbe = '';
      try {
        multiEditProbe = fs.readFileSync(absFilePath, 'utf8');
      } catch {
        // File doesn't exist — start from empty.
        multiEditProbe = '';
      }
      let probeOk = true;
      for (const edit of edits) {
        const { result, matched } = applyEdit(multiEditProbe, edit.old_string || '', edit.new_string || '');
        if (!matched) { probeOk = false; break; }
        multiEditProbe = result;
      }
      if (probeOk) contentToProbe = multiEditProbe;
    }
    if (contentToProbe !== null && hasFreeFormMemoHeader(contentToProbe)) {
      process.stdout.write(buildMemoOfferPayload());
      process.exit(0);
    }

    // -------------------------------------------------------------------------
    // Own-inbox guard (Chunk 5 extension)
    //
    // A file matching cross-repo/[0-9]*.md is this repo's INBOX. An EM writing
    // a memo with from=<thisRepo> and to=<otherRepo> into their own cross-repo/
    // is placing an OUTBOUND memo in their own inbox — the recipient will never
    // see it. Deny and redirect to the cross-repo-memo CLI.
    //
    // Error condition: from resolves to THIS repo's em-id AND to != THIS repo's em-id.
    // Carve-out: from==to==thisRepo (--self-receipt pattern) → silent.
    // Normal inbound (from=<other>, to=<self>) → silent.
    // Override: COORDINATOR_OVERRIDE_OWN_INBOX=1 → skip check entirely.
    //
    // Fires only for Write/Edit/MultiEdit on cross-repo/inbox/[0-9]*.md (canonical inbox shape).
    // Negative-spec: does NOT fire for cross-repo/archive/ writes (closed memos are not outbound
    // misplacements) or for cross-repo/README.md and other non-digit-prefixed files.
    // Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § Chunk C (T2)
    // -------------------------------------------------------------------------

    // Hoist repoRoot realpath once — both the own-inbox guard (below) and the routing
    // comparison (further down) need it on the same value; computing it once makes the
    // fail-open coherence structural rather than a naming convention between two separate
    // try/catch blocks. Guarded by _DOE_CLAUDE_PATH !== null so the realpath syscall is
    // skipped entirely when machine-local is unavailable.
    // Review: code-reviewer — F2: eliminate maintenance-fragile duplication of realpathSync call
    let repoRootRealpath = null;
    if (_DOE_CLAUDE_PATH !== null) {
      try { repoRootRealpath = fs.realpathSync(repoRoot.replace(/[/\\]+$/, '')); } catch { /* fall through */ }
    }

    const isCanonicalInboxWrite = /^cross-repo\/inbox\/[0-9]/.test(repoRel.replace(/\\/g, '/'));
    if (isCanonicalInboxWrite && process.env.COORDINATOR_OVERRIDE_OWN_INBOX !== '1') {
      // Derive this repo's em-id.
      // Path-anchor: if repoRoot realpath === repos.doe_claude realpath, this IS the
      // central landing repo → thisEmId = 'claude-central-em'.
      // Fallback (machine-local unavailable or non-DoE machine): use basename convention.
      // Spec backlink: docs/plans/2026-07-04-central-identity-flip.md § C3 (own-inbox guard fix)
      const repoBasename = path.basename(repoRoot.replace(/[/\\]+$/, ''));
      let thisEmId;
      if (repoRootRealpath !== null && repoRootRealpath === _DOE_CLAUDE_PATH) {
        thisEmId = 'claude-central-em';
      }
      if (thisEmId === undefined) {
        thisEmId = emIdForBasename(repoBasename);
      }

      // Determine full prospective content to inspect for frontmatter.
      // Write: full content is directly available.
      // Edit: read existing file and apply edit to get the full prospective doc.
      //   If the file doesn't exist or old_string doesn't match, skip silently.
      // MultiEdit: contentToProbe is already the fully-composed result (or null on mismatch).
      let inboxContent = null;
      if (toolName === 'Write') {
        inboxContent = toolInput.content || '';
      } else if (toolName === 'Edit') {
        try {
          const existing = fs.readFileSync(absFilePath, 'utf8');
          const { result, matched } = applyEdit(existing, toolInput.old_string || '', toolInput.new_string || '');
          if (matched) inboxContent = result;
          // If not matched, inboxContent stays null → guard skips silently.
        } catch {
          // File doesn't exist → skip silently.
        }
      } else if (toolName === 'MultiEdit') {
        inboxContent = contentToProbe; // null on mismatch → guard skips silently.
      }

      if (inboxContent !== null) {
        const { frontmatter: inboxFm } = parseFrontmatter(inboxContent);
        if (inboxFm !== null) {
          const fromValue = (inboxFm.from || '').trim();
          const toValue = (inboxFm.to || '').trim();
          // Only fire when `from` is non-empty and resolves to THIS repo's em-id.
          if (fromValue && fromValue === thisEmId) {
            // Carve-out: from==to==thisRepo (self-receipt) → silent.
            if (toValue !== thisEmId) {
              // Error condition: outbound memo sitting in own inbox.
              process.stdout.write(buildOwnInboxDenyPayload(thisEmId, toValue));
              process.exit(0);
            }
          }
        }
      }
    }

    // -------------------------------------------------------------------------
    // Routing-mismatch memo-redirect offer (Chunk G)
    //
    // Wiki citation (N1 — greppable from shipped hook):
    // eager-agent-calibration.md § Offer-Shape vs. Friction-as-Warning
    //
    // The failure mode is misdirection (EM means to deliver a memo and reaches for
    // a plausible local path). Misdirection → offer-shape is correct: redirect to the
    // right primitive (cross-repo-memo CLI), never block.
    //
    // Step 1 — Gate: is this write itself a memo?
    //   Signal (a): YAML frontmatter `to:` field present in the file's own content, OR
    //   Signal (b): hasFreeFormMemoHeader() returns true AND the path is memo-shaped
    //               (*/memos/* or */cross-repo/*).
    // Explicitly NOT triggered by To:/From: appearing in arbitrary content (plans,
    // wikis, handoffs quoting example headers) — the gate prevents the offer from
    // firing on every doc edit that happens to mention memo-format headers.
    //
    // Step 2 — Two reads for two purposes (DO NOT merge into one case-insensitive regex):
    //   hasFreeFormMemoHeader() detects hand-rolled headers (capitalized, not YAML).
    //   extractYamlToField() extracts `to:` for routing comparison from proper YAML memos.
    //
    // Step 3 — Routing comparison:
    //   to:-repo ≠ landing-repo → offer.
    //   to:-repo = landing-repo → SILENT (correct inbound).
    //   to: claude-central-em / central-em / central, landing in ~/.claude → SILENT (routing match).
    //   Unresolvable to: → SILENT (can't prove mismatch; detect-then-fail-loud-only-when-proven).
    //
    // CLI self-write exemption: bin/cross-repo-memo writes via Python open(path,"w") at
    // bin/cross-repo-memo:444 (_write_file), NOT the Claude Write tool. PreToolUse hooks fire
    // on the Claude Code tool invocation surface, not on subprocess fs writes. The exemption
    // is structural — no runtime check needed. A hand-Write of memo content IS caught (by design).
    //
    // Override: COORDINATOR_OVERRIDE_MEMO_REDIRECT=1 silences this branch entirely.
    // Spec backlink: docs/plans/2026-05-23-cross-repo-inbox-archive-restructure.md § Chunk G
    // -------------------------------------------------------------------------
    // Routing-mismatch check does NOT apply to canonical inbox writes — the own-inbox
    // guard above handles that surface (with its own COORDINATOR_OVERRIDE_OWN_INBOX
    // carve-out). Canonical archive writes are closed actioned memos — not misrouted
    // outbound writes. Both cases are excluded so the two guards don't overlap.
    //
    // Transient migration note (Review: F2 — document pre-migration sibling behavior):
    // Siblings that have NOT yet run migrate-cross-repo-layout.sh still hold grandfathered
    // flat cross-repo/<file>.md memos. The routing check fires on those writes if the
    // memo's to: normalizes differently from emIdForBasename(landingBasename). This is a
    // false positive on legitimate lifecycle edits (e.g. status: open → actioned). It will
    // self-resolve once each sibling runs migrate-cross-repo-layout.sh. No carve-out is
    // added here — over-engineering for transient state. Affected siblings: example-game-repo,
    // project-rag, project-rag-ue-addon.
    const normalizedRelForRouting = repoRel.replace(/\\/g, '/');
    const isCanonicalMemoSurface = /^cross-repo\/inbox\//.test(normalizedRelForRouting) ||
                                   /^cross-repo\/archive\//.test(normalizedRelForRouting);
    if (process.env.COORDINATOR_OVERRIDE_MEMO_REDIRECT !== '1' && !isCanonicalMemoSurface) {
      // Determine full prospective content to check (reuse contentToProbe from above).
      // contentToProbe was computed above for the free-form-header check; reuse here avoids
      // a second file-read + apply cycle. null means MultiEdit failed to apply → skip silently.
      // Review: F10 — explain contentToProbe reuse; see also line 422 comment on first use.
      let memoCheckContent = null;
      if (toolName === 'Write') {
        memoCheckContent = toolInput.content || '';
      } else if (toolName === 'Edit') {
        memoCheckContent = toolInput.new_string || '';
      } else if (toolName === 'MultiEdit') {
        memoCheckContent = contentToProbe; // may be null on mismatch
      }

      if (memoCheckContent !== null) {
        const normalizedRel = normalizedRelForRouting;
        // Memo-shaped path: /memos/ segment (non-canonical), OR a cross-repo/ path that
        // is NOT the canonical inbox/archive (already excluded by isCanonicalMemoSurface above).
        // cross-repo/ at root (flat, non-inbox) is a valid signal for hand-rolled memos.
        const isMemoShapedPath = /(?:^|\/)memos\//.test(normalizedRel) ||
                                 /^cross-repo\//.test(normalizedRel);

        // Step 1: determine if this write IS a memo (two qualifying signals, BOTH path-gated).
        //
        // Review: code-reviewer F4 — tightened 2026-05-23. Previously signal (a) `yamlToValue !== null`
        // fired path-agnostically per the plan's spec. The reviewer's AC-9(a) test exposed the
        // overbreadth: a `docs/plans/<file>.md` with a YAML `to:` field in its frontmatter triggered
        // the routing offer — a false-positive on doc edits that happen to use the same key. The
        // gate now requires `isMemoShapedPath` for BOTH signals: a write is a memo only if it lands
        // in a memo-shaped path AND carries memo-shaped content (proper YAML `to:` OR hand-rolled
        // `To:`/`From:` headers). Non-memo files with `to:` fields are no longer misclassified.
        //
        // The case this loses (an EM writes a proper-YAML memo to a non-memo-shaped path like
        // `tasks/foo.md`) is rare and caught by the mislocated-memo offer + own-inbox guard
        // downstream. Net: smaller false-positive surface, same true-positive coverage.
        const yamlToValue = extractYamlToField(memoCheckContent);
        const hasFreeForm = hasFreeFormMemoHeader(memoCheckContent);
        const isThisAMemo = isMemoShapedPath &&
                            (yamlToValue !== null || hasFreeForm);

        if (isThisAMemo) {
          // Step 2: extract `to:` for routing. Two reads for two purposes — hasFreeForm
          // already used for detection above; yamlToValue is for routing resolution.
          const toFieldRaw = yamlToValue;

          // Step 3: routing comparison.
          // Determine landing repo em-id from the write's absolute path.
          // Path-anchor: compare repoRoot realpath to repos.doe_claude realpath (C3).
          // If they match, landing IS the central repo → landingEmId = 'claude-central-em'.
          // Fallback (machine-local unavailable or non-DoE machine): use basename convention.
          // Spec backlink: docs/plans/2026-07-04-central-identity-flip.md § C3 (landing anchor)
          const landingBasename = path.basename(repoRoot.replace(/[/\\]+$/, ''));
          let landingEmId;
          if (repoRootRealpath !== null && repoRootRealpath === _DOE_CLAUDE_PATH) {
            landingEmId = 'claude-central-em';
          }
          if (landingEmId === undefined) {
            landingEmId = emIdForBasename(landingBasename);
          }

          if (toFieldRaw !== null) {
            // Normalize to: value for comparison.
            const toNorm = toFieldRaw.trim().toLowerCase();

            // Central-aware: to: claude-central-em (or aliases) landing in DoE-claude → SILENT.
            // C3 spec: central landing is now path-anchored to repos.doe_claude.
            // Spec backlink: docs/plans/2026-07-04-central-identity-flip.md § C3
            const toIsCentral = _CENTRAL_EM_IDS.has(toFieldRaw.trim()) ||
                                _CENTRAL_EM_IDS.has(toNorm);
            const landingIsCentral = landingEmId === 'claude-central-em';
            if (toIsCentral && landingIsCentral) {
              // Routing match for central — fall through silent.
            } else if (toIsCentral && _DOE_CLAUDE_PATH === null) {
              // Machine-local unavailable: central path anchor missing.
              // Can't prove whether landing IS or ISN'T central → fail-open silently.
              // No offer: an incorrect central offer would be worse than no offer.
              // (own-inbox guard also degrades under this condition — see _DOE_CLAUDE_PATH block)
            } else {
              // Resolve to:-repo via emIdForBasename (same lookup, no mirror).
              // The to: field may be an em-id like "example-game-repo-em" or "project-rag-em".
              // We normalise by comparing em-ids directly (landingEmId vs toFieldRaw).
              // Unresolvable: if to: value doesn't look like a known em-id pattern,
              // we can't prove a mismatch → stay silent.
              const toEmId = toFieldRaw.trim();
              // A valid em-id ends with -em (convention). Unknown patterns → SILENT.
              const toLooksLikeEmId = /\S+-em$/.test(toEmId) || _CENTRAL_EM_IDS.has(toEmId);
              if (toLooksLikeEmId) {
                // Normalize both to lowercase for comparison (em-ids are lowercase by convention).
                const toEmIdNorm = toEmId.toLowerCase();
                const landingEmIdNorm = landingEmId.toLowerCase();
                if (toEmIdNorm !== landingEmIdNorm) {
                  // Routing mismatch: memo addressed to a different repo than where it's landing.
                  process.stdout.write(buildMemoRoutingOfferPayload(toEmId));
                  process.exit(0);
                }
                // else: routing match → silent (correct inbound or self-delivery).
              }
              // else: unresolvable to: → SILENT.
            }
          }
          // else: no to: field resolvable for routing → SILENT (can't prove mismatch).
        }
      }
    }
  }

  // Load schemas (telemetry-style: log to stderr on error, never block)
  // The try/catch here makes a duplicate-kind throw from loadSchemas WARN-safe:
  // the throw is caught, logged to stderr, and the hook exits silent.
  let schemas;
  try {
    schemas = loadSchemas(SCHEMAS_DIR);
  } catch (err) {
    process.stderr.write(`validate-frontmatter-schema: schema load error: ${err.message}\n`);
    process.exit(0);
  }

  // Build prospective content based on tool type.
  //
  // This block moves ABOVE the tracked-ness gate so that parseFrontmatter can
  // read kind: before matchSchema runs. Every silent-exit path is preserved:
  //   - Edit: file-not-found → exit 0; old_string-not-matched → exit 0.
  //   - MultiEdit: any edit mismatch → exit 0.
  //   - Unknown tool → exit 0.
  // Behavior is identical to the prior order for all existing tracked paths;
  // the only change is that these exits now run for ALL .md writes rather than
  // only for files the path glob already admitted.
  //
  // Spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § C3
  // Negative-spec: do NOT re-order the memo-offer / own-inbox / routing branches
  // above — those run before schema selection and are independent of this reorder.
  let prospectiveContent;

  if (toolName === 'Write') {
    // Write: use content directly
    prospectiveContent = toolInput.content || '';

  } else if (toolName === 'Edit') {
    const oldString = toolInput.old_string;
    const newString = toolInput.new_string;

    // Read current file if it exists
    let current;
    try {
      current = fs.readFileSync(absFilePath, 'utf8');
    } catch {
      // File doesn't exist — old_string can't match; fall through silent.
      // (Edit will fail on its own merits when Claude applies it.)
      process.exit(0);
    }

    // Apply the edit
    const { result, matched } = applyEdit(current, oldString || '', newString || '');
    if (!matched) {
      // old_string doesn't appear — fall through silent (let Edit fail on its own)
      process.exit(0);
    }
    prospectiveContent = result;

  } else if (toolName === 'MultiEdit') {
    const edits = toolInput.edits || [];

    // Read current file if it exists
    let current = '';
    try {
      current = fs.readFileSync(absFilePath, 'utf8');
    } catch {
      // File doesn't exist — start with empty
      current = '';
    }

    // Apply each edit sequentially
    let content = current;
    for (const edit of edits) {
      const { result, matched } = applyEdit(content, edit.old_string || '', edit.new_string || '');
      if (!matched) {
        // Any mismatch — fall through silent
        process.exit(0);
      }
      content = result;
    }
    prospectiveContent = content;

  } else {
    process.exit(0);
  }

  // Parse frontmatter so kind: is available for matchSchema.
  // parseFrontmatter returns {frontmatter: object|null, body: string}.
  // frontmatter may be null (no --- block) — matchSchema handles null gracefully
  // (kind-first branch skips, falls to glob-fallback).
  const { frontmatter } = parseFrontmatter(prospectiveContent);

  // Tracked-ness gate: a file is validated if its path matches a glob OR its
  // kind: maps to a schema. matchSchema implements kind-first, glob-fallback.
  // Returns null if neither branch matches → not a tracked-record path → exit silent.
  //
  // Spec backlink: docs/plans/2026-06-23-deliverable-type-schema-taxonomy.md § Decision 1
  const match = matchSchema(repoRel, frontmatter, schemas);
  if (!match) process.exit(0);

  const { schemaName, schema } = match;

  // ---------------------------------------------------------------------------
  // Design-as-offers: scaffold generator offer (C0a)
  //
  // When a Write tool creates a NEW schema-matching file, offer the CLI scaffolder
  // instead of letting the agent hand-author the frontmatter. Lead with the better
  // alternative (coordinator-doc-new --type <T>), never block (outside strict mode).
  //
  // Fire condition: Write tool AND the target file does NOT yet exist (new-file
  // creation) AND the matched schema is in SCAFFOLD_OFFER_MAP. Frontmatter presence
  // in the content is irrelevant — the offer fires on any new schema-matching file
  // (with or without hand-rolled frontmatter). This is the correct C0a semantic:
  // even a correctly-hand-authored new file should be redirected to the scaffolder
  // (the scaffolder guarantees conformance; hand-rolling does not). Existing tests
  // that Write to non-existent schema-matching paths with complete frontmatter are
  // reconciled via pre-create (they write the fixture file before calling the hook
  // so fs.existsSync is true and the offer guard doesn't fire).
  //
  // WHY new-file-only — do NOT fire on Edit (required maintainer note, C0a spec):
  //   Scaffold-then-fill works because the scaffolder creates the file via Python
  //   open() (a filesystem write, NOT a Claude Write tool call). PreToolUse hooks
  //   fire on the Claude Code tool surface only. So the scaffolder's file creation
  //   is structurally exempt from this hook — no offer loop. The agent then fills
  //   the body via Edit or Write against the now-existing file. Because the file
  //   exists by then, !fs.existsSync(absFilePath) is false and the offer stays
  //   silent. A maintainer MUST NOT "fix" this to fire on Edit calls — doing so
  //   would nag the agent on every body-fill pass, defeating the scaffold pattern
  //   and creating the exact "offer loop" this discriminator is designed to prevent.
  //   The new-file discriminator is the architectural load-bearing element here.
  //
  // Spec backlink: docs/plans/2026-06-29-cli-scaffold-deterministic-docs.md § C0a
  // ---------------------------------------------------------------------------
  if (toolName === 'Write' && !fs.existsSync(absFilePath) && schemaName in SCAFFOLD_OFFER_MAP) {
    // Kind-first offer resolution: a kind sharing this schema (handoff/spinoff/
    // spinoff-roadmap → schemaName 'handoff') is disambiguated from frontmatter.kind
    // so the offer names the correct --type. Falls back to the schemaName-based
    // SCAFFOLD_OFFER_MAP entry when no kind override applies (or no kind present).
    const kindValue = (frontmatter && frontmatter.kind != null) ? String(frontmatter.kind) : null;
    const override = kindValue ? KIND_OFFER_OVERRIDE[kindValue] : null;
    const { type, isSidecar } = override || SCAFFOLD_OFFER_MAP[schemaName];
    const authoringHint = override ? override.authoringHint : null;
    let derivedArgs = null;
    if (override && override.manualArgs) {
      // Non-path-derivable required args (e.g. spinoff-roadmap --roadmap-id/--stub-id)
      // surfaced as placeholders, same pattern as the sidecar --plan <stem> derivation.
      derivedArgs = override.manualArgs;
    } else if (isSidecar) {
      // Derive --plan <stem> from the sidecar path (docs/plans/<stem>.<type>.md).
      // coordinator-doc-new hard-exits without --plan for sidecar types (line ~1148-1184).
      const stem = deriveSidecarPlanStem(repoRel, type);
      derivedArgs = stem ? `--plan ${stem}` : '--plan <stem>';
    }
    process.stdout.write(buildScaffoldOfferPayload(schemaName, type, derivedArgs, authoringHint, override ? kindValue : null));
    process.exit(0);
  }

  // Validate the prospective content against the schema.
  let validationResult;

  if (schema.match_mode === 'inline-tag-per-entry') {
    // DEAD BRANCH — no schema currently uses match_mode: inline-tag-per-entry.
    // The lesson-entry schema migrated to whole-document-yaml (2026-07-01).
    // Retained to avoid a silent behaviour change if a schema re-adopts this
    // mode in the future. validateLessonsFile() in bin/lib/schema.js remains
    // exercised via a synthetic fixture in schema.test.js (not this branch).
    // Lessons file — validate inline tags on the DELTA only (the text being
    // written now), never the whole reconstructed file. A per-write hook must
    // not re-flag pre-existing entries' tag drift and blame the current writer
    // for it. For a full Write the delta IS the whole file; for Edit/MultiEdit
    // it is the new text. The Edit/MultiEdit apply above already exited silent
    // if old_string didn't match, so by here the change is known applicable.
    //
    // By-design coverage gap: pre-existing tag drift in unchanged regions of
    // lessons.md is NOT caught at write time (that re-flagging WAS the noise
    // this scoping removes). There is no whole-file sweep today — lessons tag
    // validation is a warn-mode authoring aid, not a blocker, so accumulated
    // cosmetic drift is acceptable. If a sweep is ever wanted, add a
    // --validate-all mode to bin/query-records and call it from /update-docs;
    // do not restore whole-file validation to this per-write hook.
    //
    // Each delta fragment is validated independently and errors unioned, so a
    // MultiEdit cannot fabricate a phantom **entry** line by joining two
    // fragments across a line boundary (code-review F3).
    let deltas;
    if (toolName === 'Edit') {
      deltas = [toolInput.new_string || ''];
    } else if (toolName === 'MultiEdit') {
      deltas = (toolInput.edits || []).map(e => e.new_string || '');
    } else {
      // Write (whole-file author) — the author owns the entire content.
      deltas = [toolInput.content || ''];
    }
    const lessonErrors = [];
    for (const d of deltas) {
      const r = validateLessonsFile(d, schema);
      if (!r.ok) lessonErrors.push(...r.errors);
    }
    validationResult = lessonErrors.length === 0 ? { ok: true } : { ok: false, errors: lessonErrors };
  } else {
    // Standard frontmatter validation.
    // frontmatter was already parsed above — do NOT re-parse prospectiveContent here.

    if (schema.match_mode === 'whole-document-yaml') {
      // Bare-YAML queue files (improvement-queue, bug-backlog, debt-backlog) — the
      // entire document IS the record; no --- frontmatter fences are used.
      // Parse prospectiveContent as a bare YAML document and validate against the schema.
      //
      // Latent-bug fix (bounded, same block): whole-document-yaml now also backs
      // .json-extension schemas (e.g. review-trail, defaulted via
      // bin/lib/schema.js's applyDefaultMatchMode). parseYaml() is a homegrown
      // YAML-subset parser that does NOT understand JSON's curly-brace flow-mapping
      // syntax — feeding it compact JSON silently returns a mangled object (quoted
      // keys/values as literal strings, not an error), which downstream reports
      // every required field "missing". Try JSON.parse first for .json-extension
      // files; only fall back to the YAML parser for actual YAML content. A JSON
      // parse failure on a .json path is deliberately non-fatal here — falls
      // through to parseYaml so a maintainer who hand-edits a .json record with
      // YAML-ish shorthand isn't blocked outright by this widening.
      let parsed;
      try {
        if (repoRel.toLowerCase().endsWith('.json')) {
          try {
            parsed = JSON.parse(prospectiveContent);
          } catch {
            parsed = parseYaml(prospectiveContent);
          }
        } else {
          parsed = parseYaml(prospectiveContent);
        }
      } catch (err) {
        process.stdout.write(buildViolationPayload(schemaName, [{
          field: '(parse error)',
          error: `YAML parse error: ${err && err.message ? err.message : String(err)}`,
          hint: 'Ensure the file is valid YAML with no --- frontmatter fences',
        }]));
        process.exit(0);
      }
      validationResult = validateFrontmatter(parsed, schema);
    } else if (schema.match_mode === 'no-frontmatter') {
      // Bare prose artifacts (e.g. review-findings) — the schema declares its
      // records deliberately carry NO YAML frontmatter block. Do not run the
      // "missing frontmatter" warn/deny path below; there is nothing to validate.
      // Spec backlink: schemas/review-findings.yaml match_mode comment.
      validationResult = { ok: true };
    } else {
      // Missing frontmatter on a schema'd file → surface as warn (or deny under strict mode)
      if (frontmatter === null) {
        const requiredFields = schema.required ? Object.keys(schema.required) : [];
        const hint = requiredFields.length > 0
          ? `expected fields: ${requiredFields.join(', ')}`
          : 'add --- delimited YAML frontmatter';
        process.stdout.write(buildViolationPayload(schemaName, [{
          field: '(missing frontmatter)',
          error: 'no YAML frontmatter found',
          hint,
        }]));
        process.exit(0);
      }

      validationResult = validateFrontmatter(frontmatter, schema);
    }
  }

  // ---------------------------------------------------------------------------
  // C2 — lineage-reachability write-time hard-reject.
  //
  // Runs AFTER the schema.js shape pass above (schema.js stays filesystem/
  // git-free by deliberate invariant). Deny-always posture (PM-ratified
  // 2026-07-08): fires regardless of COORDINATOR_SCHEMA_STRICT and regardless
  // of whether the shape pass itself already found violations — reachability
  // is an orthogonal, independently-fatal check.
  //
  // Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C2
  // ---------------------------------------------------------------------------
  const reachabilityViolations = checkLineageReachability(frontmatter, schemaName, repoRoot, absFilePath);
  if (reachabilityViolations.length > 0) {
    process.stdout.write(buildReachabilityDenyPayload(reachabilityViolations));
    process.exit(0);
  }

  if (validationResult.ok) {
    // Pass — exit silent
    process.exit(0);
  }

  // Fail — emit warn (or deny under COORDINATOR_SCHEMA_STRICT=1) to stdout
  process.stdout.write(buildViolationPayload(schemaName, validationResult.errors));
  process.exit(0);
}

main().catch(err => {
  process.stderr.write(`validate-frontmatter-schema: unexpected error: ${err.message}\n`);
  process.exit(0);
});
