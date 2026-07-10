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
 *   handoff-transition.js supersede --handoff <path>
 *   handoff-transition.js ship --handoff <path>
 *   handoff-transition.js repark --handoff <path>
 *   handoff-transition.js gate-recheck --handoff <path> --at <ISO date> [--cleared]
 *
 * The `gate-recheck` verb performs the awaiting_gate re-check transition as ONE atomic
 * file write. `--at` is always stamped into `last_gate_recheck:`. `--cleared` additionally
 * flips deployment_state: awaiting_gate → ready_to_fire and strips gate_dependency. See
 * the gateRecheck() docstring below for the full contract.
 *
 * Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C5b
 *
 * The `repark` verb performs an intentional-unpause (re-park) transition as ONE atomic file write:
 *   - deployment_state: in_flight → ready_to_fire
 * Does NOT change status: (stays consumed — the claim/consumed_by/consumed_at record is
 * untouched; repark is a deployment_state-only unpause, not a fresh pickup). For a LIVE
 * session choosing to pause its own in-flight work and make it re-fireable — distinct from
 * the crash-orphan reaper below, which targets a DEAD holder's abandoned in_flight node.
 * Idempotency: no-op exit 0 when deployment_state==ready_to_fire already.
 * Fails loud if deployment_state is not currently in_flight (repark is defined ONLY as the
 * in_flight → ready_to_fire transition; parking from any other state is not this verb's job).
 *
 * Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C5a
 *
 * The `ship` verb sets deployment_state: shipped in place (stamp-only path for
 * coordinator-handoff-archive.sh --stamp-only, which skips git mv and delegates
 * archival to the async sweep-shipped-handoffs.sh janitor):
 *   - deployment_state: <any> → shipped
 * Does NOT change status:. Idempotency: no-op exit 0 when deployment_state==shipped.
 * shipped_in: is assumed already stamped by stamp_shipped_in() before this call.
 *
 * Spec backlink: docs/plans/2026-06-30-session-terminator-mechanism-unification.md § C3a
 *
 * The `supersede` verb performs the supersession terminal transition as ONE atomic
 * file write (no half-mutated on-disk intermediate):
 *   - status: <any> → consumed
 *   - deployment_state: <any> → abandoned
 * No consumed_at/consumed_by are written — supersession does not create a pickup claim.
 * shipped_in: is assumed already stamped by stamp_shipped_in() before this call.
 * Idempotency: no-op exit 0 when status==consumed AND deployment_state==abandoned.
 *
 * Spec backlink: docs/plans/2026-06-30-session-terminator-mechanism-unification.md § C3b
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
 * Fail-loud (the Staff Engineer P2): an empty/missing --session-id is rejected with a non-zero
 *   exit and NO write — never write `consumed_by:` empty (it would corrupt the
 *   claim-gate idempotency check and the audit trail the freeze hook rests on).
 *
 * Exit codes:
 *   0 — transition applied OR already-at-target no-op
 *   1 — error (bad args, empty session-id, missing frontmatter, I/O failure)
 *
 * Frontmatter primitives (splitFrontmatter/readFmField/serializeYamlScalar/
 * replaceFmField/insertFmField) are required from the canonical shared module
 * lib/schema.js — reconciled from the 5 divergent copies (this file, memo-transition.js,
 * normalize-consumed-frontmatter.js, stamp-shipped-in.js) into ONE implementation.
 * See lib/schema.js's docstrings above each primitive for the reconciliation rationale.
 */

const fs = require('fs');
const path = require('path');

const {
  splitFrontmatter,
  readFmField,
  serializeYamlScalar,
  replaceFmField,
  insertFmField,
  removeFmField,
} = require(path.join(__dirname, 'lib', 'schema.js'));

// --- D4 schema-validation seam (Ask 2 adoption point) ---------------------------

/**
 * validateHandoffFrontmatter — parses post-transition frontmatter YAML and runs
 * it through the handoff schema validator (validateFrontmatter + applyCrossFieldRules
 * via schema.js) before the file write. Exits non-zero with a clear message on
 * any schema or cross-field-rule violation. Fails loud if the handoff schema cannot
 * be found (unexpected missing schema — indicates an installation issue).
 * Review: code-reviewer ROBUSTNESS — docstring updated to match actual behavior (fails
 *   loud on missing schema, not no-op); the old "no-op" claim was incorrect.
 *
 * D5: reuses schema.js primitives; no parallel validation logic.
 * Spec backlink: archive/specs/2026-06/2026-06-25-example-initiative-tc-4-fleet-machinery-contract-emit.md § Chunk A3a
 */
function validateHandoffFrontmatter(fmText) {
  // Lazy-require schema.js so the module only loads when a consume is actually
  // in progress — avoids startup cost on parse-error / arg-validation paths.
  const schemaLib = require(path.join(__dirname, 'lib', 'schema.js'));
  const schemasDir = path.join(__dirname, '..', 'schemas');

  let schemas;
  try {
    schemas = schemaLib.loadSchemas(schemasDir);
  } catch (e) {
    // Schema directory missing or parse error — fail loud so infra issues surface.
    fail(`validateHandoffFrontmatter: could not load schemas from ${schemasDir}: ${e.message}`);
  }

  const handoffSchema = schemas['handoff'];
  if (!handoffSchema) {
    // Handoff schema absent — fail loud (unexpected missing schema).
    fail(`validateHandoffFrontmatter: handoff schema not found in ${schemasDir}`);
  }

  // Parse the frontmatter YAML body (without --- delimiters) using the same
  // parser schema.js uses internally — single source of truth (D5).
  // Review: code-reviewer ROBUSTNESS — use public parseYamlBlock (not test-only _parseYaml).
  const fm = schemaLib.parseYamlBlock(fmText);

  const result = schemaLib.validateFrontmatter(fm, handoffSchema);
  if (!result.ok) {
    const details = (result.errors || [])
      .map(e => `  ${e.field}: ${e.error}${e.hint ? ' (' + e.hint + ')' : ''}`)
      .join('\n');
    fail(`handoff frontmatter validation failed:\n${details}\n  (add missing fields to the handoff frontmatter, then retry)`);
  }
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
  const opts = { verb, handoff: null, sessionId: null, at: null, cleared: false };
  // Review: code-reviewer A9 — bounds-check before consuming next arg so a trailing flag
  // with no value gets a clear error rather than silently assigning undefined.
  for (let i = 1; i < args.length; i++) {
    const a = args[i];
    const nextVal = () => { if (i + 1 >= args.length) fail('flag requires a value: ' + a); return args[++i]; };
    if (a === '--handoff') opts.handoff = nextVal();
    else if (a === '--session-id') opts.sessionId = nextVal();
    else if (a === '--at') opts.at = nextVal();
    else if (a === '--cleared') opts.cleared = true;
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

  // Validates post-mutation frontmatter before the file write — any schema error exits
  // non-zero here, leaving the on-disk file unchanged. All fmText mutations above have
  // already been applied in-memory; validation is the gate before the write commits them.
  validateHandoffFrontmatter(fmText);

  const fmNormalized = fmText.endsWith('\n') ? fmText : fmText + '\n';
  const rebuilt = `${split.preamble || ''}---\n${fmNormalized}---${split.bodyWithLeadingNewline}`;
  fs.writeFileSync(opts.handoff, rebuilt);
  process.stdout.write(`handoff-transition: consumed ${opts.handoff} (consumed_by ${opts.sessionId})\n`);
  process.exit(0);
}

// --- ship verb ------------------------------------------------------------------

/**
 * ship — set deployment_state: shipped in place (stamp-only path).
 * Called by coordinator-handoff-archive.sh --stamp-only AFTER stamp_shipped_in and
 * after the live-children guard clears. The handoff remains in state/handoffs/ so
 * sweep-shipped-handoffs.sh can pick it up later for the git mv step.
 * Does NOT mutate status: — the handoff may still be status: active or consumed.
 */
function ship(opts) {
  if (!opts.handoff) fail('ship requires --handoff <path>');
  if (!fs.existsSync(opts.handoff)) fail(`handoff not found: ${opts.handoff}`);

  // Review: A2 — normalize CRLF on read so splitFrontmatter's \n-based parsing works
  // on Windows-authored handoffs (DR-148 cross-platform portability).
  const original = fs.readFileSync(opts.handoff, 'utf8').replace(/\r\n/g, '\n');
  const split = splitFrontmatter(original);
  if (!split) fail(`no parseable YAML frontmatter in ${opts.handoff}`);

  const deployment = readFmField(split.fmText, 'deployment_state');

  // Idempotency: no-op when already shipped.
  if (deployment === 'shipped') {
    process.stdout.write(`handoff-transition: ${opts.handoff} already deployment_state:shipped — no-op\n`);
    process.exit(0);
  }

  let fmText = split.fmText;

  // deployment_state → shipped (replace if present, insert after status if missing)
  if (deployment === null) {
    fmText = insertFmField(fmText, 'deployment_state', 'shipped', 'status');
  } else {
    fmText = replaceFmField(fmText, 'deployment_state', 'shipped');
  }

  validateHandoffFrontmatter(fmText);

  const fmNormalized = fmText.endsWith('\n') ? fmText : fmText + '\n';
  const rebuilt = `${split.preamble || ''}---\n${fmNormalized}---${split.bodyWithLeadingNewline}`;
  fs.writeFileSync(opts.handoff, rebuilt);
  process.stdout.write(`handoff-transition: shipped ${opts.handoff} (deployment_state: shipped)\n`);
  process.exit(0);
}

// --- supersede verb -------------------------------------------------------------

function supersede(opts) {
  if (!opts.handoff) fail('supersede requires --handoff <path>');
  if (!fs.existsSync(opts.handoff)) fail(`handoff not found: ${opts.handoff}`);

  // Review: code-reviewer A2 — normalize CRLF on read so splitFrontmatter's \n-based
  // parsing works on Windows-authored handoffs (DR-148 cross-platform portability).
  const original = fs.readFileSync(opts.handoff, 'utf8').replace(/\r\n/g, '\n');
  const split = splitFrontmatter(original);
  if (!split) fail(`no parseable YAML frontmatter in ${opts.handoff}`);

  const status = readFmField(split.fmText, 'status');
  const deployment = readFmField(split.fmText, 'deployment_state');

  // Idempotency: no-op ONLY at the full target state.
  if (status === 'consumed' && deployment === 'abandoned') {
    process.stdout.write(`handoff-transition: ${opts.handoff} already consumed+abandoned — no-op\n`);
    process.exit(0);
  }

  let fmText = split.fmText;

  // status → consumed (replace existing key; insert anchored after title if missing)
  if (status !== 'consumed') {
    if (status === null) {
      fmText = insertFmField(fmText, 'status', 'consumed', 'title');
    } else {
      fmText = replaceFmField(fmText, 'status', 'consumed');
    }
  }

  // deployment_state → abandoned (replace if present, insert after status if missing)
  if (deployment !== 'abandoned') {
    if (deployment === null) {
      fmText = insertFmField(fmText, 'deployment_state', 'abandoned', 'status');
    } else {
      fmText = replaceFmField(fmText, 'deployment_state', 'abandoned');
    }
  }

  // Validates post-mutation frontmatter before the file write — any schema error exits
  // non-zero here, leaving the on-disk file unchanged.
  validateHandoffFrontmatter(fmText);

  const fmNormalized = fmText.endsWith('\n') ? fmText : fmText + '\n';
  const rebuilt = `${split.preamble || ''}---\n${fmNormalized}---${split.bodyWithLeadingNewline}`;
  fs.writeFileSync(opts.handoff, rebuilt);
  process.stdout.write(`handoff-transition: superseded ${opts.handoff} (status: consumed, deployment_state: abandoned)\n`);
  process.exit(0);
}

// --- repark verb ----------------------------------------------------------------

/**
 * repark — intentional-pause transition: deployment_state in_flight → ready_to_fire.
 * Called for a LIVE session choosing to unpause its own claimed-but-paused handoff back
 * into the ready pool (freeze-hook-safe Bash node-write, same pattern as consume/ship/
 * supersede). status: is untouched — the handoff stays consumed; only deployment_state
 * flips, so the next /pickup on this handoff sees a re-fireable node rather than a stuck
 * in_flight one.
 * Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C5a
 */
function repark(opts) {
  if (!opts.handoff) fail('repark requires --handoff <path>');
  if (!fs.existsSync(opts.handoff)) fail(`handoff not found: ${opts.handoff}`);

  // Review: A2 — normalize CRLF on read so splitFrontmatter's \n-based parsing works
  // on Windows-authored handoffs (DR-148 cross-platform portability).
  const original = fs.readFileSync(opts.handoff, 'utf8').replace(/\r\n/g, '\n');
  const split = splitFrontmatter(original);
  if (!split) fail(`no parseable YAML frontmatter in ${opts.handoff}`);

  const deployment = readFmField(split.fmText, 'deployment_state');

  // Idempotency: no-op when already parked.
  if (deployment === 'ready_to_fire') {
    process.stdout.write(`handoff-transition: ${opts.handoff} already deployment_state:ready_to_fire — no-op\n`);
    process.exit(0);
  }

  // Fail loud on any state other than in_flight — repark is defined ONLY as the
  // in_flight → ready_to_fire transition, not a general deployment_state reset.
  if (deployment !== 'in_flight') {
    fail(`repark requires deployment_state:in_flight (found "${deployment}") — ${opts.handoff}`);
  }

  const fmText = replaceFmField(split.fmText, 'deployment_state', 'ready_to_fire');

  validateHandoffFrontmatter(fmText);

  const fmNormalized = fmText.endsWith('\n') ? fmText : fmText + '\n';
  const rebuilt = `${split.preamble || ''}---\n${fmNormalized}---${split.bodyWithLeadingNewline}`;
  fs.writeFileSync(opts.handoff, rebuilt);
  process.stdout.write(`handoff-transition: reparked ${opts.handoff} (deployment_state: ready_to_fire)\n`);
  process.exit(0);
}

// --- gate-recheck verb -----------------------------------------------------------

/**
 * gate-recheck — awaiting_gate re-check transition, one atomic file write:
 *   - `--at <ISO date>` is ALWAYS stamped into `last_gate_recheck:` (replace if present,
 *     insert after `gate_dependency` if absent) — recording that the gate was re-checked,
 *     regardless of outcome. `--at` is validated as a well-formed date AND rejected (fail
 *     loud, no write) if chronologically earlier than the existing `last_gate_recheck:` —
 *     an unconditional overwrite could reset handoff-gate-aging.sh's 7-day recheck cooldown
 *     backward. Matches the fail-loud discipline `consume` uses on `--session-id`.
 *   - `--cleared` additionally flips `deployment_state: awaiting_gate → ready_to_fire` AND
 *     strips `gate_dependency` entirely (schema.js's ready_to_fire→gate_dependency-forbidden
 *     cross-field rule requires the field be absent, not merely blank — see
 *     bin/lib/schema.js CROSS_FIELD_RULES.handoff, the `must be empty or omitted when
 *     deployment_state=ready_to_fire` rule).
 *   - Without `--cleared`: the gate is still closed — only `last_gate_recheck:` is stamped;
 *     `deployment_state` stays `awaiting_gate` and `gate_dependency` is untouched.
 * Does NOT change `status:`. Fails loud if `deployment_state` is not currently
 * `awaiting_gate` — gate-recheck is defined ONLY as the awaiting_gate re-check/clear
 * transition, not a general deployment_state/last_gate_recheck stamper.
 * Idempotency: with `--cleared`, no-op exit 0 when deployment_state is already
 * ready_to_fire (the aging-reconcile caller may re-invoke after a prior clear).
 *
 * Replaces the plan's prior prose-only "fold it into the Step 5 mutation pass" Edit —
 * mirrors consume/ship/supersede/repark: atomic, freeze-hook-safe (Bash-driven node
 * write, invisible to the Edit-only consumed-handoff freeze hook), single authorized
 * writer for this transition.
 *
 * Spec backlink: docs/plans/2026-07-08-handoff-spinoff-robustness-hardening.md § C5b
 */
function gateRecheck(opts) {
  if (!opts.handoff) fail('gate-recheck requires --handoff <path>');
  if (!opts.at || !opts.at.trim()) fail('gate-recheck requires --at <ISO date>');
  if (!fs.existsSync(opts.handoff)) fail(`handoff not found: ${opts.handoff}`);

  // Review: A2 — normalize CRLF on read so splitFrontmatter's \n-based parsing works
  // on Windows-authored handoffs (DR-148 cross-platform portability).
  const original = fs.readFileSync(opts.handoff, 'utf8').replace(/\r\n/g, '\n');
  const split = splitFrontmatter(original);
  if (!split) fail(`no parseable YAML frontmatter in ${opts.handoff}`);

  const deployment = readFmField(split.fmText, 'deployment_state');

  // Idempotency: no-op ONLY for the --cleared path already at target (ready_to_fire).
  // A no-`--cleared` re-run always re-stamps last_gate_recheck (that IS the point of a
  // re-check call) so it does not short-circuit here.
  if (opts.cleared && deployment === 'ready_to_fire') {
    process.stdout.write(`handoff-transition: ${opts.handoff} already deployment_state:ready_to_fire — no-op\n`);
    process.exit(0);
  }

  // Fail loud on any state other than awaiting_gate — gate-recheck is defined ONLY
  // as the awaiting_gate re-check/clear transition.
  if (deployment !== 'awaiting_gate') {
    fail(`gate-recheck requires deployment_state:awaiting_gate (found "${deployment}") — ${opts.handoff}`);
  }

  // --at monotonicity guard (Review: code-reviewer F4) — fail loud on a malformed date
  // or one chronologically earlier than the existing last_gate_recheck: an unconditional
  // overwrite could silently reset handoff-gate-aging.sh's 7-day recheck cooldown backward.
  const atMs = Date.parse(opts.at);
  if (Number.isNaN(atMs)) {
    fail(`gate-recheck --at is not a valid date: "${opts.at}"`);
  }

  let fmText = split.fmText;

  // last_gate_recheck — always stamped (replace if present, insert after
  // gate_dependency if absent).
  const existingRecheck = readFmField(fmText, 'last_gate_recheck');
  if (existingRecheck !== null) {
    const existingMs = Date.parse(existingRecheck);
    if (!Number.isNaN(existingMs) && atMs < existingMs) {
      fail(`gate-recheck --at (${opts.at}) is earlier than the existing last_gate_recheck ` +
        `(${existingRecheck}) — refusing to reset the aging cooldown backward`);
    }
    fmText = replaceFmField(fmText, 'last_gate_recheck', opts.at);
  } else {
    fmText = insertFmField(fmText, 'last_gate_recheck', opts.at, 'gate_dependency');
  }

  if (opts.cleared) {
    fmText = replaceFmField(fmText, 'deployment_state', 'ready_to_fire');
    // gate_dependency must be entirely absent at ready_to_fire (schema.js cross-field
    // rule) — strip, not blank.
    fmText = removeFmField(fmText, 'gate_dependency');
  }

  validateHandoffFrontmatter(fmText);

  const fmNormalized = fmText.endsWith('\n') ? fmText : fmText + '\n';
  const rebuilt = `${split.preamble || ''}---\n${fmNormalized}---${split.bodyWithLeadingNewline}`;
  fs.writeFileSync(opts.handoff, rebuilt);
  const outcome = opts.cleared
    ? `cleared (deployment_state: ready_to_fire, gate_dependency stripped)`
    : `still closed (last_gate_recheck: ${opts.at})`;
  process.stdout.write(`handoff-transition: gate-recheck ${opts.handoff} — ${outcome}\n`);
  process.exit(0);
}

function main() {
  const opts = parseArgs(process.argv);
  switch (opts.verb) {
    case 'consume':
      consume(opts);
      break;
    case 'ship':
      ship(opts);
      break;
    case 'supersede':
      supersede(opts);
      break;
    case 'repark':
      repark(opts);
      break;
    case 'gate-recheck':
      gateRecheck(opts);
      break;
    default:
      fail(`unknown verb: ${opts.verb || '(none)'} — supported: consume, ship, supersede, repark, gate-recheck`);
  }
}

main();
