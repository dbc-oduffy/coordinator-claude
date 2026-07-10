#!/usr/bin/env node
'use strict';
/**
 * memo-transition.js — atomic cross-repo-memo lifecycle frontmatter transitions.
 *
 * Purpose: the single authorized writer of a memo's lifecycle frontmatter
 * (status, picked_up_by/at, decision, realized_by, actioned_note). Mirrors
 * handoff-transition.js — same frontmatter primitives, same fail-loud discipline,
 * same dup-key guard and post-write self-verify pattern.
 *
 * Spec backlink: docs/plans/2026-06-21-memo-pickup-claim-lock-and-routed-plan-reconcile.md § C2
 *
 * Usage:
 *   memo-transition.js claim   --memo <path> --session-id <id> --at <ISO>
 *   memo-transition.js action  --memo <path> (--decision <val> --decision-note <text> --realized-by <ptr>
 *                                              | --actioned-note <text>)
 *   memo-transition.js release --memo <path>
 *
 * Gate note: the `action` verb bypasses the cs_action_memo liveness-gated ownership gate when
 * called directly (liveness is a shell-only predicate; not computable in node). Route all
 * terminal memo flips through cs_action_memo (lib/coordinator-archive-stamp.sh) to enforce the
 * gate. Review: F4 — surfaced here so node CLI users see it, not only readers of the bash lib.
 *
 * Verbs:
 *   claim   — open → in_progress; writes picked_up_at + picked_up_by.
 *   action  — in_progress → actioned; writes decision/decision_note/realized_by
 *              OR actioned_note (consult/fyi shape). Preserves picked_up_by/at.
 *   release — in_progress → open; removes picked_up_by + picked_up_at entirely.
 *
 * Dup-key guard: if the frontmatter contains ≥2 `status:` keys BEFORE any write,
 * the tool fails loud and requires manual hand-collapse. After each write it
 * self-verifies exactly one `status:` key remains.
 *
 * Validation seam: validateMemoFrontmatter runs cross-field rules only (not base-required
 * fields) — memos are foreign-authored and a sender's base-field slip must never block
 * a legitimate receiver transition. Rules via schema.js applyCrossFieldRulesFor.
 *
 * Exit codes:
 *   0 — transition applied OR already-at-target no-op
 *   1 — error (bad args, dup status keys, unexpected state, validation failure, I/O error)
 */

const fs = require('fs');
const path = require('path');

// --- Frontmatter primitives ------------------------------------------------------
// splitFrontmatter/readFmField/serializeYamlScalar/replaceFmField/insertFmField/
// removeFmField are the shared write-side primitives reconciled onto lib/schema.js
// (canonical single implementation — see schema.js module header for reconciliation
// notes). removeFmField was migrated onto the shared boundary-safe implementation
// 2026-07-09 (code-reviewer B-F1) — its 3 local copies are consolidated there.
const {
  splitFrontmatter,
  readFmField,
  serializeYamlScalar,
  replaceFmField,
  insertFmField,
  removeFmField,
} = require(path.join(__dirname, 'lib', 'schema.js'));

// --- Dup-key guard ---------------------------------------------------------------

function countStatusKeys(fmText) {
  // Count occurrences of `^status:` (line-anchored, boundary-safe via /m flag).
  // Review: code-reviewer slice A — F2: add (?=[ \t]|$) boundary to align with readFmField's
  // contract; prevents `status:open` (no space) from being counted as present by the guard
  // while returning null from readFmField → avoids spurious "2 status: keys" internal error.
  const re = /^status:(?=[ \t]|$)/mg;
  return (fmText.match(re) || []).length;
}

// --- fail helper ----------------------------------------------------------------

function fail(msg) {
  process.stderr.write(`memo-transition: ${msg}\n`);
  process.exit(1);
}

// --- Validation seam ------------------------------------------------------------
//
// validateMemoFrontmatter — validates CROSS-FIELD RULES ONLY (not base-required fields).
//
// Negative-spec: base-required field validation is intentionally ABSENT here. Memos are
// foreign-authored (a sibling-repo EM); a sender's base-field slip (missing title/from/etc.)
// must never fail-loud-block the receiver's own legitimate lifecycle transition. Only
// cross-field rules that the receiver's own transition might violate are checked.
//
// Rules dispatched via schema.js applyCrossFieldRulesFor('cross-repo-memo', fm):
//   1. status=in_progress requires non-empty picked_up_by
//   2. status=actioned + decision=accepted|partial requires well-formed realized_by
//   3. Grandfather cutoff: created < 2026-05-22 → skip all cross-field checks
//
// The single-status-key postcondition is also verified here (part of seam requirement).
//
// Spec backlink: docs/plans/2026-06-21-memo-pickup-claim-lock-and-routed-plan-reconcile.md § C2

function validateMemoFrontmatter(fmText) {
  // Lazy-require schema.js — avoids startup cost on arg-validation paths.
  const schemaLib = require(path.join(__dirname, 'lib', 'schema.js'));

  // Single-status-key postcondition (seam requirement: verify after mutations, before write).
  const keyCount = countStatusKeys(fmText);
  if (keyCount !== 1) {
    fail(`post-mutation frontmatter has ${keyCount} status: key(s) (expected exactly 1) — fix the frontmatter manually`);
  }

  const fm = schemaLib.parseYamlBlock(fmText);
  const errors = schemaLib.applyCrossFieldRulesFor('cross-repo-memo', fm);
  if (errors.length > 0) {
    const details = errors
      .map(e => `  ${e.field}: ${e.error}${e.hint ? ' (' + e.hint + ')' : ''}`)
      .join('\n');
    fail(`memo cross-field validation failed:\n${details}`);
  }
}

// --- arg parser -----------------------------------------------------------------

function parseArgs(argv) {
  const args = argv.slice(2);
  // Explicit null (not undefined) when no verb given, so switch default branch receives null
  // and `opts.verb || '(none)'` works consistently.
  const verb = args.length > 0 ? args[0] : null;
  const opts = {
    verb,
    memo: null,
    sessionId: null,
    at: null,
    decision: null,
    decisionNote: null,
    realizedBy: null,
    actionedNote: null,
  };
  // Bounds-check before consuming next arg so a trailing flag with no value gets a clear
  // error rather than silently assigning undefined.
  for (let i = 1; i < args.length; i++) {
    const a = args[i];
    const nextVal = () => { if (i + 1 >= args.length) fail('flag requires a value: ' + a); return args[++i]; };
    if (a === '--memo') {
      opts.memo = nextVal();
      // Review: code-reviewer slice A — F8: parse-time path validation; guards against
      // empty strings and path-traversal sequences in the agent-supplied --memo argument.
      if (opts.memo === '' || /\.\.[\\/]/.test(opts.memo)) fail('--memo path must not be empty or contain ".." traversal segments');
    } else if (a === '--session-id')    opts.sessionId = nextVal();
    else if (a === '--at')            opts.at = nextVal();
    else if (a === '--decision')      opts.decision = nextVal();
    else if (a === '--decision-note') opts.decisionNote = nextVal();
    else if (a === '--realized-by')   opts.realizedBy = nextVal();
    else if (a === '--actioned-note') opts.actionedNote = nextVal();
    else fail(`unknown argument: ${a}`);
  }
  return opts;
}

// --- claim verb -----------------------------------------------------------------

function claim(opts) {
  if (!opts.memo) fail('claim requires --memo <path>');
  // Fail-loud on empty/missing session-id — never write `picked_up_by:` empty.
  if (!opts.sessionId || !opts.sessionId.trim()) {
    fail('claim requires a non-empty --session-id (empty picked_up_by would corrupt the claim gate)');
  }
  if (!opts.at || !opts.at.trim()) fail('claim requires --at <ISO timestamp>');
  if (!fs.existsSync(opts.memo)) fail(`memo not found: ${opts.memo}`);

  const original = fs.readFileSync(opts.memo, 'utf8').replace(/\r\n/g, '\n');
  const split = splitFrontmatter(original);
  if (!split) fail(`no parseable YAML frontmatter in ${opts.memo}`);

  // Pre-mutation dup-key guard — fail before touching anything on disk.
  const preDupCount = countStatusKeys(split.fmText);
  if (preDupCount >= 2) {
    fail(
      `memo has ${preDupCount} status: keys — hand-collapse the duplicate before retrying\n` +
      `  (edit the frontmatter to leave exactly one status: line, then retry)`
    );
  }

  const status = readFmField(split.fmText, 'status');
  const pickedUpBy = readFmField(split.fmText, 'picked_up_by');

  // Idempotency: no-op when already in_progress with the SAME session.
  if (status === 'in_progress' && pickedUpBy === opts.sessionId.trim()) {
    process.stdout.write(`memo-transition: ${opts.memo} already in_progress (picked_up_by ${opts.sessionId.trim()}) — no-op\n`);
    process.exit(0);
  }

  // Any other in_progress is a concurrency collision — fail loud.
  if (status === 'in_progress') {
    fail(`memo is already in_progress (held by ${pickedUpBy || '(empty)'}); release it first or use a different session`);
  }

  // Unexpected terminal or unknown state.
  if (status !== 'open' && status !== null) {
    fail(`unexpected current status "${status}" for claim — expected open`);
  }

  let fmText = split.fmText;

  // status → in_progress (replace existing key; insert anchored after title if missing)
  if (status === null) {
    fmText = insertFmField(fmText, 'status', 'in_progress', 'title');
  } else {
    fmText = replaceFmField(fmText, 'status', 'in_progress');
  }

  // picked_up_at — insert if absent (anchored after status)
  if (readFmField(fmText, 'picked_up_at') === null) {
    fmText = insertFmField(fmText, 'picked_up_at', opts.at.trim(), 'status');
  }

  // picked_up_by — insert if absent (anchored after picked_up_at)
  if (readFmField(fmText, 'picked_up_by') === null) {
    fmText = insertFmField(fmText, 'picked_up_by', opts.sessionId.trim(), 'picked_up_at');
  }

  // Validate post-mutation frontmatter before the file write — any violation exits
  // non-zero here, leaving the on-disk file unchanged.
  validateMemoFrontmatter(fmText);

  const fmNormalized = fmText.endsWith('\n') ? fmText : fmText + '\n';
  const rebuilt = `${split.preamble || ''}---\n${fmNormalized}---${split.bodyWithLeadingNewline}`;
  fs.writeFileSync(opts.memo, rebuilt);

  // Post-write self-verify: confirm exactly one status: key survived the write.
  const writtenSplit = splitFrontmatter(fs.readFileSync(opts.memo, 'utf8').replace(/\r\n/g, '\n'));
  if (!writtenSplit || countStatusKeys(writtenSplit.fmText) !== 1) {
    process.stderr.write(`memo-transition: INTERNAL ERROR — post-write status key count ≠ 1. Inspect ${opts.memo} immediately.\n`);
    process.exit(1);
  }

  process.stdout.write(`memo-transition: claimed ${opts.memo} (picked_up_by ${opts.sessionId.trim()})\n`);
  process.exit(0);
}

// --- action verb ----------------------------------------------------------------

function action(opts) {
  // OWNERSHIP GATE NOTE: claim-based ownership enforcement (in_progress→actioned stand-down
  // for memos held by a different live session) lives in the cs_action_memo bash wrapper in
  // lib/coordinator-archive-stamp.sh. Liveness is a shell-only predicate (_cs_claim_holder_live)
  // and is not computable here. A direct caller of this verb bypasses that gate — route all
  // terminal memo flips through cs_action_memo, not this verb directly.
  if (!opts.memo) fail('action requires --memo <path>');
  if (!fs.existsSync(opts.memo)) fail(`memo not found: ${opts.memo}`);

  // Mutually exclusive disposition modes.
  if (opts.decision && opts.actionedNote) {
    fail('action: --decision and --actioned-note are mutually exclusive');
  }
  if (!opts.decision && !opts.actionedNote) {
    fail('action requires either --decision <accepted|partial|declined> [--decision-note <text>] [--realized-by <ptr>] or --actioned-note <text>');
  }

  if (opts.decision) {
    const validDecisions = ['accepted', 'partial', 'declined'];
    if (!validDecisions.includes(opts.decision)) {
      fail(`action: --decision must be one of: ${validDecisions.join(', ')} (got "${opts.decision}")`);
    }
    // realized_by is required for accepted|partial (shape validated by cross-field seam).
    if ((opts.decision === 'accepted' || opts.decision === 'partial') && !opts.realizedBy) {
      fail(`action: --realized-by is required when --decision is ${opts.decision}`);
    }
  }

  const original = fs.readFileSync(opts.memo, 'utf8').replace(/\r\n/g, '\n');
  const split = splitFrontmatter(original);
  if (!split) fail(`no parseable YAML frontmatter in ${opts.memo}`);

  // Pre-mutation dup-key guard.
  const preDupCount = countStatusKeys(split.fmText);
  if (preDupCount >= 2) {
    fail(
      `memo has ${preDupCount} status: keys — hand-collapse the duplicate before retrying\n` +
      `  (edit the frontmatter to leave exactly one status: line, then retry)`
    );
  }

  const status = readFmField(split.fmText, 'status');

  // Idempotency: no-op when already at the exact target disposition.
  if (status === 'actioned') {
    // Review: code-reviewer slice A — F1: serializeYamlScalar wraps values containing quote-
    // trigger chars (`:` `#` `{` etc.) in YAML single-quotes. readFmField returns the raw on-
    // disk text including those quotes. Unquote before comparing against the unquoted CLI arg
    // to prevent a false "already actioned with a different disposition" exit on re-invocation.
    const unq = (r) => (r && r.startsWith("'") && r.endsWith("'")) ? r.slice(1, -1).replace(/''/g, "'") : r;
    let alreadyAtTarget = false;
    if (opts.decision) {
      const curDecision = readFmField(split.fmText, 'decision');
      const curDecisionNote = readFmField(split.fmText, 'decision_note');
      const curRealizedBy = readFmField(split.fmText, 'realized_by');
      alreadyAtTarget = curDecision === opts.decision &&
        (unq(curDecisionNote) || null) === (opts.decisionNote || null) &&
        (unq(curRealizedBy) || null) === (opts.realizedBy || null);
    } else {
      const curActionedNote = readFmField(split.fmText, 'actioned_note');
      alreadyAtTarget = (unq(curActionedNote) || null) === (opts.actionedNote || null);
    }
    if (alreadyAtTarget) {
      process.stdout.write(`memo-transition: ${opts.memo} already actioned at target disposition — no-op\n`);
      process.exit(0);
    }
    fail(`memo is already actioned with a different disposition — cannot re-action`);
  }

  if (status !== 'in_progress') {
    fail(`unexpected current status "${status || '(missing)'}" for action — expected in_progress`);
  }

  let fmText = split.fmText;

  // PRESERVE picked_up_by and picked_up_at — they are the claim-of-record for the archived memo.
  // status → actioned
  fmText = replaceFmField(fmText, 'status', 'actioned');

  if (opts.decision) {
    // decision field: replace if present, insert after status if absent.
    if (readFmField(fmText, 'decision') === null) {
      fmText = insertFmField(fmText, 'decision', opts.decision, 'status');
    } else {
      fmText = replaceFmField(fmText, 'decision', opts.decision);
    }
    // decision_note (optional): replace or insert after decision.
    if (opts.decisionNote) {
      if (readFmField(fmText, 'decision_note') === null) {
        fmText = insertFmField(fmText, 'decision_note', opts.decisionNote, 'decision');
      } else {
        fmText = replaceFmField(fmText, 'decision_note', opts.decisionNote);
      }
    }
    // realized_by (required for accepted|partial, absent for declined): replace or insert.
    if (opts.realizedBy) {
      const anchor = opts.decisionNote ? 'decision_note' : 'decision';
      if (readFmField(fmText, 'realized_by') === null) {
        fmText = insertFmField(fmText, 'realized_by', opts.realizedBy, anchor);
      } else {
        fmText = replaceFmField(fmText, 'realized_by', opts.realizedBy);
      }
    }
  } else {
    // Consult/fyi shape: write actioned_note only.
    if (readFmField(fmText, 'actioned_note') === null) {
      fmText = insertFmField(fmText, 'actioned_note', opts.actionedNote, 'status');
    } else {
      fmText = replaceFmField(fmText, 'actioned_note', opts.actionedNote);
    }
  }

  validateMemoFrontmatter(fmText);

  const fmNormalized = fmText.endsWith('\n') ? fmText : fmText + '\n';
  const rebuilt = `${split.preamble || ''}---\n${fmNormalized}---${split.bodyWithLeadingNewline}`;
  fs.writeFileSync(opts.memo, rebuilt);

  // Post-write self-verify.
  const writtenSplit = splitFrontmatter(fs.readFileSync(opts.memo, 'utf8').replace(/\r\n/g, '\n'));
  if (!writtenSplit || countStatusKeys(writtenSplit.fmText) !== 1) {
    process.stderr.write(`memo-transition: INTERNAL ERROR — post-write status key count ≠ 1. Inspect ${opts.memo} immediately.\n`);
    process.exit(1);
  }

  process.stdout.write(`memo-transition: actioned ${opts.memo}\n`);
  process.exit(0);
}

// --- release verb ---------------------------------------------------------------

function release(opts) {
  if (!opts.memo) fail('release requires --memo <path>');
  if (!fs.existsSync(opts.memo)) fail(`memo not found: ${opts.memo}`);

  const original = fs.readFileSync(opts.memo, 'utf8').replace(/\r\n/g, '\n');
  const split = splitFrontmatter(original);
  if (!split) fail(`no parseable YAML frontmatter in ${opts.memo}`);

  // Pre-mutation dup-key guard.
  const preDupCount = countStatusKeys(split.fmText);
  if (preDupCount >= 2) {
    fail(
      `memo has ${preDupCount} status: keys — hand-collapse the duplicate before retrying\n` +
      `  (edit the frontmatter to leave exactly one status: line, then retry)`
    );
  }

  const status = readFmField(split.fmText, 'status');

  // Idempotency: no-op when already open.
  if (status === 'open') {
    process.stdout.write(`memo-transition: ${opts.memo} already open — no-op\n`);
    process.exit(0);
  }

  if (status !== 'in_progress') {
    fail(`unexpected current status "${status || '(missing)'}" for release — expected in_progress`);
  }

  let fmText = split.fmText;

  // status → open
  fmText = replaceFmField(fmText, 'status', 'open');

  // CLEAR picked_up_by and picked_up_at entirely — release reverts the claim.
  // Negative-spec: do NOT preserve these fields (contrast with action, which does preserve them).
  fmText = removeFmField(fmText, 'picked_up_by');
  fmText = removeFmField(fmText, 'picked_up_at');

  validateMemoFrontmatter(fmText);

  const fmNormalized = fmText.endsWith('\n') ? fmText : fmText + '\n';
  const rebuilt = `${split.preamble || ''}---\n${fmNormalized}---${split.bodyWithLeadingNewline}`;
  fs.writeFileSync(opts.memo, rebuilt);

  // Post-write self-verify.
  const writtenSplit = splitFrontmatter(fs.readFileSync(opts.memo, 'utf8').replace(/\r\n/g, '\n'));
  if (!writtenSplit || countStatusKeys(writtenSplit.fmText) !== 1) {
    process.stderr.write(`memo-transition: INTERNAL ERROR — post-write status key count ≠ 1. Inspect ${opts.memo} immediately.\n`);
    process.exit(1);
  }

  process.stdout.write(`memo-transition: released ${opts.memo} (status reset to open, claim cleared)\n`);
  process.exit(0);
}

// --- main -----------------------------------------------------------------------

function main() {
  const opts = parseArgs(process.argv);
  switch (opts.verb) {
    case 'claim':
      claim(opts);
      break;
    case 'action':
      action(opts);
      break;
    case 'release':
      release(opts);
      break;
    default:
      fail(`unknown verb: ${opts.verb || '(none)'} — supported: claim, action, release`);
  }
}

main();
