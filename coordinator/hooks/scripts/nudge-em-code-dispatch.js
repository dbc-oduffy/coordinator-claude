'use strict';
/**
 * nudge-em-code-dispatch.js — PreToolUse hook that offers dispatch over inline
 * code-file authoring when the EM (main-agent) writes a non-doc/data file.
 *
 * Design-as-offers: leads with the dispatcher path (/execute-plan, fan-out wave)
 * before naming the inline carve-out.  NEVER exits non-zero — NEVER blocks.
 *
 * Negative-spec: subagent writes (agent_id present in payload) are ALWAYS allowed
 * silently; executors are supposed to write code.  Doc/data extensions are allowed
 * silently — the nudge is for code files only (denylist shape, not allowlist).
 *
 * Sentinel suppression: the EM may create /tmp/coordinator-dispatch-nudge-ok-<SESSION_ID>
 * to suppress the nudge for an authorized inline run.  Autonomous-run sentinel
 * /tmp/autonomous-run-<SESSION_ID> (written by /autonomous-mode) also suppresses.
 *
 * Spec backlink: coordinator-tripwires.md § NUDGE-EM-CODE-DISPATCH
 * Design: docs/wiki/eager-agent-calibration.md (design-as-offers)
 */

const fs   = require('fs');
const os   = require('os');
const path = require('path');

// ---------------------------------------------------------------------------
// Doc / data extension denylist — nudge fires on everything EXCEPT these.
// A code-allowlist would let .sh, .rb, .kt, .sql, .swift, extensionless scripts
// escape.  "Guards match conditions, not containers."
// ---------------------------------------------------------------------------
const DOC_DATA_EXTENSIONS = new Set([
  '.md', '.yaml', '.yml', '.json', '.txt', '.toml',
  '.csv', '.lock', '.cfg', '.ini',
]);

// ---------------------------------------------------------------------------
// Session-ID resolution
// Tries payload.session_id first, then falls back to a <hostname>-<pid> key.
// The fallback is stable within one node process invocation and collides only
// if two sessions share a machine + pid (astronomically unlikely in practice).
// ---------------------------------------------------------------------------
function resolveSessionId(payload) {
  const sid = payload.session_id;
  if (sid && typeof sid === 'string' && sid.trim().length > 0) {
    return sid.trim();
  }
  // Fallback: hostname + pid — NOT persistent across hook re-invocations for
  // the same session, so sentinel files written using this fallback will only
  // work if the hook happens to be invoked by the same OS pid.  This is a
  // known limitation; document and don't crash.
  // FALLBACK-NOTE: if payload.session_id is absent/empty, the sentinel path
  // constructed from this fallback is pid-scoped.  The EM should use the
  // payload's session_id to derive the correct sentinel path when writing it
  // manually; the hook will match only if called under the same pid.
  const hostname = os.hostname().replace(/[^a-zA-Z0-9_-]/g, '-');
  return `${hostname}-${process.pid}`;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

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

  // --- Bypass 1: subagent writes are allowed unconditionally ---
  // agent_id present in payload → this is a subagent executor; executors are
  // supposed to write code.  Allow silently.
  if (Object.prototype.hasOwnProperty.call(payload, 'agent_id')) {
    process.exit(0);
  }

  // --- Extract file path ---
  // Review: code-reviewer — MultiEdit payloads carry no top-level file_path;
  // they carry tool_input.edits[].file_path instead (same pattern as
  // nudge-windows-subprocess-popup.sh and block-bin-polyglot-break.sh).
  // Select the first edit whose extension is NOT in the doc/data denylist so
  // the nudge fires on the same conditions as a plain Write to that file.
  const toolInput = payload.tool_input || {};
  let filePath = toolInput.file_path;

  if (!filePath && Array.isArray(toolInput.edits)) {
    for (const edit of toolInput.edits) {
      const editExt = path.extname(edit.file_path || '').toLowerCase();
      if (!DOC_DATA_EXTENSIONS.has(editExt)) {
        filePath = edit.file_path;
        break;
      }
    }
  }

  if (!filePath) process.exit(0);

  // --- Bypass 2: doc/data extension denylist ---
  const ext = path.extname(filePath).toLowerCase();
  if (DOC_DATA_EXTENSIONS.has(ext)) {
    process.exit(0);
  }

  // --- Resolve session id and sentinel paths ---
  const sessionId = resolveSessionId(payload);

  // --- Bypass 3: dispatch-nudge suppression sentinel ---
  const nudgeOkSentinel = `/tmp/coordinator-dispatch-nudge-ok-${sessionId}`;
  try {
    fs.accessSync(nudgeOkSentinel, fs.constants.F_OK);
    process.exit(0); // sentinel present → suppressed
  } catch {
    // sentinel absent → continue
  }

  // --- Bypass 4: autonomous-run sentinel ---
  const autonomousSentinel = `/tmp/autonomous-run-${sessionId}`;
  try {
    fs.accessSync(autonomousSentinel, fs.constants.F_OK);
    process.exit(0); // autonomous mode → suppress nudge
  } catch {
    // not in autonomous mode → continue
  }

  // --- Emit the offer-shaped nudge ---
  // Leads with the better path (dispatcher), then names the inline carve-out.
  // Never blocks, never exits non-zero.

  // When session_id was absent the resolved sentinel path is pid-scoped and
  // will not match across re-invocations — append a warning so the EM is not
  // misled into writing a sentinel that will never be seen again.
  // Review: code-reviewer — fallback sentinel instruction misleads when session_id absent
  const hasTrueSessionId = payload.session_id &&
    typeof payload.session_id === 'string' &&
    payload.session_id.trim().length > 0;

  const nudgeMessage =
    `You're the EM, not the typist. This is a code-file write — did you mean to dispatch an executor (/execute-plan or a fan-out wave)? ` +
    `If inline is genuinely cheaper here, name why per the When-to-EM-Inline checklist (agent-dispatch-economics.md). ` +
    `To suppress for an authorized inline run, the carve-out path writes /tmp/coordinator-dispatch-nudge-ok-${sessionId}` +
    (hasTrueSessionId
      ? '.'
      : ' (invocation-scoped — session_id was absent from payload; this sentinel only matches if the same OS pid runs the hook again).');

  // Mirror validate-ac-grammar.js warn-branch: additionalContext only, no hookEventName.
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      additionalContext: `[em-code-dispatch nudge] ${nudgeMessage}`,
    },
  }));
  process.exit(0);
}

main().catch(err => {
  process.stderr.write(`nudge-em-code-dispatch: unexpected error: ${err.message}\n`);
  process.exit(0);
});
