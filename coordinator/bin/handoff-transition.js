#!/usr/bin/env node
'use strict';
/**
 * handoff-transition.js — atomic handoff-lifecycle frontmatter transitions.
 *
 * Purpose: the single authorized writer of a consumed/shipped handoff's lifecycle
 * frontmatter, invoked from Bash by the cs_*_handoff wrapper family in
 * lib/coordinator-archive-stamp.sh. Because it is a Bash-driven node write (not a
 * Write/Edit tool call), it is structurally invisible to the consumed-handoff freeze
 * hook (hooks/scripts/block-consumed-handoff-edit.sh matches only
 * Write|Edit|MultiEdit|NotebookEdit) — so the lifecycle write sails through while
 * manual Edit progress-appends stay blocked. See the plan's § Premise corrections.
 *
 * Spec backlink: docs/plans/2026-06-24-handoff-lifecycle-transition-helper.md § C1
 *
 * Usage:
 *   handoff-transition.js consume --handoff <path> --session-id <id> --at <ISO>
 *
 * The `consume` verb performs the pickup-time transition as ONE atomic file write
 * (no half-consumed on-disk intermediate):
 *   - status: <non-consumed> → consumed
 *   - deployment_state: <any> → in_flight
 *   - consumed_at: <ISO>      (inserted if absent)
 *   - consumed_by: <session>  (inserted if absent)
 *   - pickup_ready:           preserved untouched (authorial-intent record)
 *
 * Idempotency (D5): no-op exit 0 ONLY when the FULL target state already holds
 *   (status==consumed AND deployment_state==in_flight). A partial prior state
 *   (status==consumed but deployment_state!=in_flight — e.g. a normalize sweep that
 *   flipped status but not deployment_state) COMPLETES the transition rather than
 *   short-circuiting, so pickup's documented `in_flight` invariant always holds.
 *
 * Fail-loud (Patrik P2): an empty/missing --session-id is rejected with a non-zero
 *   exit and NO write — never write `consumed_by:` empty (it would corrupt the
 *   claim-gate idempotency check and the audit trail the freeze hook rests on).
 *
 * Exit codes:
 *   0 — transition applied OR already-at-target no-op
 *   1 — error (bad args, empty session-id, missing frontmatter, I/O failure)
 *
 * Frontmatter primitives are COPIED from normalize-consumed-frontmatter.js (the
 * canonical safer variant: 4-arg-anchored insertFmField + block-scalar-guarded
 * replaceFmField), matching the established stamp-shipped-in.js copy pattern. DRY
 * consolidation of the divergent copies is deferred — see the plan § Anti-scope.
 */

const fs = require('fs');

// --- Frontmatter primitives (copied from normalize-consumed-frontmatter.js) -----

function splitFrontmatter(content) {
  // Tolerate an optional leading preamble — blank lines and complete HTML comment
  // blocks (`<!-- ... -->`) — before the opening `---`. Installer-seeded batons carry
  // a provenance comment ahead of the frontmatter (project_rag_setup / holodeck
  // installers); the preamble is captured and reassembled verbatim on write so the
  // provenance survives the lifecycle edit. Spec backlink: handoff-lifecycle helper plan.
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
  // [ \t]* (not \s*) — \s eats newlines and would consume the body's leading blank line.
  const closeRe = /^---[ \t]*$/m;
  const closeMatch = closeRe.exec(rest);
  if (!closeMatch) return null;
  const fmText = rest.slice(0, closeMatch.index);
  const bodyStart = closeMatch.index + closeMatch[0].length;
  const bodyWithLeadingNewline = rest.slice(bodyStart);
  return { preamble, fmText, bodyWithLeadingNewline };
}

function readFmField(fmText, key) {
  // Review: code-reviewer A1 — boundary lookahead prevents a key matching a longer key's prefix
  // (e.g. `status` must not match `status_message:`).
  const re = new RegExp('^' + key + ':(?=[ \\t]|$)\\s*(.*?)\\s*$', 'm');
  const m = re.exec(fmText);
  return m ? m[1].trim() : null;
}

function serializeYamlScalar(value) {
  const needsQuoting = /[#:{}\[\],&*!|>"'%@`]/.test(value) ||
                       value.startsWith('-') ||
                       value.startsWith('?') ||
                       value.startsWith(' ');
  if (!needsQuoting) return value;
  return `'${value.replace(/'/g, "''")}'`;
}

function replaceFmField(fmText, key, value) {
  // Block-scalar guard (normalize-consumed Patrik F1): fail loud rather than
  // truncating a folded/literal YAML value into a single line.
  const currentValue = readFmField(fmText, key);
  if (currentValue !== null && (currentValue.startsWith('>') || currentValue.startsWith('|'))) {
    // Review: code-reviewer A4 — only append `...` when the value was actually truncated.
    throw new Error(
      `handoff-transition: field "${key}" uses a block-scalar YAML value ` +
      `("${currentValue.length > 40 ? currentValue.slice(0, 40) + '...' : currentValue}") — cannot safely replace single-line. ` +
      `Fix the frontmatter manually.`
    );
  }
  // Review: code-reviewer A1 — boundary: `key:` requires whitespace or EOL after colon so
  // `status` does not match `status_message:` etc.
  const re = new RegExp('^(' + key + ':(?=[ \\t]|$)\\s*).*$', 'm');
  return fmText.replace(re, `$1${serializeYamlScalar(value)}`);
}

function insertFmField(fmText, key, value, afterKey) {
  // Insert `key: value` immediately after the line matching `afterKey:`.
  // If afterKey not present, append to end of frontmatter.
  // Review: code-reviewer A1 — boundary lookahead on afterKey prevents prefix-match.
  const afterRe = new RegExp('^' + afterKey + ':(?=[ \\t]|$).*$', 'm');
  const m = afterRe.exec(fmText);
  if (m) {
    const insertAt = m.index + m[0].length;
    return fmText.slice(0, insertAt) + `\n${key}: ${serializeYamlScalar(value)}` + fmText.slice(insertAt);
  }
  const trimmed = fmText.replace(/\s+$/, '');
  return `${trimmed}\n${key}: ${serializeYamlScalar(value)}\n`;
}

// --- D4 schema-validation seam (Ask 2 adoption point) ---------------------------

/**
 * validateHandoffFrontmatter — permissive no-op stub. When Ask 2 (handoff body
 * schema for project-opticon) lands, this validates the post-transition frontmatter
 * against the handoff schema before the write, the way cross-repo-memo validates
 * memo frontmatter. Until then it accepts everything.
 * TODO(ask2): wire to the handoff schema validator once defined.
 */
function validateHandoffFrontmatter(_fmText) {
  return;
}

// --- consume verb ---------------------------------------------------------------

function fail(msg) {
  process.stderr.write(`handoff-transition: ${msg}\n`);
  process.exit(1);
}

function parseArgs(argv) {
  const args = argv.slice(2);
  // Review: code-reviewer A8 — explicit null (not undefined) when no verb given, so
  // switch default branch receives null and `opts.verb || '(none)'` works consistently.
  const verb = args.length > 0 ? args[0] : null;
  const opts = { verb, handoff: null, sessionId: null, at: null };
  // Review: code-reviewer A9 — bounds-check before consuming next arg so a trailing flag
  // with no value gets a clear error rather than silently assigning undefined.
  for (let i = 1; i < args.length; i++) {
    const a = args[i];
    const nextVal = () => { if (i + 1 >= args.length) fail('flag requires a value: ' + a); return args[++i]; };
    if (a === '--handoff') opts.handoff = nextVal();
    else if (a === '--session-id') opts.sessionId = nextVal();
    else if (a === '--at') opts.at = nextVal();
    else fail(`unknown argument: ${a}`);
  }
  return opts;
}

function consume(opts) {
  if (!opts.handoff) fail('consume requires --handoff <path>');
  // Fail-loud on empty/missing session-id — never write `consumed_by:` empty.
  if (!opts.sessionId || !opts.sessionId.trim()) {
    fail('consume requires a non-empty --session-id (empty consumed_by would corrupt the claim gate)');
  }
  if (!opts.at || !opts.at.trim()) fail('consume requires --at <ISO timestamp>');
  if (!fs.existsSync(opts.handoff)) fail(`handoff not found: ${opts.handoff}`);

  // Review: code-reviewer A2 — normalize CRLF on read so splitFrontmatter's \n-based
  // parsing works on Windows-authored handoffs (DR-148 cross-platform portability).
  const original = fs.readFileSync(opts.handoff, 'utf8').replace(/\r\n/g, '\n');
  const split = splitFrontmatter(original);
  if (!split) fail(`no parseable YAML frontmatter in ${opts.handoff}`);

  const status = readFmField(split.fmText, 'status');
  const deployment = readFmField(split.fmText, 'deployment_state');

  // Idempotency: no-op ONLY at the full target state. Partial state completes.
  if (status === 'consumed' && deployment === 'in_flight') {
    process.stdout.write(`handoff-transition: ${opts.handoff} already consumed+in_flight — no-op\n`);
    process.exit(0);
  }

  let fmText = split.fmText;

  // Review: code-reviewer A7 — intentional read/mutation asymmetry below:
  // `status` and `deployment` were read from split.fmText BEFORE any mutations (they gate
  // which branches to take). `consumed_at`/`consumed_by` are re-read from the evolving
  // `fmText` AFTER each insertion above them — so their presence checks account for
  // insertions made by this same run (e.g. a fresh file that needs both fields added).
  // This is correct, not fragile: the pre-mutation reads are control-flow gates; the
  // post-mutation reads are idempotency guards for the insert-if-absent fields.

  // Consume writes literal target values 'consumed' / 'in_flight' inline below.
  // bin/lib/consumed-marker.js exports terminal-state SETS + a marker regex (used by the
  // normalizer to detect terminal state), not target-value strings — so it is intentionally
  // NOT imported here; importing it would add an abstraction with no concrete benefit for
  // this writer. Review: code-reviewer A10.

  // status → consumed (replace existing key; insert anchored after title if missing)
  if (status !== 'consumed') {
    if (status === null) {
      fmText = insertFmField(fmText, 'status', 'consumed', 'title');
    } else {
      fmText = replaceFmField(fmText, 'status', 'consumed');
    }
  }

  // deployment_state → in_flight (replace if present, insert after status if missing)
  if (deployment !== 'in_flight') {
    if (deployment === null) {
      fmText = insertFmField(fmText, 'deployment_state', 'in_flight', 'status');
    } else {
      fmText = replaceFmField(fmText, 'deployment_state', 'in_flight');
    }
  }

  // consumed_at — insert if absent (anchored after deployment_state)
  // Review: code-reviewer A3 — anchor after deployment_state (not status) so field order
  // matches spec: status → deployment_state → consumed_at → consumed_by.
  if (readFmField(fmText, 'consumed_at') === null) {
    fmText = insertFmField(fmText, 'consumed_at', opts.at, 'deployment_state');
  }

  // consumed_by — insert if absent (anchored after consumed_at)
  if (readFmField(fmText, 'consumed_by') === null) {
    fmText = insertFmField(fmText, 'consumed_by', opts.sessionId, 'consumed_at');
  }

  validateHandoffFrontmatter(fmText);

  const fmNormalized = fmText.endsWith('\n') ? fmText : fmText + '\n';
  const rebuilt = `${split.preamble || ''}---\n${fmNormalized}---${split.bodyWithLeadingNewline}`;
  fs.writeFileSync(opts.handoff, rebuilt);
  process.stdout.write(`handoff-transition: consumed ${opts.handoff} (consumed_by ${opts.sessionId})\n`);
  process.exit(0);
}

function main() {
  const opts = parseArgs(process.argv);
  switch (opts.verb) {
    case 'consume':
      consume(opts);
      break;
    default:
      fail(`unknown verb: ${opts.verb || '(none)'} — supported: consume`);
  }
}

main();
