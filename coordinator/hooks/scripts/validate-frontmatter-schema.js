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
 * silent (let Edit fail on its own merits per Patrik R1 finding 0).
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
const { execSync } = require('child_process');
const { loadSchemas, matchSchema, matchSchemaForPath, parseFrontmatter, validateFrontmatter, validateLessonsFile } = require('../../bin/lib/schema.js');

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SCHEMAS_DIR = path.join(__dirname, '../../schemas');

// ---------------------------------------------------------------------------
// Cross-repo own-inbox guard — alias map
//
// Mirrors RECEIVER_EM_ALIASES from bin/cross-repo-memo IN REVERSE so that
// a repo's directory basename can be mapped to its canonical em-id WITHOUT
// shelling out. The forward map is: shortname → registry-key-suffix (e.g.
// "holodeck" → "claude_unreal_holodeck"). The reverse we need here is:
// registry-key-suffix (== dir basename with dashes→underscores) → shortname.
//
// Spec backlink: docs/plans/2026-05-23-cross-repo-single-surface-and-canonical-scaffold.md
// Negative-spec: do NOT shell out to cross-repo-memo or machine-local — this must be
// a pure in-process lookup so the hook is fast and offline-safe.
// ---------------------------------------------------------------------------

/** Maps repo directory basename → canonical em-id shortname (pre-suffix).
 * Populated from the INVERSE of bin/cross-repo-memo's RECEIVER_EM_ALIASES.
 * Only entries whose doctrine name diverges from the repo basename live here.
 * Convention-covered repos (basename→dashes-em) need no entry.
 */
const REPO_BASENAME_TO_EM_SHORTNAME = {
  // RECEIVER_EM_ALIASES reverse: "holodeck" → "claude_unreal_holodeck"
  // Inverse: basename "claude-unreal-holodeck" → em shortname "holodeck"
  'claude-unreal-holodeck': 'holodeck',
};

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

// Central receiver IDs — a memo `to: claude-central-em` (or aliases) landing
// in ~/.claude is a routing MATCH, not a mismatch. Consistent with CLI's
// _CENTRAL_RECEIVER_IDS and the B2 fix that makes central an explicit receiver.
//
// MANUAL MIRROR of bin/cross-repo-memo._CENTRAL_RECEIVER_IDS (lines ~107-111).
// Bidirectional update contract: if you add an alias here, add it to the Python
// frozenset too, and vice versa. No machine-enforced link exists — it is a
// two-file contract by design (avoids a JSON/shared-file dependency at hook load).
// Review: F6 — document manual-mirror contract to prevent alias drift
const _CENTRAL_EM_IDS = new Set([
  'claude-central-em',
  'central-em',
  'central',
]);

// The ~/.claude meta-repo has no conventional basename that resolves to
// "claude-central-em" via the <basename>-em convention (basename would be ".claude").
// We hard-code the mapping here so central routing stays silent.
const _CENTRAL_REPO_BASENAMES = new Set(['.claude']);

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
    const isCanonicalInboxWrite = /^cross-repo\/inbox\/[0-9]/.test(repoRel.replace(/\\/g, '/'));
    if (isCanonicalInboxWrite && process.env.COORDINATOR_OVERRIDE_OWN_INBOX !== '1') {
      // Derive this repo's em-id from the repo root basename.
      // resolveRepoRoot returns the full path; basename gives the dir name.
      const repoBasename = path.basename(repoRoot.replace(/[/\\]+$/, ''));
      const thisEmId = emIdForBasename(repoBasename);

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
    // added here — over-engineering for transient state. Affected siblings: holodeck,
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
          const landingBasename = path.basename(repoRoot.replace(/[/\\]+$/, ''));
          let landingEmId;
          if (_CENTRAL_REPO_BASENAMES.has(landingBasename)) {
            landingEmId = 'claude-central-em';
          } else {
            landingEmId = emIdForBasename(landingBasename);
          }

          if (toFieldRaw !== null) {
            // Normalize to: value for comparison.
            const toNorm = toFieldRaw.trim().toLowerCase();

            // Central-aware: to: claude-central-em (or aliases) landing in ~/.claude → SILENT.
            const toIsCentral = _CENTRAL_EM_IDS.has(toFieldRaw.trim()) ||
                                _CENTRAL_EM_IDS.has(toNorm);
            const landingIsCentral = landingEmId === 'claude-central-em';
            if (toIsCentral && landingIsCentral) {
              // Routing match for central — fall through silent.
            } else {
              // Resolve to:-repo via emIdForBasename (same lookup, no mirror).
              // The to: field may be an em-id like "holodeck-em" or "project-rag-em".
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

  // Validate the prospective content against the schema.
  // The lessons match_mode branch validates the DELTA (toolInput), not the parsed
  // frontmatter — lessons.md has no frontmatter block, so frontmatter is null here
  // and matchSchema reached this schema via glob-fallback (state/lessons.md → lessons glob).
  let validationResult;

  if (schema.match_mode === 'inline-tag-per-entry') {
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
